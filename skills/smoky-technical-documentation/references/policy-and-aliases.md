# Policy and alias checks

Read this when agent instructions or contributor governance are in scope, not as a reason to audit unrelated policy files.

1. Discover the root and applicable nested instructions, contributor guide, aliases and scoped rules for the requested paths. Include hidden rule directories only where the repository/harness actually uses them. A directory named `.agents` may contain skills, not policy.
2. Identify the repository's declared canonical source, directory/glob applicability, harness loading semantics and alias relationships. Inspect existing pointers/symlinks without modifying them. Do not impose a universal AGENTS/CLAUDE/other-file precedence or create compatibility links by default.
3. Compare task-critical statements across applicable surfaces: commands and working directories, writable owner, permissions, review gates, prohibited actions and escalation. Record the source and scope of each conflict. Do not reconcile authority conflicts by choosing whichever text is easier to follow.
4. Preserve `must`, `may`, `only`, `unless`, `planned`, dates and safety conditions. Shortening a human-approval rule into an automatic action is a policy change, not an editorial improvement.
5. Verify referenced paths, tools and aliases through the current implementation and applicable contract. A compatibility pointer must resolve to the intended policy; an alias that invokes a wrapper must retain its distinct defaults and gates.
6. Propose policy or alias migration separately if it exceeds the wording task. Do not overwrite an existing rule directory, repoint a symlink or duplicate an entire policy for another harness as a cleanup side effect.

Keep instruction files actionable and bounded; use existing linked procedures for depth. Do not add arbitrary Always/Ask/Never headings, boilerplate governance, or a new model/tool roster just to match a template. The repository owns its policy and structure.

Report findings with location, conflicting/current evidence, reader impact and required decision. If remediation is authorized, make the smallest source-owned correction and recheck applicable links/commands. Do not silently widen an audit or create a separate policy authority.
