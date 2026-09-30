import assert from "node:assert/strict";
import { mkdtemp, mkdir, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { CursorAcpBroker } from "../../cursor-acp/broker.mjs";

// Real pinned ACpx + real local child, no provider, subscription, credentials,
// writes outside the temp fixture, or detached process. This is synthetic proof.
test("local synthetic smoke: unsupported close, owned exit, restart and second full task", { timeout: 30_000 }, async () => {
  const root = await mkdtemp(path.join(tmpdir(), "acp-local-lifecycle-smoke-"));
  const workspace = path.join(root, "workspace");
  await mkdir(workspace);
  const peer = fileURLToPath(new URL("../../cursor-acp/test/unsupported-close-peer.mjs", import.meta.url));
  const executable = path.join(root, "fixture-cursor");
  const quote = value => "'" + value.replaceAll("'", "'\\''") + "'";
  await writeFile(executable, `#!/bin/sh\nif [ "$1" = "--version" ]; then echo synthetic-1; exit 0; fi\nif [ "$2" = "--help" ]; then echo Usage: cursor acp; exit 0; fi\nexec ${quote(process.execPath)} ${quote(peer)}\n`, { mode: 0o700 });
  const options = { stateRoot: path.join(root, "state"), cursorExecutable: executable,
    model: "candidate-default", processEnv: { HOME: root, PATH: process.env.PATH ?? "" },
    defaultHostConversationId: "actual-unchanged-conversation", timeoutMs: 5000,
    runtimeControlTimeoutMs: 5000, workerExitWaitMs: 2000 };
  const first = new CursorAcpBroker(options);
  let second;
  try {
    const submitted = await first.delegate({ workspace, prompt: "synthetic hello" });
    const result = await first.result({ jobId: submitted.jobId, waitMs: 10000 });
    assert.equal(result.status, "completed", JSON.stringify(result));
    assert.equal(result.complete, true, JSON.stringify(result));
    assert.equal(result.cleanup.backendSessionDiscard, "unsupported");
    const raw = await first.getJob(submitted.jobId);
    assert.ok(raw.workers.length > 0);
    for (const worker of raw.workers) {
      assert.ok(worker.processStartTime);
      assert.equal((await first.inspectProcess(worker.pid)).status, "missing");
    }
    await first.close();
    second = new CursorAcpBroker(options);
    assert.notEqual(second.brokerId, first.brokerId);
    assert.equal(second.defaultBinderId, first.defaultBinderId);
    const followup = await second.delegate({ workspace, prompt: "synthetic follow-up" });
    assert.equal(followup.binding.replacedJobId, submitted.jobId);
    const done = await second.result({ jobId: followup.jobId, waitMs: 10000 });
    assert.equal(done.complete, true, JSON.stringify(done));
    for (const worker of (await second.getJob(followup.jobId)).workers) {
      assert.equal((await second.inspectProcess(worker.pid)).status, "missing");
    }
  } finally {
    await first.close();
    await second?.close();
  }
});
