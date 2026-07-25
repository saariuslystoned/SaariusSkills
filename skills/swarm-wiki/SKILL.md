---
name: swarm-wiki
description: Maintain the SWARM knowledge wiki that the phone-side notebook reads. Use when ingesting a source into the wiki, filing a notebook answer back, appending to the run log, linting the corpus, or when the user asks what the swarm did, mentions the SWARM notebook, the SWARM Drive folder, or invokes $swarm-wiki. Not for reading a repo's own docs.
license: MIT
---

# SWARM Wiki

Keep a compiled body of knowledge that a phone can ask questions of, and keep it
honest. This skill instructs **our** agents. It does not configure Gemini.

## Activate naturally

Activate when the user asks to record what happened, ingest an article or proof
packet into the wiki, file a notebook answer back, append a run entry, lint the
corpus, or asks what the swarm has been doing. Accept `$swarm-wiki` explicitly.

Do not activate for ordinary repo documentation, for a passing mention of the
notebook, or for questions about how the skill works.

## The one rule

**The notebook sources the wiki. The notebook never sources raw material.**

A notebook pointed at raw sources rediscovers everything from scratch on every
question and never accumulates. Pointed at a compiled synthesis, it reads
something that got better over time. Everything below follows from that.

So: **compile first.** If an entry could be replaced by a link, it is not
compiled yet. Never add a raw article, transcript or proof packet as a notebook
source.

## Where things live

| Artifact | Home | Role |
|---|---|---|
| Wiki pages, log, schema | this repo (source of truth) | versioned, reviewable |
| `SWARM Wiki` (Doc) | `My Drive/SWARM/` | what the notebook reads |
| `SWARM Run Log` (Sheet) | `My Drive/SWARM/` | structured per-run rows |
| `SWARM Briefing` (Slides) | `My Drive/SWARM/` | human-facing visual state |

The repo is authoritative. Drive is a **surface**, published to. Never treat a
Drive edit as the record — it can be overwritten by the next publish.

Full layout, ids and publish commands: [references/layout.md](references/layout.md).

## Workflows

### Ingest

1. Read the raw source.
2. Write the **synthesis** into the relevant wiki page — what it means here, not
   what it said. Cite the source; do not paste it.
3. Append a log line: `## [YYYY-MM-DD] ingest | <Title>`
4. Publish to Drive (see references/drive-cli.md).
5. Do **not** add the raw source to the notebook.

### Query

1. Ask the notebook (see references/notebook.md — **use the NotebookLM app**).
2. Check the answer against the wiki. This notebook is **not source-locked**: it
   answers past its sources from general knowledge, fluently. **An answer that
   cites nothing is a hypothesis, not a fact.**
3. If the answer is worth keeping, file it back.

### Answer write-back

1. Append the answer to the wiki as a page, with the question that produced it.
2. Log it: `## [YYYY-MM-DD] answer | <question>`

An answer that is not filed back is **lost**, not "in chat history". Google's
own auto-filing does not count — see the poisoning warning in
[references/notebook.md](references/notebook.md).

### Lint

Run the checker, then fix what it reports:

```bash
python3 scripts/swarm_log.py lint <wiki-dir>
```

It flags relative dates, uncompiled link-only entries, malformed log lines,
duplicate page headings, a missing vocabulary page, and missing canaries.

Close with: `## [YYYY-MM-DD] lint | <what changed>`

### Log append

```bash
python3 scripts/swarm_log.py append <log.md> ingest "Article Title"
```

Format, adopted verbatim so the tail stays greppable:

```
## [2026-04-02] ingest | Article Title
```

```bash
grep "^## \[" log.md | tail -5
```

Verbs: `ingest`, `answer`, `lint`, `run`. Dates are absolute `YYYY-MM-DD` —
never relative. This corpus is read months later and relative dates rot silently.

## The vocabulary page is mandatory

**Notebook chats do not inherit the Gemini account's global custom instruction.**
Proven on the Pixel 9 Pro, 2026-07-25: asked about `w1:pV`, a notebook chat
reproduced the exact pre-instruction error the instruction was written to fix,
calling it a Kubernetes *"worker node"*.

Combined with not being source-locked, the failure mode is not "the notebook
cannot answer swarm questions" — it is **"the notebook answers them confidently
and wrongly."**

So the vocabulary arrives the way everything else does: **as a page in the
wiki**, versioned and repo-owned, with no Gemini-side configuration that can
drift or vanish on an account change.

**If the vocabulary page is missing, the notebook is unsafe to trust.** The
linter treats its absence as an error, not a warning.

## Canaries: never assume a source is fresh

Each published Drive artifact carries a line:

```
RESYNC-CANARY-<TYPE>: <COLOUR>
```

Drive sources **do** re-sync — verified 2026-07-25 across Doc, Sheet and Slides
by editing each and re-asking without re-adding. That is why the design works at
all, and the canaries are how it stays verifiable rather than assumed.

Re-check after any change to how publishing works. Leave the canaries in place.

## Hard rules

- **Never** add a raw source to the notebook. Compile first.
- **Never** let a notebook answer stay only in chat.
- **Never** use relative dates.
- **Never** trust an uncited notebook answer.
- **Never** drive the Gemini UI to maintain this. Agents write files; brittle UI
  automation against an app Google redesigns breaks silently.
- **Never** put secrets, tokens, `.env` contents, keys or credential material in
  the wiki. Drive is Google-hosted and sits outside the repo trust boundary.

## References

- [references/layout.md](references/layout.md) — artifacts, ids, what each is for
- [references/log-format.md](references/log-format.md) — the log contract
- [references/notebook.md](references/notebook.md) — the two query routes and their traps
- [references/drive-cli.md](references/drive-cli.md) — publishing via rclone
