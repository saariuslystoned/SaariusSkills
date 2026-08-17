---
name: browser
description: Dispatches a dedicated browser subagent to execute autonomous web browsing, interactive UI automation, visual verification, and page inspection using Chrome DevTools MCP.
license: MIT
---

# Browser Subagent & Automation Skill

The `/browser` skill enables autonomous, high-fidelity browser control and web inspection inside the Google Antigravity ecosystem (including the Antigravity App and `agy` CLI).

## Direct Subagent Invocation Directive

When invoked in the `agy` CLI (via `/browser <task>` or explicit browser requests):

1. **Invoke the Subagent**: Dispatch the dedicated `browser` subagent via `invoke_subagent`:
   ```json
   {
     "TypeName": "browser",
     "Role": "Browser Automation Specialist",
     "Prompt": "<user-provided browser objective and tasks>"
   }
   ```
2. **Subagent Execution Isolation**: The subagent runs inside its own isolated context, executing browser actions with the `chrome_devtools` MCP toolset.
3. **Telemetry & Proof Verification**: The subagent collects DOM state, executes interactions, takes screenshots (`take_screenshot`), and reports sanitized findings back to the parent agent.

---

## Tool Protocol & Workflow Lifecycle

Interactions follow the standard DevTools MCP workflow:

```text
Connect / Navigate -> Snapshot (UIDs) -> Interact (Fill / Click / Drag) -> Script / Draw -> Screenshot Proof
```

### 1. Connection & Navigation
- Check open pages: `list_pages`
- Open or navigate: `new_page(url: "...")` or `navigate_page(url: "...")`
- Adjust viewport if needed: `resize_page(width: 1400, height: 950)`

### 2. Semantic Snapshot & Element Targeting
- Query interactive elements: `take_snapshot`
- Extract unique element `uid` tags for deterministic targeting.

### 3. Core Interaction Suite
- **Typing**: `fill_form(elements: [...])` or `type_text(uid: "...", text: "...")`
- **Checkboxes & Radios**: `click(uid: "...")` or `fill_form`
- **Buttons & Clicks**: `click(uid: "...")`
- **Drag & Drop**: `drag(from_uid: "...", to_uid: "...")` or coordinate drag
- **Dynamic Scripting & Canvas**: `evaluate_script(function: "() => ...")`
- **Proof Capture**: `take_screenshot(fullPage: true)`

---

## Authoritative Verification Suite

To verify browser automation capabilities end-to-end, execute the verification script:

```bash
python3 <skill-root>/scripts/verify_browser.py
```

The verification suite evaluates six core interaction categories against the built-in [fixtures/verification_studio.html](fixtures/verification_studio.html):
1. **Text Typing**: Populates form text, emails, and multiline inputs.
2. **Checkboxes & Radios**: Toggles theme options, capability flags, and dropdown selections.
3. **Button Clicks**: Triggers HUD state synchronization and brush mode toggles.
4. **Drag & Drop**: Drags cryptographic tokens into security drop zones.
5. **Vector Canvas Drawing**: Renders multi-layer vector starbursts, spirals, and resonance graphs.
6. **Proof Capture**: Takes full-page screenshots and validates telemetry event logs.

See [references/protocol.md](references/protocol.md) and [references/verification_suite.md](references/verification_suite.md) for protocol details.
