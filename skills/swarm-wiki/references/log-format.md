# The log contract

One line per event, consistent prefix so the tail is greppable:

```
## [2026-04-02] ingest | Article Title
```

```bash
grep "^## \[" log.md | tail -5
```

That grep is the reason for the format. Anything that breaks it — a heading
level change, a missing bracket, a prose date — silently removes the entry from
every future tail, which is worse than not logging it.

## Verbs

| Verb | Means |
|---|---|
| `ingest` | A raw source was compiled into a wiki page |
| `answer` | A notebook answer was filed back as a page |
| `lint` | A maintenance pass changed the corpus |
| `run` | Swarm work was recorded |

## Dates

Absolute `YYYY-MM-DD`. Never "yesterday", "last week", "recently". This corpus is
read months later, and relative dates rot without any signal that they have.

## Publishing keeps the literal prefix

Google Docs auto-formats typed markdown — it will consume a leading `#` and
convert the line to a real heading, destroying the greppable prefix. **Publish by
paste or by rclone import, never by typing**, and keep the markdown literal in
the Drive copy. Detail in [drive-cli.md](drive-cli.md).
