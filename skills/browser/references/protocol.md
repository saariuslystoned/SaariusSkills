# Browser Control & DevTools MCP Protocol

This document defines the architecture, transport bindings, and tool specifications for the `/browser` subagent and skill.

## 1. Chrome DevTools MCP Integration

The skill communicates with Google Chrome via the Model Context Protocol (MCP) using `chrome-devtools-mcp`.

### Configuration (`~/.gemini/antigravity/mcp_config.json` or `.mcp.json`)

```json
{
  "mcpServers": {
    "chrome_devtools": {
      "command": "npx",
      "args": [
        "-y",
        "chrome-devtools-mcp@latest",
        "--browserUrl",
        "http://localhost:9222"
      ]
    }
  }
}
```

### Launching Chrome with Debug Port on macOS

```bash
open -na "Google Chrome" --args --remote-debugging-port=9222 --user-data-dir=/tmp/chrome-debug-profile
```

---

## 2. MCP Tool Specifications

| Tool | Parameters | Description |
| :--- | :--- | :--- |
| `list_pages` | `{}` | Lists all open browser tabs and active session indicators. |
| `new_page` | `{ url: string, background?: boolean }` | Opens a new page and loads the target URL. |
| `navigate_page` | `{ url: string }` | Navigates the currently selected tab to a URL. |
| `select_page` | `{ pageIdx: number }` | Switches active focus to a specific tab index. |
| `resize_page` | `{ width: number, height: number }` | Sets the browser viewport dimensions. |
| `take_snapshot` | `{ verbose?: boolean }` | Extracts accessibility DOM tree with deterministic element `uid`s. |
| `click` | `{ uid: string, button?: string }` | Clicks an element identified by its snapshot `uid`. |
| `hover` | `{ uid: string }` | Hovers over an element identified by its snapshot `uid`. |
| `type_text` | `{ uid: string, text: string }` | Types text into an element. |
| `fill_form` | `{ elements: Array<{ uid: string, value: string }> }` | Fills multiple form inputs in a single batch operation. |
| `drag` | `{ from_uid: string, to_uid: string }` | Drags an element to a target element or drop zone. |
| `press_key` | `{ key: string }` | Synthesizes keyboard key events (e.g. `Enter`, `Tab`, `Escape`). |
| `evaluate_script` | `{ function: string, args?: string[] }` | Executes JavaScript within the page context and returns serializable JSON. |
| `take_screenshot` | `{ fullPage?: boolean, format?: string }` | Captures a high-resolution screenshot of the viewport or entire page. |

---

## 3. Subagent Dispatch Protocol

When the user issues a request using `/browser <prompt>`:
1. The parent agent receives the command and immediately delegates to the `browser` subagent via `invoke_subagent`.
2. The `browser` subagent initiates the tool sequence, maintaining state across DOM changes.
3. The subagent returns structured evidence (including telemetry, DOM state changes, and screenshot citations) to the parent conversation.
