import assert from 'node:assert/strict';
import { mkdtemp, mkdir, readFile, rm, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { CursorAcpBroker } from '../broker.mjs';

const LUNA = 'gpt-5.6-luna[context=272k,reasoning=medium,fast=false]';
const GROK = 'grok-4.6[effort=high,fast=true]';
const GROK7 = 'grok-4.7[context=256k,reasoning_effort=high,fast=true]';
const PING = '\n\nError: RetriableError: [unavailable] PING timed out';

class Runtime {
  model = LUNA;
  available = [LUNA, GROK, GROK7];
  turns = [];
  closes = [];
  output = 'Partial work saved.' + PING;
  result = { status: 'completed', stopReason: 'end_turn' };
  cleanupFails = false;
  events = null;
  async ensureSession({ sessionKey, cwd }) { return { sessionKey, cwd }; }
  async getStatus() { return { models: { currentModelId: this.model, availableModelIds: this.available } }; }
  async setModel({ model }) { this.model = model; }
  startTurn(input) {
    this.turns.push({ model: this.model, text: input.text, timeoutMs: input.timeoutMs });
    const events = this.events ?? [{ type: 'text_delta', stream: 'output', text: this.output }];
    const result = this.result;
    return {
      promptStarted: Promise.resolve(),
      events: (async function* () { yield* events; })(),
      result: new Promise(resolve => setTimeout(() => resolve(result), 5)),
      cancel: async () => {},
    };
  }
  async close(input) { this.closes.push(input); if (this.cleanupFails) throw new Error('cleanup unobservable'); }
  async shutdown() {}
}

async function setup(t, options = {}) {
  const root = await mkdtemp(path.join(os.tmpdir(), 'cursor-fallback-'));
  const workspace = path.join(root, 'workspace');
  await mkdir(workspace);
  const executable = path.join(root, 'cursor-agent');
  await writeFile(executable, '#!/bin/sh\nexit 0\n', { mode: 0o700 });
  const runtime = new Runtime();
  const broker = await new CursorAcpBroker({
    stateRoot: path.join(root, 'state'), cursorExecutable: executable, runtime,
    execFile: async () => ({ stdout: 'fixture' }), processEnv: {},
    defaultHostConversationId: 'fallback-test', defaultBinderId: 'test-owner', ...options,
  }).init();
  t.after(() => broker.close());
  return { root, workspace, executable, runtime, broker };
}
async function run(broker, workspace, input = {}) {
  const job = await broker.delegate({ workspace, prompt: 'Inspect one bounded fixture.', ...input });
  return broker.result({ jobId: job.jobId, waitMs: 5000 });
}
const refuses = (code) => error => error.code === code;

test('Cursor native PING suffix fails the turn while retaining partial handoff and cleanup', async t => {
  const { broker, workspace } = await setup(t);
  const done = await run(broker, workspace);
  assert.equal(done.status, 'failed');
  assert.equal(done.error.code, 'CURSOR_TRANSPORT_UNAVAILABLE');
  assert.equal(done.error.source, 'cursor-output-signature');
  assert.match(done.handoff, /Partial work saved/);
  assert.equal(done.taskComplete, true);
  assert.equal(done.cleanupReady, true);
  assert.equal(done.complete, true);
  assert.equal(done.stopReason, 'end_turn');
  assert.match(await readFile(done.proof.proof, 'utf8'), /CURSOR_TRANSPORT_UNAVAILABLE/);
});

test('quoted, fenced, thought, tool output and recovered errors do not impersonate native terminal failure', async t => {
  const { broker, workspace, runtime } = await setup(t);
  for (const text of [JSON.stringify(PING), '```text' + PING + '\n```', PING + '\nRecovered.', 'Example: ' + PING.trim(), '```text\n' + 'x'.repeat(13000) + PING]) {
    runtime.output = text;
    assert.equal((await run(broker, workspace)).status, 'completed');
  }
  for (const event of [
    { type: 'text_delta', stream: 'thought', text: PING },
    { type: 'tool_call', text: PING },
  ]) {
    runtime.events = [event, { type: 'text_delta', stream: 'output', text: 'Completed fixture.' }];
    assert.equal((await run(broker, workspace)).status, 'completed');
  }
});

test('structured runtime errors take precedence even if runtime result says completed', async t => {
  const { broker, workspace, runtime } = await setup(t);
  runtime.events = [{ type: 'error', code: 'FIXTURE_FAILURE', message: 'fixture transport failed' }];
  const done = await run(broker, workspace);
  assert.equal(done.status, 'failed');
  assert.equal(done.error.code, 'FIXTURE_FAILURE');
});

test('opt-in fallback is parent reviewed, creates a new exact-model job, and retains root deadline and history', async t => {
  let time = Date.now();
  const { broker, workspace, runtime } = await setup(t, { now: () => new Date(time).toISOString() });
  const first = await run(broker, workspace, { fallbackModels: ['grok-4.6', 'grok-4.7'], timeoutMs: 30000 });
  assert.equal(first.fallback.nextModel, GROK);
  assert.equal(first.fallback.eligible, true);
  assert.equal(runtime.turns.length, 1); // result/status never dispatches fallback
  await assert.rejects(() => broker.delegate({ workspace, prompt: 'Continue reviewed work.', retryOf: first.jobId }), refuses('FALLBACK_REVIEW_REQUIRED'));
  time += 5000;
  const second = await run(broker, workspace, { retryOf: first.jobId, partialWorkReviewed: true, prompt: 'Continue only the inspected unfinished fixture step.' });
  assert.notEqual(second.jobId, first.jobId);
  assert.equal(second.model, GROK);
  assert.equal(second.fallback.rootJobId, first.jobId);
  assert.equal(second.fallback.nextModel, GROK7);
  assert.equal(second.timeoutMs, 25000);
  assert.equal(second.binding.replacedJobId, first.jobId);
  assert.equal((await broker.result({ jobId: first.jobId })).model, LUNA);
  const third = await run(broker, workspace, { retryOf: second.jobId, partialWorkReviewed: true });
  assert.equal(third.model, GROK7);
  assert.equal(third.fallback.reason, 'exhausted');
  await assert.rejects(() => broker.delegate({ workspace, prompt: 'No fourth attempt.', retryOf: third.jobId, partialWorkReviewed: true }), refuses('FALLBACK_EXHAUSTED'));
  assert.equal(runtime.turns.length, 3);
  assert(!runtime.turns[1].text.includes('Inspect one bounded fixture.'));
});

test('explicit per-job and server model/effort pins reject a nonempty fallback chain before launching', async t => {
  for (const options of [{}, { model: 'grok-4.6' }, { model: 'gpt-5.6-luna-medium' }, { effort: 'medium' }]) {
    const { broker, workspace, runtime } = await setup(t, options);
    const pins = options.model || options.effort ? [{}] : [{ model: 'gpt-5.6-luna' }, { effort: 'medium' }];
    for (const pin of pins) await assert.rejects(() => run(broker, workspace, { ...pin, fallbackModels: ['grok-4.6'] }), refuses('FALLBACK_PINNED'));
    assert.equal(runtime.turns.length, 0);
    assert.equal(runtime.closes.length, 0);
  }
});

test('fallback configuration rejects duplicates, unknown, ambiguous and oversized lists without a prompt', async t => {
  const { broker, workspace, runtime } = await setup(t);
  for (const [fallbackModels, code] of [
    [['grok-4.6', GROK], 'FALLBACK_DUPLICATE'], [['gpt-5.6-luna'], 'FALLBACK_DUPLICATE'],
    [['missing'], 'MODEL_UNAVAILABLE'], [['grok-4.6', 'grok-4.7', 'missing'], 'INVALID_FALLBACK_MODELS'],
    ['grok-4.6', 'INVALID_FALLBACK_MODELS'],
  ]) await assert.rejects(() => run(broker, workspace, { fallbackModels }), refuses(code));
  runtime.available.push('grok-4.6[effort=medium,fast=true]');
  await assert.rejects(() => run(broker, workspace, { fallbackModels: ['grok-4.6'] }), refuses('MODEL_AMBIGUOUS'));
  assert.equal(runtime.turns.length, 0);
});

test('fallback rejects unproven cleanup, explicit failure classes, completed partial work and expired budget', async t => {
  for (const kind of ['cleanup', 'permission', 'timeout', 'completed', 'expired']) {
    let time = Date.now();
    const { broker, workspace, runtime } = await setup(t, { now: () => new Date(time).toISOString() });
    if (kind === 'cleanup') runtime.cleanupFails = true;
    if (kind === 'permission') runtime.result = { status: 'failed', error: { code: 'PERMISSION_PROMPT_UNAVAILABLE', message: 'write denied' } };
    if (kind === 'timeout') runtime.result = { status: 'failed', error: { code: 'TIMEOUT', message: 'job timeout' } };
    if (kind === 'completed') runtime.output = 'Browser verification incomplete; bounded turn ended.';
    const first = await run(broker, workspace, { fallbackModels: ['grok-4.6'], timeoutMs: 10000 });
    if (kind === 'expired') time += 10001;
    await assert.rejects(() => broker.delegate({ workspace, prompt: 'Continue.', retryOf: first.jobId, partialWorkReviewed: true }));
    assert.equal(runtime.turns.length, 1);
  }
});

test('fallback retains exact workspace, owner, executable and permissions; refuses overrides and stale binding', async t => {
  const { broker, workspace, runtime } = await setup(t);
  const first = await run(broker, workspace, { fallbackModels: ['grok-4.6'] });
  for (const override of [{ model: 'grok-4.7' }, { effort: 'high' }, { timeoutMs: 30000 }, { fallbackModels: [] }]) {
    await assert.rejects(() => run(broker, workspace, { retryOf: first.jobId, partialWorkReviewed: true, ...override }), refuses('FALLBACK_OVERRIDE_FORBIDDEN'));
  }
  const other = path.join(workspace, 'other'); await mkdir(other);
  await assert.rejects(() => run(broker, other, { retryOf: first.jobId, partialWorkReviewed: true }), refuses('FALLBACK_SCOPE_CHANGED'));
  broker.cursorExecutable += '-changed';
  await assert.rejects(() => run(broker, workspace, { retryOf: first.jobId, partialWorkReviewed: true }), refuses('FALLBACK_SCOPE_CHANGED'));
  broker.cursorExecutable = first.route.executable;
  broker.processEnv.SAARIUS_ACP_PERMISSION_MODE = 'approve-all';
  await assert.rejects(() => run(broker, workspace, { retryOf: first.jobId, partialWorkReviewed: true }), refuses('FALLBACK_SCOPE_CHANGED'));
  broker.processEnv = {};
  runtime.output = 'Completed next assigned job.';
  await run(broker, workspace);
  await assert.rejects(() => run(broker, workspace, { retryOf: first.jobId, partialWorkReviewed: true }), refuses('FALLBACK_SOURCE_CHANGED'));
  assert.equal(runtime.turns.length, 2);
});


test('missing binding, foreign identity, changed pins and catalog drift cannot continue a fallback', async t => {
  for (const kind of ['missing-binding', 'foreign-conversation', 'foreign-binder', 'pin', 'catalog']) {
    const { broker, workspace, runtime, root } = await setup(t);
    const first = await run(broker, workspace, { fallbackModels: ['grok-4.6'] });
    if (kind === 'missing-binding') await rm(path.join(root, 'state', 'bindings'), { recursive: true });
    if (kind === 'foreign-conversation') broker.defaultHostConversationId = 'other-conversation';
    if (kind === 'foreign-binder') broker.defaultBinderId = 'other-binder';
    if (kind === 'pin') broker.model = 'grok-4.7';
    if (kind === 'catalog') runtime.available = [LUNA, GROK7];
    await assert.rejects(() => broker.delegate({ workspace, prompt: 'Continue reviewed partial work.', retryOf: first.jobId, partialWorkReviewed: true }));
    assert.equal(runtime.turns.length, 1);
  }
});

test('the original deadline is rechecked after startup before any fallback prompt', async t => {
  let time = Date.now();
  const { broker, workspace, runtime } = await setup(t, { now: () => new Date(time).toISOString() });
  const first = await run(broker, workspace, { fallbackModels: ['grok-4.6'], timeoutMs: 10000 });
  const ensure = runtime.ensureSession.bind(runtime);
  runtime.ensureSession = async input => { time += 10001; return ensure(input); };
  const next = await run(broker, workspace, { retryOf: first.jobId, partialWorkReviewed: true });
  assert.equal(next.status, 'failed');
  assert.equal(next.error.code, 'FALLBACK_DEADLINE_EXHAUSTED');
  assert.equal(runtime.turns.length, 1);
  assert.equal(next.cleanupReady, true);
});

test('a reviewed chain survives broker restart and concurrent retry admits only one next worker', async t => {
  const { broker, workspace, root, executable } = await setup(t);
  const first = await run(broker, workspace, { fallbackModels: ['grok-4.6'] });
  await broker.close();
  const runtime = new Runtime();
  const restarted = await new CursorAcpBroker({
    stateRoot: path.join(root, 'state'), cursorExecutable: executable, runtime,
    execFile: async () => ({ stdout: 'fixture' }), processEnv: {},
    defaultHostConversationId: 'fallback-test', defaultBinderId: 'test-owner',
  }).init();
  t.after(() => restarted.close());
  const attempts = await Promise.allSettled([1, 2].map(() => restarted.delegate({
    workspace, prompt: 'Continue only the inspected step.', retryOf: first.jobId, partialWorkReviewed: true,
  })));
  assert.equal(attempts.filter(result => result.status === 'fulfilled').length, 1);
  const job = attempts.find(result => result.status === 'fulfilled').value;
  const done = await restarted.result({ jobId: job.jobId, waitMs: 5000 });
  assert.equal(done.model, GROK);
  assert.equal(done.fallback.rootJobId, first.jobId);
  assert.equal(runtime.turns.length, 1);
});

test('published runtime and real synthetic ACP child reproduce error-as-text and reviewed model continuation', { timeout: 15000 }, async t => {
  const { createAcpRuntime, createAgentRegistry } = await import('acpx/runtime');
  const { createProcessLifecycleTracker } = await import('../../acp-runtime/lifecycle.mjs');
  const root = await mkdtemp(path.join(os.tmpdir(), 'cursor-fallback-peer-'));
  const peer = path.join(root, 'peer.mjs');
  await writeFile(peer, `
    import { createInterface } from 'node:readline';
    const models = ${JSON.stringify([LUNA, GROK])};
    let model = models[0];
    const send = (id, result) => process.stdout.write(JSON.stringify({jsonrpc:'2.0',id,result})+'\\n');
    createInterface({input:process.stdin}).on('line', line => {
      const {id,method,params} = JSON.parse(line);
      if(id === undefined) return;
      if(method === 'initialize') return send(id,{protocolVersion:params.protocolVersion,agentCapabilities:{loadSession:true,sessionCapabilities:{close:{}}},authMethods:[]});
      if(method === 'session/new') return send(id,{sessionId:'failure-peer',models:{currentModelId:model,availableModels:models.map(modelId => ({modelId,name:modelId}))}});
      if(method === 'session/set_model') { model = params.modelId; return send(id,{}); }
      if(method === 'session/prompt') {
        process.stdout.write(JSON.stringify({jsonrpc:'2.0',method:'session/update',params:{sessionId:params.sessionId,update:{sessionUpdate:'agent_message_chunk',content:{type:'text',text:model === models[0] ? ${JSON.stringify('Synthetic partial work.' + PING)} : 'Synthetic reviewed continuation complete.'}}}})+'\\n');
        return send(id,{stopReason:'end_turn'});
      }
      send(id,{});
    });
  `);
  const tracker = createProcessLifecycleTracker();
  const sessions = new Map();
  const runtime = createAcpRuntime({
    cwd: root, timeoutMs: 10000, fs: false, terminal: false,
    agentRegistry: createAgentRegistry({ overrides: { cursor: [process.execPath, peer] } }),
    sessionStore: {
      async load(id) { return structuredClone(sessions.get(id)); },
      async save(record) { sessions.set(record.acpxRecordId, structuredClone(record)); },
    },
    processLifecycle: tracker.processLifecycle,
  });
  const { broker, workspace } = await setup(t, { runtime, processLifecycleTracker: tracker });
  const first = await run(broker, workspace, { fallbackModels: ['grok-4.6'], timeoutMs: 10000 });
  assert.equal(first.status, 'failed');
  assert.equal(first.error.code, 'CURSOR_TRANSPORT_UNAVAILABLE');
  assert.equal(first.stopReason, 'end_turn');
  assert.equal(first.cleanupReady, true);
  const next = await run(broker, workspace, { retryOf: first.jobId, partialWorkReviewed: true, prompt: 'Continue the reviewed synthetic step.' });
  assert.equal(next.status, 'completed');
  assert.equal(next.model, GROK);
  assert.equal(next.cleanupReady, true);
  assert.match(next.handoff, /reviewed continuation complete/);
  for (const job of [first, next]) {
    const exits = await tracker.waitForOwnedExit(`cursor-acp:${job.jobId}`, { timeoutMs: 1000 });
    assert.equal(exits.status, 'exited');
    assert.equal(exits.started.length, exits.exits.length);
    assert.ok(exits.started.length > 0);
  }
});


test('rolling handoff truncation and fragmented deltas retain full-stream fence context', async t => {
  const { broker, workspace, runtime } = await setup(t);
  runtime.events = [
    { type: 'text_delta', text: '```text\n' + 'x'.repeat(13000) },
    { type: 'text_delta', text: '\n```' + PING.slice(0, 17) },
    { type: 'text_delta', text: PING.slice(17) },
  ];
  const done = await run(broker, workspace);
  assert.equal(done.status, 'failed');
  assert.equal(done.error.code, 'CURSOR_TRANSPORT_UNAVAILABLE');
});

test('observed Cursor resource-exhausted error fails visibly without inferring a model-scoped fallback', async t => {
  const { broker, workspace, runtime } = await setup(t);
  runtime.output = 'Review did not finish.\n\nError: RetriableError: [resource_exhausted] Error';
  const done = await run(broker, workspace, { fallbackModels: ['grok-4.6'] });
  assert.equal(done.status, 'failed');
  assert.equal(done.error.code, 'CURSOR_RESOURCE_EXHAUSTED');
  assert.equal(done.error.source, 'cursor-output-signature');
  assert.equal(done.cleanupReady, true);
  assert.match(done.handoff, /Review did not finish/);
  assert.equal(done.fallback.reason, 'failure_ineligible');
  await assert.rejects(() => run(broker, workspace, { retryOf: done.jobId, partialWorkReviewed: true }), refuses('FALLBACK_INELIGIBLE'));
  assert.equal(runtime.turns.length, 1);
});
