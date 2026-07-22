## Regular lifecycle overlay

This is the regular-session overlay.

- Execute ordinary unprefixed steering for the selected target session profile.
- Operate with `regular_only` activation and zero config writes.
- Never use native command mode and never request non-regular transport flags.
- Perform no cleanup side effects unless explicitly declared outside this wrapper.
