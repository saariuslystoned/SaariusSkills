# Layout: where the corpus lives

## Source of truth: this repo

Wiki pages, the log, and this schema are versioned here. Reviewable, diffable,
and visible to every agent. **The repo is authoritative.**

## Surface: `My Drive/SWARM/`

Folder id `1LYXfp3hJY9-VRdqnbx28hhwN5EAiSoBh`. Published to, not edited by hand.
A Drive edit is not the record — the next publish overwrites it.

| File | Type | Role | Canary |
|---|---|---|---|
| `AGENTS.md` | Doc | The schema, mirrored for readers who land in Drive | -- |
| `README.md` | Doc | Human landing page | -- |
| `SWARM Wiki` | Doc | Compiled synthesis. **What the notebook reads.** Carries the Vocabulary page. | `RESYNC-CANARY-DOC` |
| `SWARM Run Log` | Sheet | `date, agent, host, session, task, status, proof, notes` | `RESYNC-CANARY-SHEET` |
| `SWARM Briefing` | Slides | Human-facing visual state | `RESYNC-CANARY-SLIDE` |

## Why three native types rather than one file

They answer different questions and degrade differently:

- **Doc** — prose synthesis. What happened and what it means. The thing you *ask*.
- **Sheet** — structured rows. What ran, where, whether it passed. The thing you *filter*.
- **Slides** — visual state. The thing a human *glances at* without reading.

NotebookLM reads all three, verified. Slides is the only one carrying
visualisation for humans rather than text for a model — and because the deck is
generated from source (`pptxgenjs`) rather than hand-built, it stays an
agent-maintainable artifact instead of something only one person can update.

## Wiki page conventions

One `# Page: <Name>` heading per page. Pages are synthesis, not storage:

- No link-only entries. A URL with a sentence around it is not compiled.
- No relative dates. Absolute `YYYY-MM-DD` only.
- Merge duplicates rather than accumulating near-identical pages.

### Mandatory pages

- **`# Page: Vocabulary`** — the terms the assistant gets wrong, each paired with
  the observed failure and the correct reading. Its absence is a lint **error**:
  without it the notebook confabulates swarm state confidently.
