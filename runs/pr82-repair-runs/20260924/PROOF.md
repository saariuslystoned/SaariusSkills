# PR82 repair proof

- Cursor admission regression: 7/7 passed.
- Antigravity admission regression: 7/7 passed.
- Shared host-policy regression: 14/14 passed.
- Full Cursor bridge suite: 73 passed, 11 skipped.
- Full Antigravity bridge suite: 55 passed, 12 skipped.
- `node --check` passed for both brokers and admission tests; `git diff --check` passed.
- No live provider, install, account, merge, or external message action performed.
