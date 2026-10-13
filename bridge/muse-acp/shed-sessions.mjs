import { randomBytes } from "node:crypto";
import { readFile, rename, writeFile } from "node:fs/promises";
import path from "node:path";
import { redactDeep, redactText } from "./viewer-redact.mjs";

// Read-only session viewer support for remote-shed tasks. The runner keeps a
// bounded, redacted transcript per ACP session (prompt, agent messages,
// thoughts, tool calls, plan, final result) and persists it under
// <stateDir>/sessions/<sessionId>.json, so a finished session renders from
// disk with no live ACP process. Nothing here can start or cancel a task.
export const SESSION_ID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
export const SESSION_BASE_URL_ENV = "SAARIUS_ACP_SESSION_BASE_URL";
export const DEFAULT_SESSION_BASE_URL = "https://shed.sm0ky.dev";
export const MAX_TRANSCRIPT_ENTRIES = 2_000;
export const MAX_ENTRY_CHARS = 20_000;
const TERMINAL = new Set(["pr_opened", "pushed", "no_changes", "failed", "cancelled", "unavailable"]);

export function isSessionId(value) {
  return typeof value === "string" && SESSION_ID_PATTERN.test(value);
}

export function resolveSessionBaseUrl(env = process.env) {
  const raw = env[SESSION_BASE_URL_ENV]?.trim() || DEFAULT_SESSION_BASE_URL;
  const url = new URL(raw);
  if (url.protocol !== "https:" && !["127.0.0.1", "localhost"].includes(url.hostname)) {
    throw new Error(`${SESSION_BASE_URL_ENV} must be an https URL`);
  }
  return url.origin;
}

export function sessionUrl(baseUrl, sessionId) {
  return isSessionId(sessionId) ? `${baseUrl}/s/${sessionId}` : undefined;
}

const bound = (text) => (text.length > MAX_ENTRY_CHARS ? `${text.slice(0, MAX_ENTRY_CHARS - 1)}…` : text);

export function createTranscript({ prompt } = {}) {
  return { prompt: redactText(prompt ?? ""), entries: [], plan: [], result: null, droppedEntries: 0, version: 0 };
}

// Fold one acpx runtime event (text_delta / tool_call / status) into the transcript.
export function appendEvent(transcript, event, at = new Date().toISOString()) {
  if (!event || typeof event !== "object") return;
  transcript.version += 1;
  const push = (entry) => {
    if (transcript.entries.length >= MAX_TRANSCRIPT_ENTRIES) {
      transcript.droppedEntries += 1;
      return;
    }
    transcript.entries.push({ at, ...entry });
  };
  if (event.type === "text_delta") {
    const kind = event.stream === "thought" ? "thought" : "message";
    const last = transcript.entries.at(-1);
    if (last && last.kind === kind) {
      last.text = bound(last.text + String(event.text ?? ""));
      return;
    }
    push({ kind, text: bound(String(event.text ?? "")) });
    return;
  }
  if (event.type === "tool_call") {
    const id = typeof event.toolCallId === "string" ? event.toolCallId : undefined;
    const existing = id ? transcript.entries.find((entry) => entry.kind === "tool" && entry.toolCallId === id) : undefined;
    const detail = bound(String(event.text ?? ""));
    if (existing) {
      if (event.status) existing.status = String(event.status);
      if (event.title) existing.title = String(event.title);
      if (detail) existing.detail = detail;
      existing.updatedAt = at;
      return;
    }
    push({ kind: "tool", toolCallId: id, title: String(event.title ?? "tool call"), toolKind: event.kind ? String(event.kind) : undefined, status: event.status ? String(event.status) : undefined, detail });
    return;
  }
  if (event.type === "status") {
    if (Array.isArray(event.entries)) {
      transcript.plan = event.entries.slice(0, 100).map((entry) => ({ content: bound(String(entry?.content ?? "")), status: String(entry?.status ?? "") }));
      return;
    }
    // usage / command-list chatter is not useful to a reader.
    if (/usage|available_commands/i.test(String(event.tag ?? ""))) return;
    if (event.text) push({ kind: "status", text: bound(String(event.text)) });
  }
}

export function isTerminalTaskStatus(status) {
  return TERMINAL.has(status);
}

// The one shape both /s/<id> and /s/<id>.json render from. Always redacted.
export function buildView({ sessionId, task, transcript }) {
  return redactDeep({
    sessionId,
    live: !isTerminalTaskStatus(task?.status),
    task: task
      ? {
          taskId: task.taskId,
          status: task.status,
          repo: task.repo,
          forge: task.forge,
          baseBranch: task.baseBranch,
          branch: task.branch,
          requestedBy: task.requestedBy,
          prUrl: task.prUrl ?? null,
          headSha: task.headSha ?? null,
          createdAt: task.createdAt,
          updatedAt: task.updatedAt,
          error: task.error ?? null,
        }
      : null,
    prompt: transcript?.prompt ?? "",
    plan: transcript?.plan ?? [],
    entries: transcript?.entries ?? [],
    droppedEntries: transcript?.droppedEntries ?? 0,
    result: transcript?.result ?? task?.summary ?? null,
    version: `${task?.updatedAt ?? ""}:${transcript?.version ?? 0}`,
  });
}

