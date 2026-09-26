// Grader validity: every task's hidden tests must fail on the untouched seed
// and pass on the reference solution, and the gates must catch tampering and
// broken syntax. Runs offline; no ACP route is contacted.
import test from "node:test";
import assert from "node:assert/strict";
import { cp, mkdtemp, readdir, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { grade, loadTask } from "../lib/grade.mjs";

const TASKS = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "tasks");
const ids = (await readdir(TASKS, { withFileTypes: true })).filter((d) => d.isDirectory()).map((d) => d.name).sort();

async function workspace(task, withReference) {
  const dir = await mkdtemp(path.join(tmpdir(), `acp-eval-ws-${task.id}-`));
  await cp(path.join(task.dir, "seed"), dir, { recursive: true });
  if (withReference) await cp(path.join(task.dir, "reference"), dir, { recursive: true });
  return dir;
}

test("five tasks are defined", () => {
  assert.deepEqual(ids, ["bounded-impl", "quick-fix", "refactor", "review", "ui-slice"]);
});

for (const id of ids) {
  test(`${id}: seed fails the hidden tests`, async () => {
    const task = await loadTask(path.join(TASKS, id));
    const ws = await workspace(task, false);
    try {
      const g = await grade(ws, task);
      assert.equal(g.solved, false);
      assert.ok(g.hidden.fail > 0, JSON.stringify(g.hidden));
    } finally { await rm(ws, { recursive: true, force: true }); }
  });

  test(`${id}: reference solution passes every check`, async () => {
    const task = await loadTask(path.join(TASKS, id));
    const ws = await workspace(task, true);
    try {
      const g = await grade(ws, task);
      assert.deepEqual({ solved: g.solved, syntaxErrors: g.syntaxErrors, changedProtected: g.changedProtected, hiddenFail: g.hidden.fail, visibleFail: g.visible.fail },
        { solved: true, syntaxErrors: [], changedProtected: [], hiddenFail: 0, visibleFail: 0 });
      assert.equal(g.score, 1);
    } finally { await rm(ws, { recursive: true, force: true }); }
  });
}

test("gates: editing a protected test fails the attempt", async () => {
  const task = await loadTask(path.join(TASKS, "quick-fix"));
  const ws = await workspace(task, true);
  try {
    await writeFile(path.join(ws, "test", "paginate.test.mjs"), "import test from 'node:test'; test('x', () => {});\n");
    const g = await grade(ws, task);
    assert.deepEqual(g.changedProtected, ["test/"]);
    assert.equal(g.solved, false);
    assert.equal(g.score, 0);
  } finally { await rm(ws, { recursive: true, force: true }); }
});

test("gates: literal \\n corruption is caught as a syntax failure", async () => {
  const task = await loadTask(path.join(TASKS, "bounded-impl"));
  const ws = await workspace(task, true);
  try {
    await writeFile(path.join(ws, "src", "extra.mjs"), 'export const a = 1;\\n  export const b = "\\n";\\n');
    const g = await grade(ws, task);
    assert.deepEqual(g.syntaxErrors, [path.join("src", "extra.mjs")]);
    assert.equal(g.solved, false);
  } finally { await rm(ws, { recursive: true, force: true }); }
});

test("gates: a hidden folder planted by the worker is replaced", async () => {
  const task = await loadTask(path.join(TASKS, "quick-fix"));
  const ws = await workspace(task, false);
  try {
    await cp(path.join(task.dir, "seed", "test"), path.join(ws, "hidden"), { recursive: true });
    await writeFile(path.join(ws, "hidden", "paginate.hidden.test.mjs"), "import test from 'node:test'; test('fake', () => {});\n");
    const g = await grade(ws, task);
    assert.equal(g.solved, false);
  } finally { await rm(ws, { recursive: true, force: true }); }
});
