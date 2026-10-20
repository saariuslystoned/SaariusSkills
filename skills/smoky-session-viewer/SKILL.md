---
name: smoky-session-viewer
description: Render an explicitly selected local agent JSONL transcript as searchable private HTML. Use for local inspection or debugging; rendering does not make a transcript safe to publish.
---

# Private Session Viewer

Read the current request and trusted repository instructions first. If they name an optional binding for this skill, read it for local targets, tools and policy. Without a binding, use the portable workflow below. A binding does not grant authority to act.

Read `references/session-policy.md`. Use an exact input file provided by the user or authorized task; do not discover sessions by searching unrelated accounts or home directories.

```sh
python3 skills/smoky-session-viewer/scripts/render-session session.jsonl --out session.html
```

The helper reads JSONL, extracts common message shapes and escapes content for a self-contained HTML viewer. Token replacement is best-effort and does not remove every kind of private information. Raw or unrecognized records, system instructions, file paths and personal data may remain. Treat the entire output as private.

Use `--open` only when local viewing is requested. Use `--no-redact` only for explicitly authorized private inspection. Do not upload, attach or send the output merely because rendering completed; sharing requires a separate authorized review/redaction step. Preserve the source transcript and use a separate output path.

Output is created with owner-only permissions where supported. Existing output requires `--overwrite`; the source transcript and symlink outputs are refused.

Report input/output paths, event count, warnings, whether the viewer opened and the remaining privacy limitations. For product behavior use `smoky-behavior-validator`; this helper does not stop processes, clean sessions or prove an application works.
