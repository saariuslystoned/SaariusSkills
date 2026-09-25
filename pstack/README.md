# pstack (Saarius Edition)

Cherry-pick of Lauren Tan's pstack engineering skills, plus Saarius overlays.

**Upstream:** [`cursor/plugins` `pstack/skills`](https://github.com/cursor/plugins/tree/main/pstack/skills)
**Pinned at:** `fadd23794c0075468eb8964b0fd93e06e09486ad` (2026-09-25 sparse clone of `cursor/plugins` `main`)

`backnotprop/pstack` is a third-party any-harness mirror, not this overlay's source.

## Skills Included

Synced from Cursor (this pin):

| Skill | Description |
| :--- | :--- |
| **`unslop`** | Strips AI conversational filler, sycophancy, hedging, and defensive bloat; enforces surgical diffs. |
| **`blast-radius`** | Analyzes downstream callers and dependencies before modifying interfaces. |
| **`architect`** | Type and interface design contract before code generation. |
| **`how`** | Traces runtime execution paths and control flow. |
| **`why`** | Explores commit history and historical architectural rationale. |
| **`tdd`** | Enforces red-green-refactor with verified test failure proof first. |
| **`create-verification-skill`** | Generates a project-local verification skill that drives the real app. |
| **`maintain-verification-skill`** | Upkeep loop when the app, harness, or feature map drifts. |
| **`reflect`** | Post-task retrospective analyzer mining transcript friction. |
| **`automate-me`** | Drafts or revises a personal `-mode` skill from operator evidence. |

Saarius overlays (not in Cursor pstack):

| Skill | Description |
| :--- | :--- |
| **`pstack-playbooks`** | Standard task runbooks (bug-fix, feature, refactor, hillclimb, forensics). |
| **`bobby-mode`** | Active behavioral profile enforcing Voice-to-Text brevity and Swarm proof policy. |

The rest of upstream pstack (`poteto-mode`, `principle-*`, `arena`, `swarm`, and others) is intentionally not vendored here.

## OpenClaw

Do not copy these into Skill Workshop. Workshop is for skills this agent authors under `workshop-skills`. This stash is a sibling repo.

On the bobby Gateway, load the symlink farm so every agent on the profile sees them:

```json5
{
  skills: {
    load: {
      extraDirs: ["~/Developer/repos/saariuslystoned/SaariusSkills/skills"],
      allowSymlinkTargets: ["~/Developer/repos/saariuslystoned/SaariusSkills/pstack/skills"],
      watch: true
    }
  }
}
```

Then `openclaw --profile bobby skills list` and `openclaw --profile bobby skills check`. Existing chats keep the old snapshot until `/new`.

Cursor-only primitives in the synced skills (`.cursor/skills`, `AskQuestion`, `/add-plugin`) stay as upstream wrote them. DinkusKit still proves with repo `FEATURE_MAP.md` plus `bin/verify-*`.

## Installation on SmOmarchy / ChatGPT App

1. In ChatGPT / Codex desktop app on SmOmarchy:
   - Point your plugin directory to `/path/to/SaariusSkills/pstack` (or install via `.codex-plugin/plugin.json`).
2. Skills will be automatically registered and namespaced for your sessions.
