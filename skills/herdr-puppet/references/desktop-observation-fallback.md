# Desktop observation fallback

Use Peekaboo as a bounded fallback when Computer Use reports
`cgWindowNotFound`, `timeoutReached`, or another app-window resolution failure
for a Screen Sharing or VNC window that the operator says is visible. This
fallback restores observation and harmless wake/focus control only. It does
not replace the Herdr lease, transport controller, Pixel Use MCP, or any
action-specific human gate.

## Classify before acting

Distinguish these states with fresh visual evidence:

1. the CP-1 display is showing a screen saver;
2. the Screen Sharing window exists but control input is disabled;
3. the remote host display is asleep;
4. the remote host is at an authentication screen; or
5. the remote desktop is already visible and only the window title says
   `Locked`.

Do not infer that VNC is offline from a Computer Use resolution error. Do not
infer an authentication gate from the Screen Sharing title alone when the
remote desktop is visibly rendered.

## Recover observation

1. Confirm Peekaboo is installed, then inspect its own permission report:

   ```bash
   command -v peekaboo
   peekaboo permissions --json
   ```

   Require Screen Recording and Accessibility. A configured CP-1 Peekaboo
   bridge is an acceptable capture surface; record its reported source without
   exposing socket paths or host credentials.

2. Capture before sending input:

   ```bash
   peekaboo image --mode screen --screen-index 0 \
     --format png --path <private-proof-path>
   ```

   Keep raw captures private when they contain phone numbers, messages,
   accounts, notifications, or other operator data. Publish only sanitized
   evidence.

3. Resolve the exact Screen Sharing window structurally:

   ```bash
   peekaboo list windows --app "Screen Sharing" --json \
     --include-details bounds,ids
   peekaboo see --app "Screen Sharing" \
     --window-title <exact-worker-label> --json
   ```

   Re-derive the current window ID and element IDs after every observation.
   Never reuse an ID from an older snapshot or select a window by ordinal
   alone.

4. If the exact window exposes `Control Screen` and control is off, use the
   current `see` snapshot's labeled element to enable it. Then send one harmless
   wake input to the exact current window:

   ```bash
   peekaboo click --on <current-control-screen-element> \
     --snapshot <current-snapshot-id>
   peekaboo press space --window-id <current-window-id> --no-auto-focus
   ```

   Do not type text, submit a composer, or send a phone action as a wake probe.

5. If the target becomes off-screen or reports negative bounds, restore only
   that exact window and capture again:

   ```bash
   peekaboo window maximize --window-id <current-window-id>
   peekaboo image --mode screen --screen-index 0 \
     --format png --path <private-proof-path>
   ```

Stop when the expected remote desktop is visibly rendered. Do not keep sending
wake inputs after success.

## Preserve the gates

- Never enter or retrieve a password, token, or other credential through this
  fallback. Hand authentication back to the operator.
- Apply the active Computer Use confirmation policy to every consequential UI
  action.
- Use Pixel Use MCP for phone semantics and mutations. Peekaboo/Vysor may
  provide visual proof, not a bypass around registered-device policy.
- Do not use Peekaboo to read arbitrary terminal transcripts, bypass the
  Herdr lease, adopt an unowned tab, or infer harness completion.
- Record the fallback reason, exact non-secret window identity, bounded action
  class, and sanitized before/after result in the run journal or proof packet.
