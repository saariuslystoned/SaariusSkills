import assert from "node:assert/strict";
import test from "node:test";
import { execFile as execFileCallback } from "node:child_process";
import { promisify } from "node:util";
import { compareProcessStartTimes, inspectProcessIdentity, parseUtcProcessStart } from "../process-identity.mjs";

const birth = "ps-utc-v1:2026-10-01T11:25:46.000Z";
const execFile = promisify(execFileCallback);

test("real ps observes this test process identically from callers in different timezones", {
  skip: process.platform === "win32",
}, async () => {
  const url = new URL("../process-identity.mjs", import.meta.url).href;
  const script = `import { inspectProcessIdentity } from ${JSON.stringify(url)}; console.log(JSON.stringify(await inspectProcessIdentity(Number(process.argv[1]))));`;
  const results = [];
  for (const TZ of ["America/New_York", "America/Los_Angeles", "UTC"]) {
    const { stdout } = await execFile(process.execPath, ["--input-type=module", "-e", script, String(process.pid)], {
      env: { PATH: process.env.PATH ?? "/usr/bin:/bin", TZ, LC_ALL: "C" }, timeout: 5000,
    });
    results.push(JSON.parse(stdout));
  }
  assert.equal(results[0].status, "alive");
  assert.equal(compareProcessStartTimes(results[0].startTime, results[0].startTime), "matching");
  assert.deepEqual(results[1], results[0]);
  assert.deepEqual(results[2], results[0]);
});

test("process probes collect UTC/C regardless of observer timezone and locale", async () => {
  for (const timezone of ["America/New_York", "America/Los_Angeles", "UTC"]) {
    for (const locale of ["C", "de_DE.UTF-8"]) {
      const run = async (command, args, options) => {
        assert.equal(command, "ps");
        assert.deepEqual(args, ["-p", "55161", "-o", "lstart="]);
        assert.equal(options.env.TZ, "UTC", `observer ${timezone}/${locale}`);
        assert.equal(options.env.LC_ALL, "C");
        assert.equal(options.timeout, 2000);
        assert.equal(options.maxBuffer, 4096);
        return { stdout: "Thu Oct  1 11:25:46 2026\n" };
      };
      assert.deepEqual(await inspectProcessIdentity(55161, run, () => {}), { status: "alive", startTime: birth });
    }
  }
});

test("UTC identities remain stable across the DST overlap", () => {
  const first = parseUtcProcessStart("Sun Nov  1 05:30:00 2026");
  const second = parseUtcProcessStart("Sun Nov  1 06:30:00 2026");
  assert.equal(compareProcessStartTimes(first, first), "matching");
  assert.equal(compareProcessStartTimes(first, second), "different");
});

test("genuine birth changes are different; legacy, mixed and malformed identities are unknown", () => {
  assert.equal(compareProcessStartTimes(birth, birth), "matching");
  assert.equal(compareProcessStartTimes(birth, "ps-utc-v1:2026-10-01T11:25:47.000Z"), "different");
  for (const other of [undefined, "", "Thu Oct  1 07:25:46 2026", "ps-utc-v2:2026-10-01T11:25:46.000Z", "ps-utc-v1:2026-02-30T11:25:46.000Z"]) {
    assert.equal(compareProcessStartTimes(birth, other), "unknown");
    assert.equal(compareProcessStartTimes(other, birth), "unknown");
    assert.equal(compareProcessStartTimes(other, other), "unknown");
  }
});

test("malformed or incomplete ps rows never establish identity", async () => {
  for (const stdout of ["", "Thu Oct 32 11:25:46 2026", "Thu Oct  1 25:25:46 2026", "Thu Okt  1 11:25:46 2026", "Thu Oct  1 11:25:46 2026\nThu Oct  1 11:25:47 2026", undefined]) {
    assert.deepEqual(await inspectProcessIdentity(55161, async () => ({ stdout }), () => {}), { status: "unknown" });
  }
});

test("timeouts and permission failures are unknown; only ESRCH establishes missing", async () => {
  const failure = (code) => Object.assign(new Error(code), { code });
  for (const code of ["ETIMEDOUT", "EPERM", "EACCES"]) {
    assert.deepEqual(await inspectProcessIdentity(55161, async () => { throw failure(code); }, () => {}), { status: "unknown" });
  }
  assert.deepEqual(await inspectProcessIdentity(55161, async () => { throw failure("EPERM"); }, () => { throw failure("EPERM"); }), { status: "unknown" });
  let called = false;
  assert.deepEqual(await inspectProcessIdentity(55161, async () => { called = true; }, () => { throw failure("ESRCH"); }), { status: "missing" });
  assert.equal(called, false);
  let checks = 0;
  assert.deepEqual(await inspectProcessIdentity(55161, async () => { throw failure("ETIMEDOUT"); }, () => { if (++checks > 1) throw failure("ESRCH"); }), { status: "missing" });
});

test("invalid PID never probes or executes", async () => {
  for (const pid of [0, -1, 1.5, NaN, "55161", Number.MAX_SAFE_INTEGER + 1]) {
    assert.deepEqual(await inspectProcessIdentity(pid, () => { throw new Error("executed"); }, () => { throw new Error("probed"); }), { status: "unknown" });
  }
});
