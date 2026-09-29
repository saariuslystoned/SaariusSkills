# acpx 0.19.3 offline upgrade

- Status: implementation complete; private bridge regressions pass; release review pending.
- Repo: `SaariusSkills`
- Worktree: `/Users/bobbybones/.codex/worktrees/acpx-0193-offline/SaariusSkills`
- Branch: `codex/acpx-0193-offline`
- Base: `960e3a343244eb96758591f884b1c64d9615a832` (`origin/main` at dispatch)
- Author: Luna offline implementation, explicitly authorized by the parent task; not ACP-authored.
- Scope: update the three bridge package pins and lockfiles from `acpx` 0.19.1 to published 0.19.3, preserve PR96 candidate/source contracts, and update focused offline regressions and notices.
- Published source tag: `v0.19.3` at `6b4714c7aaac8c38b1fe38354848d2546f65d87d`.
- Published npm integrity: `sha512-5YvCb+NG3XzDapxzrQRDS6zGN13mWZeugaeoq03kh9NCTFgJGzt7lrdC4jT2YXp9UV6Ieg8H+AYxs2y2+g1Z/g==`.
- Fenced history: native Cursor job `e2ce20af-34ee-4f4b-99fc-56512217c0f1` timed out in a different worktree and is not retried, reused, or treated as authoring proof.
- Safety gates: no installed plugin/runtime mutation, no live provider qualification, and no merge performed.
- Offline verification: Cursor `npm test` 76 passed / 11 skipped; Antigravity `npm test` 66 passed; Grok `npm test` 66 passed.
- Repository `npm run check` wrapper was stopped after its OpenClaw Node test-isolation worker hung in `recovery.test.mjs`; direct bridge suites passed, and the same wrapper behavior is recorded as a harness limitation.
