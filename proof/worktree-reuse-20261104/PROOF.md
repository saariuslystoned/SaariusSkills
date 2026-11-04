# Assigned-workspace reuse

The worktree core now checks an existing assignment before provisioning.
Workers verify and reuse their supplied checkout; multi-repository work stays
inside each owning Git repository. The policy distinguishes helpers that
fetch from helpers that branch off local HEAD and warns that a runtime start
command may not adopt an existing workspace.

This is portable source guidance. It introduces no runtime, host, private
repository, installation, or activation requirement. Existing single-writer,
trusted-base, preservation and cleanup boundaries remain intact.

Validation: `python3 -m unittest tests.test_portable_skills tests.test_packaging -q`
passed 34 tests. `git diff --check` passed. Source review covered fresh
single-repository setup, new multi-repository setup, existing-session reuse,
and an already assigned worker; only the first two may need provisioning.
No live task or installed skill was changed. Runtime behavior and profile
bindings remain owned by their implementing projects.
