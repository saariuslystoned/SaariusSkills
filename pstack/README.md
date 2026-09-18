# pstack (Saarius Edition)

Structured engineering workflows, verification loops, anti-slop rules, and operator profiling for ChatGPT / Codex app and Antigravity (AGY).

## Skills Included

| Skill | Description |
| :--- | :--- |
| **`unslop`** | Strips AI conversational filler, sycophancy, hedging, and defensive bloat; enforces surgical diffs. |
| **`blast-radius`** | Analyzes downstream callers and dependencies before modifying interfaces. |
| **`architect`** | Type and interface design contract before code generation. |
| **`how`** | Traces runtime execution paths and control flow. |
| **`why`** | Explores commit history and historical architectural rationale. |
| **`tdd`** | Enforces red-green-refactor with verified test failure proof first. |
| **`create-verification-skill`** | Scaffolds automated `bin/verify-*` test harnesses. |
| **`maintain-verification-skill`** | Upkeep loop to update test harnesses when code drifts. |
| **`reflect`** | Post-task retrospective analyzer mining transcript friction. |
| **`pstack-playbooks`** | Standard task runbooks (bug-fix, feature, refactor, hillclimb, forensics). |
| **`automate-me`** | Mines local and remote transcripts to synthesize operator habits. |
| **`bobby-mode`** | Active behavioral profile enforcing Voice-to-Text brevity and Swarm proof policy. |

## Installation on SmOmarchy / ChatGPT App

Add the repository marketplace, then install the pstack plugin:

```bash
codex plugin marketplace add saariuslystoned/SaariusSkills
codex plugin add pstack-saarius@saarius-skills
```

Start a new ChatGPT or Codex task after installation so the namespaced skills
are loaded into the session.

For Antigravity, install the repository root. Its compatibility aliases expose
the same pstack skills while Codex uses the standalone physical package:

```bash
agy plugin install /path/to/SaariusSkills
```