export async function saveSession(dir, sessionId, record) {
  if (!isSessionId(sessionId)) throw new Error("invalid session id");
  const file = path.join(dir, `${sessionId}.json`);
  const tmp = `${file}.${randomBytes(4).toString("hex")}.tmp`;
  await writeFile(tmp, JSON.stringify(redactDeep(record)), { mode: 0o600 });
  await rename(tmp, file);
}

export async function loadSession(dir, sessionId) {
  if (!isSessionId(sessionId)) return null;
  try {
    return JSON.parse(await readFile(path.join(dir, `${sessionId}.json`), "utf8"));
  } catch {
    return null;
  }
}

const escapeHtml = (value) =>
  String(value ?? "").replace(/[&<>"']/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[ch]);

const safeHref = (value) => (typeof value === "string" && /^https:\/\/[^\s"'<>]+$/.test(value) ? value : null);

export function renderSessionHtml(view, { nonce }) {
  const t = view.task ?? {};
  const pr = safeHref(t.prUrl);
  const row = (label, value) => `<tr><th>${escapeHtml(label)}</th><td>${value}</td></tr>`;
  const entries = view.entries
    .map((entry) => {
      if (entry.kind === "tool") {
        return `<li class="tool"><div class="h">🔧 ${escapeHtml(entry.title)}${entry.toolKind ? ` <span class="k">${escapeHtml(entry.toolKind)}</span>` : ""}${entry.status ? ` <span class="s">${escapeHtml(entry.status)}</span>` : ""}<time>${escapeHtml(entry.at)}</time></div>${entry.detail ? `<pre>${escapeHtml(entry.detail)}</pre>` : ""}</li>`;
      }
      const label = entry.kind === "thought" ? "💭 thinking" : entry.kind === "status" ? "ℹ️ status" : "🤖 agent";
      return `<li class="${escapeHtml(entry.kind)}"><div class="h">${label}<time>${escapeHtml(entry.at)}</time></div><pre>${escapeHtml(entry.text)}</pre></li>`;
    })
    .join("\n");
  const plan = view.plan.length
    ? `<h2>Plan</h2><ul class="plan">${view.plan.map((p) => `<li><span class="s">${escapeHtml(p.status)}</span> ${escapeHtml(p.content)}</li>`).join("")}</ul>`
    : "";
  const poll = view.live
    ? `<script nonce="${nonce}">(()=>{const v=${JSON.stringify(view.version).replace(/</g, "\\u003c")};const tick=async()=>{try{const r=await fetch(location.pathname+".json",{cache:"no-store",credentials:"same-origin"});if(r.ok){const j=await r.json();if(j.version!==v){location.reload();return;}}}catch{}setTimeout(tick,3000)};setTimeout(tick,3000)})();</script>`
    : "";
  return `<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="robots" content="noindex, nofollow, noarchive, nosnippet">
<meta name="referrer" content="no-referrer">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Shed session ${escapeHtml(view.sessionId)}</title>
<style nonce="${nonce}">
body{font:14px/1.45 -apple-system,system-ui,sans-serif;margin:0 auto;max-width:960px;padding:16px;color:#1b1b1b;background:#fafafa}
table{border-collapse:collapse}th{text-align:left;padding:2px 12px 2px 0;color:#555;font-weight:500}
pre{white-space:pre-wrap;word-break:break-word;background:#fff;border:1px solid #e3e3e3;border-radius:6px;padding:8px;margin:4px 0 0}
ol{list-style:none;padding:0}li{margin:10px 0}.h{font-weight:600}.h time{float:right;color:#888;font-weight:400;font-size:12px}
.k,.s{font-weight:400;font-size:12px;background:#eee;border-radius:4px;padding:1px 6px}.thought pre{color:#666;font-style:italic}
.badge{display:inline-block;padding:2px 8px;border-radius:10px;background:${view.live ? "#fff3cd" : "#e2f0d9"}}
</style></head><body>
<h1>Shed session</h1>
<p><span class="badge">${escapeHtml(t.status ?? "unknown")}${view.live ? " · live" : ""}</span> <code>${escapeHtml(view.sessionId)}</code> · read-only</p>
<table>
${row("Task", `<code>${escapeHtml(t.taskId)}</code>`)}
${row("Repo", escapeHtml(`${t.forge ?? "github"}:${t.repo ?? ""}`))}
${row("Branch", `<code>${escapeHtml(t.branch)}</code> ← <code>${escapeHtml(t.baseBranch)}</code>`)}
${row("Requested by", escapeHtml(t.requestedBy))}
${row("PR", pr ? `<a href="${escapeHtml(pr)}" rel="noopener noreferrer">${escapeHtml(pr)}</a>` : "—")}
${t.headSha ? row("Head", `<code>${escapeHtml(t.headSha)}</code>`) : ""}
${row("Started", escapeHtml(t.createdAt))}
${row("Updated", escapeHtml(t.updatedAt))}
${t.error ? row("Error", escapeHtml(`${t.error.code}: ${t.error.message ?? ""}`)) : ""}
</table>
<h2>Prompt</h2><pre>${escapeHtml(view.prompt)}</pre>
${plan}
<h2>Steps</h2>
<ol>${entries || "<li>No agent activity recorded yet.</li>"}</ol>
${view.droppedEntries ? `<p>${escapeHtml(view.droppedEntries)} later steps were not kept (transcript cap).</p>` : ""}
<h2>Result</h2><pre>${escapeHtml(view.result ?? (view.live ? "(still running)" : "(none)"))}</pre>
${poll}
</body></html>`;
}
