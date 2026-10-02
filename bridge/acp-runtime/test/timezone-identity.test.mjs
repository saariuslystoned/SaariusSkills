import assert from "node:assert/strict";
import test from "node:test";
import { mkdtemp, mkdir, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

for (const lane of ["antigravity", "cursor", "grok"]) {
  test(`${lane}: a timezone-shifted legacy birth is unknown, never PID reuse`, async () => {
    const { classifyOwnerIdentity, shouldRecoverOwnedJob } = await import(`../../${lane}-acp/broker.mjs`);
    const owner = { brokerId: "timezone-owner", pid: 55161, startTime: "Thu Oct  1 07:25:46 2026" };
    const probe = { status: "alive", startTime: "Thu Oct  1 04:25:46 2026" };
    assert.equal(classifyOwnerIdentity(owner, probe), "unknown");
    assert.equal(shouldRecoverOwnedJob({ status: "running", owner }, owner, probe), false);
  });

  for (const scenario of ["timezone-change", "unobservable-birth", "real-reuse"]) {
    test(`${lane}: binding lock ${scenario} requires comparable birth evidence`, async () => {
      const { claimConversationBind, conversationBindPath } = await import(`../../${lane}-acp/host-policy.mjs`);
      const root = await mkdtemp(path.join(tmpdir(), "acp-timezone-lock-"));
      const record = { hostConversationId: "timezone-conversation", binderId: "new-binder", jobId: "new-job", workspace: root };
      const target = conversationBindPath(root, record.hostConversationId);
      const lock = `${target}.lock`;
      await mkdir(lock);
      const oldOwner = { brokerId: "old-broker", pid: 55161, startTime: scenario === "real-reuse"
        ? "ps-utc-v1:2026-10-01T11:25:46.000Z" : "Thu Oct  1 07:25:46 2026" };
      const bytes = JSON.stringify(oldOwner);
      await writeFile(path.join(lock, "owner.json"), bytes);
      const options = {
        owner: { brokerId: "new-broker", pid: 100, startTime: "ps-utc-v1:2026-10-01T23:32:44.000Z" },
        inspectOwner: async () => ({ status: "alive", ...(scenario === "unobservable-birth" ? {} : {
          startTime: scenario === "real-reuse" ? "ps-utc-v1:2026-10-01T23:32:44.000Z" : "Thu Oct  1 04:25:46 2026",
        }) }),
      };
      if (scenario === "real-reuse") {
        assert.equal((await claimConversationBind(root, record, options)).jobId, record.jobId);
      } else {
        await assert.rejects(claimConversationBind(root, record, options), { code: "CONVERSATION_BIND_BUSY" });
        assert.equal(await readFile(path.join(lock, "owner.json"), "utf8"), bytes);
        await assert.rejects(readFile(target), { code: "ENOENT" });
      }
    });
  }
}
