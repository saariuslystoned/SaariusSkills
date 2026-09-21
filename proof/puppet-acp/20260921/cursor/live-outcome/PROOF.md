# Cursor ACP v3 live attempt proof

The single released command was executed once from the fresh d5 worktree. Preflight passed: source head/tree, reviewed driver hash, pinned artifact/runtime hashes, and fresh session paths were verified.

The attempt failed during `_cursor_acp_structured_launch.require_observation` / `ensureSession` with `ValidationError`: the runtime could not spawn agent command `candidate` because a required executable, interpreter, working directory, or launch path was not found.

No candidate backend process or first task turn was established. The fixture remained unchanged (`changed_paths=[]`); the implementation and protected-test hashes remain the frozen baseline hashes. The session workspace/state are retained to prevent retry. No second prompt, retry, replacement session, or ordinary production admission occurred.

Budget: one session consumed, zero prompts completed, maximum two prompts of 300000 ms each, actual runtime timeout 30000 ms. No live qualification PASS.
