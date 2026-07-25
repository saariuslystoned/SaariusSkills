# Publishing to Drive

**Use rclone. Do not drive the Google editors through a browser.**

The remote is `gdrive:` and works on a consumer `@gmail.com` account — the
Drive/Docs/Sheets/Slides APIs are not Workspace-only. There are also no native
macOS Docs/Sheets/Slides apps; Drive for Desktop only syncs, and `.gdoc` files
are pointers rather than content.

## Publish

```bash
rclone copy wiki.md            gdrive:SWARM/ --drive-import-formats md   --drive-export-formats md
rclone copy "SWARM Run Log.csv" gdrive:SWARM/ --drive-import-formats csv  --drive-export-formats csv
rclone copy "SWARM Briefing.pptx" gdrive:SWARM/ --drive-import-formats pptx --drive-export-formats pptx
```

Mapping: `md`/`txt` → Doc, `csv` → Sheet, `pptx` → Slides.

**Both formats must be set.** Import alone fails with
`can't convert ".csv" to a document with a different export filetype (".xlsx")`.

Re-uploading the same filename **updates in place and preserves the Drive file
id**, which is what keeps existing notebook sources pointed at the same object.
Verify with `rclone lsjson gdrive:SWARM` before and after if it matters.

## Read back / verify

```bash
rclone cat "gdrive:SWARM/SWARM Wiki.txt"      --drive-export-formats txt
rclone cat "gdrive:SWARM/SWARM Run Log.csv"   --drive-export-formats csv
```

Verify server-side, not from the local copy, whenever the answer depends on what
Drive actually holds.

## Two traps

1. **Files created in the browser are not rclone-maintainable.** There is no
   local filename for rclone to match, so they must be edited by hand forever.
   **Create every artifact through rclone from the start.**
2. **The system clipboard is shared with the human at the keyboard.** Clipboard-
   driven publishing races them — an unrelated URL copied mid-run has landed
   inside a published doc. Prefer rclone; if pasting is unavoidable, verify the
   result immediately.

Keep generated Drive content **ASCII-only**: non-ASCII is mangled through the
clipboard path (`—` → `,Äî`, `→` → `,Üí`).

## Note

rclone warns that its shared Google client_id **retires during 2026**. A private
client_id is needed before this becomes load-bearing. It would also permit
`files.create` with an explicit `mimeType`, which is the missing piece for
writing Gems (`application/vnd.google-gemini.gem`) — rclone alone uploads them as
`application/octet-stream` and Gemini ignores the result.
