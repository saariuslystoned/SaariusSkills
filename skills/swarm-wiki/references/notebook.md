# The notebook: how to query it, and what it gets wrong

The SWARM notebook is **NotebookLM**, source-grounded, sourcing the SWARM Drive
folder. Findings below were established on the Pixel 9 Pro, 2026-07-25.

## Two routes. They are not equivalent.

### Route A — the NotebookLM app (use this)

Package `com.google.android.apps.labs.language.tailwind`.

Opens straight into the notebook. Tabs: **Sources / Chat / Studio**. The chat
input reports how many sources are attached (`Ask N sources…`) and answers carry
citation markers.

This is the reliable route and the only one to use for anything that will be
recorded as evidence.

> Package-name trap: the app cannot be found by grepping for `notebook`. Gemini
> likewise ships as `com.google.android.apps.bard`. **Enumerate
> `com.google.android.apps.*` and read the list** rather than grepping for the
> product name you expect.

### Route B — the Gemini app (fails silently)

Package `com.google.android.apps.bard`.

The notebook must be **attached to the conversation**: `+` in the chat bar,
scroll right, choose **Notebooks**. Miss that step and you are talking to plain
Gemini, which will answer *as if* it were notebook-aware.

Observed: an identical canary question returned

> I do not have the values for RESYNC-CANARY-DOC, RESYNC-CANARY-SHEET, or
> RESYNC-CANARY-SLIDE.

That looked like an indexing failure. It was the notebook simply not being
attached. **A plausible wrong answer, with no error.** Prefer Route A.

## Three properties that will bite you

### 1. It is not source-locked

It answers questions its sources do not cover, fluently, from general knowledge.
**An uncited answer is a hypothesis.** Check it against the wiki before acting on
it or filing it back.

### 2. It does not inherit the global custom instruction

The account-level custom instruction fires on the power-press assistant overlay
and in ordinary Gemini chats. It does **not** reach notebook chats.

Asked `Is w1:pV a host name or something else`, a notebook chat answered from
generic networking knowledge — RFC 1123 character rules, colons as port
separators — and then guessed:

> **Kubernetes or Cloud Orchestration:** it is incredibly common to see `w1` used
> as a shorthand designation for "Worker 1" (a worker node in a cluster) and `pv`
> used as the standard abbreviation for "Persistent Volume".

That is verbatim the confabulation the custom instruction was written to prevent.
Hence: **vocabulary lives in the wiki as a page**, not in Gemini's settings.

### 3. Gemini-app chats are auto-filed back as sources

The Sources tab carries a collapsed group, **"Chats from Gemini (N)"**, which
counts toward the source total — a notebook with four files reported *"Ask 6
sources"*.

This is not the write-back you want. **A confabulated chat answer becomes a
citable source in the notebook whose vocabulary page exists to prevent that
error.** Left alone, the notebook cites its own past mistakes back at itself.

**Curate it.** In the Chat tab, tap the source chip (`Selected sources: N. Tap to
change`) and deselect chat entries so the notebook grounds only on compiled,
versioned material. Deselecting is non-destructive and reversible; the menu's
`Delete chat history` is all-or-nothing and destroys data — prefer deselection,
and never delete a user's chat history without them asking for it explicitly.

> Selection state is **not** implied by what the notebook answered a moment ago.
> Open the sheet and read the checkboxes before assuming anything is attached.

## Adding a source

Sources tab → `Add a source` → **Google Drive**.

The picker is **single-select** (radio buttons, not checkboxes) — one file per
pass, so adding three files means three trips through the picker.

Mobile source types are Camera / Gallery / Files / Google Drive. There is **no
URL option on the phone**; that exists only on NotebookLM web.

## Re-sync is real

Editing a Drive-sourced file and re-asking **without re-adding** returns the new
value. Verified across Doc, Sheet and Slides simultaneously by flipping a canary
colour and re-asking. Sources are live, not snapshots taken at add time.

When verifying this again, control for three things or the test is worthless:

1. **File identity** — confirm the Drive file id is unchanged after the edit. A
   new id means the notebook still points at the old file, and the test will
   appear to work while proving nothing.
2. **Server-side content** — read the edited value back *out of Drive*, not from
   your local copy.
3. **Conversation bias** — an existing thread containing the old answer biases
   toward the stale value, so a fresh value despite it is a strong result; a
   stale value in that situation is ambiguous, not a verdict.

## Automation notes

- `uiautomator` switches the `text` attribute delimiter from `"` to `'` when the
  value contains a double quote. An extractor matching only `text="[^"]*"`
  returns **nothing** for exactly the answers that quote something, making a
  fully-rendered response look empty. Accept both delimiters.
- Values are HTML-escaped (`&#10;` for newlines) and Gemini emits zero-width
  spaces (`U+200B`) between list items. Unescape and strip before matching.
- In the Gemini overlay, `KEYCODE_ENTER` **inserts a newline, it does not
  submit** — tap the Send button, which only exists once the input is non-empty.
- Input surfaces reflow on focus, and the notebook input is a half sheet that
  **collapses and discards typed text** if anything stalls. Re-read bounds after
  focusing, and keep tap → type → send in one uninterrupted sequence.
