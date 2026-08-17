# Live browser acceptance suite

This protocol verifies the browser skill against
`fixtures/verification_studio.html`. It is a manual agent-driven acceptance run,
not something the bundled Python checker performs.

## Preflight

1. Run the static fixture check:

   ```bash
   python3 skills/browser/scripts/verify_browser.py --json
   ```

   A pass means only that required fixture elements and JavaScript hooks exist.

2. Serve the skill directory from a separate terminal:

   ```bash
   python3 -m http.server 8765 --directory skills/browser
   ```

3. In AGY CLI, invoke:

   ```text
   /browser Open http://127.0.0.1:8765/fixtures/verification_studio.html and run the live acceptance suite described in the browser skill. Save a full-page screenshot.
   ```

   Run this in the interactive TUI. The operator must make the normal workspace
   trust decision and approve the scoped `mcp(chrome-devtools/...)` request when
   prompted. Do not use `--dangerously-skip-permissions` to turn an unapproved
   headless run into a pass.

## Live checks

Use a fresh snapshot before each group and verify state after each mutation.

| Category | Action | Terminal assertion |
| --- | --- | --- |
| Text inputs | Fill codename, email, and directives with unique test values. | The three DOM values exactly match. |
| Form controls | Change the paradigm, one theme radio, and at least one capability checkbox. | `value` and `checked` state match the request. |
| Click | Click **Apply Directives**. | HUD name, channel, paradigm, and directives show the new values. |
| Drag and drop | Drag the security key to the authorization zone. | Zone contains `TOKEN_779 ACCEPTED`. |
| Canvas | Click **Draw Starburst** and **Cyber Spiral**. | `#stroke-count` increases from its pre-click value. |
| Visual proof | Take a full-page screenshot after all checks. | Screenshot exists and visibly contains the terminal fixture state. |

## Required report

Record the AGY version, plugin revision, final URL, exact pass/fail status for all
six categories, post-action assertions, and screenshot path. A setup failure is a
blocked run, not a capability pass. Do not describe static fixture inspection as a
live browser verification.
