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

export const KNOWN_HARNESSES = Object.freeze(["antigravity", "muse", "grok-build", "cursor"]);
export const DEFAULT_HARNESS = "antigravity";
export const UNKNOWN_HARNESS = "unknown";

export function normalizeHarness(raw) {
  if (typeof raw !== "string" || !raw.trim()) return UNKNOWN_HARNESS;
  const s = raw.trim().toLowerCase();
  if (KNOWN_HARNESSES.includes(s)) return s;
  if (s === "antigravity-acp") return "antigravity";
  if (s === "muse-acp") return "muse";
  if (s === "grok-acp" || s === "grok") return "grok-build";
  if (s === "cursor-acp") return "cursor";
  return UNKNOWN_HARNESS;
}

export function resolveViewerHarness(rawHarness) {
  if (rawHarness === undefined || rawHarness === null) {
    // Existing records on CP-1 saved without the field were all Antigravity.
    return DEFAULT_HARNESS;
  }
  return normalizeHarness(rawHarness);
}

export const HARNESS_INFO = Object.freeze({
  antigravity: {
    key: "antigravity",
    name: "Antigravity",
    badgeClass: "harness-antigravity",
    svg: '<svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><path d="M8 1.5l-5 6h3.5v7h3v-7H13L8 1.5z"/></svg>',
  },
  muse: {
    key: "muse",
    name: "Muse",
    badgeClass: "harness-muse",
    svg: '<svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><path d="M12 2v7.18A2.5 2.5 0 1 0 11 11.5V5H6v5.18A2.5 2.5 0 1 0 5 12.5V2h7z"/></svg>',
  },
  "grok-build": {
    key: "grok-build",
    name: "Grok Build",
    badgeClass: "harness-grok",
    svg: '<svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><path d="M8 1a7 7 0 1 0 7 7h-2.5A4.5 4.5 0 1 1 8 3.5c1.2 0 2.3.5 3.1 1.3L13 3A7 7 0 0 0 8 1zm1 5v3h4V6H9z"/></svg>',
  },
  cursor: {
    key: "cursor",
    name: "Cursor",
    badgeClass: "harness-cursor",
    svg: '<svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><path d="M3 2l10 5.5-5 1.5-1.5 5L3 2z"/></svg>',
  },
  unknown: {
    key: "unknown",
    name: "Unknown",
    badgeClass: "harness-neutral harness-unknown",
    svg: '<svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><circle cx="8" cy="8" r="6" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="8" cy="8" r="2"/></svg>',
  },
});

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
export function buildView({ sessionId, task, transcript, harness }) {
  const resolvedHarness = resolveViewerHarness(harness ?? task?.harness);
  return redactDeep({
    sessionId,
    harness: resolvedHarness,
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
  const toSave = {
    sessionId,
    ...(record?.harness !== undefined ? { harness: normalizeHarness(record.harness) } : {}),
    task: record?.task ?? null,
    transcript: record?.transcript ?? createTranscript(),
  };
  await writeFile(tmp, JSON.stringify(redactDeep(toSave), null, 2), { mode: 0o600 });
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

export function renderHarnessBadge(rawHarness) {
  const harness = resolveViewerHarness(rawHarness);
  const info = HARNESS_INFO[harness] ?? HARNESS_INFO.unknown;
  return `<span class="badge harness-badge ${info.badgeClass}">${info.svg} ${escapeHtml(info.name)}</span>`;
}

export function harnessFaviconDataUri(rawHarness) {
  const harness = resolveViewerHarness(rawHarness);
  const info = HARNESS_INFO[harness] ?? HARNESS_INFO.unknown;
  return `data:image/svg+xml,${encodeURIComponent(info.svg)}`;
}

export function renderSessionHtml(view, { nonce }) {
  const t = view.task ?? {};
  const pr = safeHref(t.prUrl);
  const row = (label, value) => `<tr><th>${escapeHtml(label)}</th><td>${value}</td></tr>`;
  const entries = (view.entries ?? [])
    .map((entry) => {
      if (entry.kind === "tool") {
        return `<li class="tool"><div class="h">🔧 ${escapeHtml(entry.title)}${entry.toolKind ? ` <span class="k">${escapeHtml(entry.toolKind)}</span>` : ""}${entry.status ? ` <span class="s">${escapeHtml(entry.status)}</span>` : ""}<time>${escapeHtml(entry.at)}</time></div>${entry.detail ? `<pre>${escapeHtml(entry.detail)}</pre>` : ""}</li>`;
      }
      const label = entry.kind === "thought" ? "💭 thinking" : entry.kind === "status" ? "ℹ️ status" : "🤖 agent";
      return `<li class="${escapeHtml(entry.kind)}"><div class="h">${label}<time>${escapeHtml(entry.at)}</time></div><pre>${escapeHtml(entry.text)}</pre></li>`;
    })
    .join("\n");
  const plan = view.plan?.length
    ? `<h2>Plan</h2><ul class="plan">${view.plan.map((p) => `<li><span class="s">${escapeHtml(p.status)}</span> ${escapeHtml(p.content)}</li>`).join("")}</ul>`
    : "";
  const poll = view.live
    ? `<script nonce="${nonce}">(()=>{const v=${JSON.stringify(view.version).replace(/</g, "\\u003c")};const tick=async()=>{try{const r=await fetch(location.pathname+".json",{cache:"no-store",credentials:"same-origin"});if(r.ok){const j=await r.json();if(j.version!==v){location.reload();return;}}}catch{}setTimeout(tick,3000)};setTimeout(tick,3000)})();</script>`
    : "";
  const harnessBadge = renderHarnessBadge(view.harness);
  const faviconUri = harnessFaviconDataUri(view.harness);
  return `<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="robots" content="noindex, nofollow, noarchive, nosnippet">
<meta name="referrer" content="no-referrer">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Shed session ${escapeHtml(view.sessionId)}</title>
<link rel="icon" href="${escapeHtml(faviconUri)}">
<style nonce="${nonce}">
body{font:14px/1.45 -apple-system,system-ui,sans-serif;margin:0 auto;max-width:960px;padding:16px;color:#1b1b1b;background:#fafafa}
table{border-collapse:collapse}th{text-align:left;padding:2px 12px 2px 0;color:#555;font-weight:500}
pre{white-space:pre-wrap;word-break:break-word;background:#fff;border:1px solid #e3e3e3;border-radius:6px;padding:8px;margin:4px 0 0}
ol{list-style:none;padding:0}li{margin:10px 0}.h{font-weight:600}.h time{float:right;color:#888;font-weight:400;font-size:12px}
.k,.s{font-weight:400;font-size:12px;background:#eee;border-radius:4px;padding:1px 6px}.thought pre{color:#666;font-style:italic}
.badge{display:inline-block;padding:2px 8px;border-radius:10px;background:${view.live ? "#fff3cd" : "#e2f0d9"}}
.harness-badge{display:inline-flex;align-items:center;gap:4px;font-size:12px;font-weight:500;padding:2px 8px;border-radius:10px;vertical-align:middle;margin-left:6px;line-height:16px}
.harness-badge svg{width:14px;height:14px;fill:currentColor;flex-shrink:0}
.harness-antigravity{background:#e8f0fe;color:#1967d2;border:1px solid #c2d7fa}
.harness-muse{background:#fce8e6;color:#c5221f;border:1px solid #fad2cf}
.harness-grok{background:#f3e8fd;color:#7627bb;border:1px solid #e1cbf7}
.harness-cursor{background:#e6f4ea;color:#137333;border:1px solid #ceead6}
.harness-neutral{background:#f1f3f4;color:#5f6368;border:1px solid #dadce0}
</style></head><body>
<h1>Shed session ${harnessBadge}</h1>
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
