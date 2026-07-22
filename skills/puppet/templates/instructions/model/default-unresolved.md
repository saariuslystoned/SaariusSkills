## Default model / unresolved policy

Use no explicit model-family assumptions in the baseline.

- Accept the caller-selected runtime defaults for this target.
- Preserve `runtime_binding` fields and model-observation defaults as opaque runtime bookkeeping.
- Never force additional model-specific prompts or routing tokens.
- Keep wrapper composition deterministic and policy hashes stable.
