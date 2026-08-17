# AGY CLI and Chrome DevTools MCP protocol

## Packaged setup

Antigravity CLI plugins can package skills, subagents, and MCP servers. This
repository therefore ships all three pieces:

- `skills/browser/SKILL.md` registers `/browser`.
- `agents/browser-cli/agent.md` defines the delegated subagent.
- `mcp_config.json` registers the `chrome-devtools` MCP server.

The server starts visible Chrome with a temporary isolated profile. The profile is
removed when the browser closes, so it is intentionally not signed in and does not
reuse a person's cookies.

Prerequisites are a current stable Chrome, Node.js LTS, npm/npx, and a current AGY
CLI. Install the plugin and restart the CLI:

```bash
agy plugin install /path/to/SaariusSkills
```

Use `agy plugin list` and `/mcp` to diagnose discovery. If startup fails, surface
the error; do not silently fall back to shell scraping or a personal Chrome profile.

## Existing browser opt-in

The packaged default is isolated. Connecting to an existing Chrome session exposes
that session's pages, cookies, and logged-in accounts to the agent. Only configure
this mode when the user explicitly wants it and understands that consequence.

For Chrome 144+, enable Remote Debugging at
`chrome://inspect/#remote-debugging`, then replace the MCP arguments with:

```json
["-y", "chrome-devtools-mcp@latest", "--autoConnect"]
```

Chrome presents its own connection approval dialog. A manual debug-port setup can
instead use `--browser-url=http://127.0.0.1:9222` with a dedicated user-data
directory. That is an operator customization, not this plugin's default.

## Exact tool arguments

These names and parameters follow the current `chrome-devtools-mcp` tool reference.

| Tool | Core arguments | Purpose |
| --- | --- | --- |
| `list_pages` | `{}` | List open pages and their numeric IDs. |
| `new_page` | `{"url":"https://example.com"}` | Open a URL in a new page. |
| `navigate_page` | `{"type":"url","url":"https://example.com"}` | Navigate the selected page. |
| `select_page` | `{"pageId":1,"bringToFront":true}` | Select a page returned by `list_pages`. |
| `take_snapshot` | `{}` | Read the current accessibility tree and fresh UIDs. |
| `fill` | `{"uid":"...","value":"..."}` | Fill one input, textarea, select, toggle, or radio. |
| `fill_form` | `{"elements":[{"uid":"...","value":"..."}]}` | Fill several form controls together. |
| `type_text` | `{"text":"...","submitKey":"Enter"}` | Type into an input that is already focused. |
| `click` | `{"uid":"..."}` | Click an element from the latest snapshot. |
| `drag` | `{"from_uid":"...","to_uid":"..."}` | Drag one snapshotted element onto another. |
| `press_key` | `{"key":"Enter"}` | Send a key or shortcut. |
| `evaluate_script` | `{"function":"() => document.title"}` | Read or manipulate narrowly scoped page state. |
| `take_screenshot` | `{"fullPage":true,"filePath":"proof.png"}` | Save visual proof. |

`pageIdx` is pagination for some list tools; it is not the selector argument for
`select_page`. UIDs expire when the page changes, so take a new snapshot after
navigation, submission, dialogs, or dynamic re-rendering.

## Dispatch and result contract

The parent sends one `invoke_subagent` request whose `Subagents` array contains a
`browser-cli` spec and `Workspace: "inherit"`. The subagent returns:

- final URL and page identity;
- relevant actions, without secrets or private form values;
- post-action DOM or script assertions;
- screenshot/artifact paths when requested;
- explicit blockers or unverified claims.

A screenshot is evidence of appearance, not proof that hidden state or a network
request succeeded. Use the matching DOM, console, or network evidence for that
claim.
