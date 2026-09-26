// Objective grader for one evals/acp-routes task attempt.
// Copies the worker's workspace, adds the hidden tests (never shown to the
// worker), and reports syntax, protected-path, hidden-test and visible-test
// results. The worker's own summary is never consulted.
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { cp, mkdtemp, readdir, readFile, rm, stat } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

const SKIP_DIRS = new Set(["node_modules", ".git", "hidden"]);
const TEST_TIMEOUT_MS = 60_000;

async function walk(dir, base = dir) {
  const out = [];
  let entries = [];
  try { entries = await readdir(dir, { withFileTypes: true }); } catch { return out; }
  for (const e of entries) {
    if (SKIP_DIRS.has(e.name)) continue;
    const full = path.join(dir, e.name);
    if (e.isDirectory()) out.push(...await walk(full, base));
    else if (e.isFile()) out.push(path.relative(base, full));
  }
  return out.sort();
}

// Protected paths: every file the seed has under the path must still exist
// with identical bytes. New files are allowed (briefs may invite extra tests);
// edits and deletions of seed files are tampering.
async function changedSeedFiles(seed, work, rel) {
  const target = path.join(seed, rel);
  let files;
  try {
    files = (await stat(target)).isDirectory() ? (await walk(target)).map((f) => path.join(rel, f)) : [rel];
  } catch { return []; }
  const changed = [];
  for (const f of files) {
    let a, b;
    try { a = await readFile(path.join(seed, f)); } catch { continue; }
    try { b = await readFile(path.join(work, f)); } catch { changed.push(f); continue; }
    if (createHash("sha256").update(a).digest("hex") !== createHash("sha256").update(b).digest("hex")) changed.push(f);
  }
  return changed;
}

function runTap(cwd, files) {
  if (!files.length) return { pass: 0, fail: 0, total: 0, ran: false };
  const r = spawnSync(process.execPath, ["--test", "--test-reporter=tap", ...files], {
    cwd, encoding: "utf8", timeout: TEST_TIMEOUT_MS, env: { PATH: process.env.PATH, NODE_ENV: "test" },
  });
  const out = `${r.stdout ?? ""}`;
  const pass = Number(/^# pass (\d+)/m.exec(out)?.[1] ?? 0);
  const fail = Number(/^# fail (\d+)/m.exec(out)?.[1] ?? 0) + Number(/^# cancelled (\d+)/m.exec(out)?.[1] ?? 0);
  const timedOut = r.error?.code === "ETIMEDOUT";
  return { pass, fail: timedOut && pass + fail === 0 ? 1 : fail, total: pass + fail || (timedOut ? 1 : 0), ran: true, timedOut };
}

export async function loadTask(taskDir) {
  const task = JSON.parse(await readFile(path.join(taskDir, "task.json"), "utf8"));
  task.dir = taskDir;
  task.prompt = await readFile(path.join(taskDir, task.brief), "utf8");
  return task;
}

/**
 * Grade a finished workspace against a task.
 * @returns {Promise<{syntaxOk, syntaxErrors, protectedOk, changedProtected, hidden, visible, solved, score}>}
 */
export async function grade(workspace, task) {
  const seed = path.join(task.dir, "seed");
  const work = await mkdtemp(path.join(tmpdir(), `acp-eval-grade-${task.id}-`));
  try {
    await cp(workspace, work, { recursive: true, filter: (src) => !src.split(path.sep).includes(".git") && !src.split(path.sep).includes("node_modules") });

    const changedProtected = [];
    for (const rel of task.protect ?? []) changedProtected.push(...await changedSeedFiles(seed, work, rel));

    const syntaxErrors = [];
    for (const f of await walk(work)) {
      if (!/\.(mjs|js)$/.test(f)) continue;
      const r = spawnSync(process.execPath, ["--check", f], { cwd: work, encoding: "utf8" });
      if (r.status !== 0) syntaxErrors.push(f);
    }

    await rm(path.join(work, "hidden"), { recursive: true, force: true });
    await cp(path.join(task.dir, "hidden"), path.join(work, "hidden"), { recursive: true });
    const hiddenFiles = (await walk(path.join(work, "hidden"), work)).length
      ? (await readdir(path.join(work, "hidden"))).filter((f) => f.endsWith(".test.mjs")).map((f) => path.join("hidden", f))
      : [];
    const visibleFiles = (await walk(path.join(work, "test"))).filter((f) => f.endsWith(".test.mjs")).map((f) => path.join("test", f));

    const hidden = runTap(work, hiddenFiles);
    const visible = runTap(work, visibleFiles);
    const protectedOk = changedProtected.length === 0;
    const syntaxOk = syntaxErrors.length === 0;
    const solved = protectedOk && syntaxOk && hidden.total > 0 && hidden.fail === 0 && visible.fail === 0;
    const score = protectedOk && syntaxOk && hidden.total ? hidden.pass / hidden.total : 0;
    return { syntaxOk, syntaxErrors, protectedOk, changedProtected, hidden, visible, solved, score };
  } finally {
    await rm(work, { recursive: true, force: true });
  }
}
