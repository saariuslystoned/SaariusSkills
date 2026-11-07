# Block Kit Visual Composition & Kumo Mapping

Upstream `@emdash-cms/blocks` renders declarative JSON blocks through `@cloudflare/kumo` components. Understanding the exact DOM and Tailwind classes each block emits prevents flat, unstyled admin screens.

## 1. Exact Block-to-Kumo Component Mapping

| Block / Element Type | Rendered Kumo / DOM Structure | Visual Role & Best Practice |
| --- | --- | --- |
| `stats` | `<div class="flex gap-4">` of `<div class="flex-1 rounded-lg border border-kumo-line p-4">` cards with `text-2xl font-bold` value + `trend` icon + `description` | **Primary bordered card primitive in Block Kit.** Use a 3-card `stats` row at the top of every admin page to frame status, active model/service, and queue counts. |
| `columns` | `grid grid-cols-2 gap-4` (2 cols) or `grid grid-cols-3 gap-4` (3 cols) | **Mandatory container for forms and onboarding splits.** Keeps forms at a readable ~50% width alongside instructions or live status. |
| `tab` | `<Tabs variant="underline">` + `<div class="pt-4">` panel renderer | **Primary workspace organizer.** Separate `Assistant / Action`, `Approval Queue`, and `Settings / Collections` into tabs instead of stacking vertically. |
| `empty` | `<Empty icon={<Package size={48} weight="duotone" />} title description commandLine size contents={actions} />` | **Hero onboarding & zero-state card.** Use `size: "base"` or `"lg"` with `actions` for 1-Click Cloudflare deploys or empty queues. |
| `table` | Kumo table with column `format`: `"badge"` (`<Badge>`), `"code"` (`<code class="rounded bg-kumo-tint px-1.5 py-0.5 font-mono text-sm">`), `"relative_time"`, `"number"`, or `"element"` | **Best primitive for 3-step setup checklists** (`Step` badge \| `Surface` \| `Action` code pill) and structured records. |
| `code` | `<CodeBlock code lang />` (`"bash" \| "ts" \| "tsx" \| "jsonc" \| "css"`) | Use for copy-paste agent pairing prompts (`npx` + `curl` fallback) and CLI snippets. |
| `accordion` | `<Collapsible.Root>` + `<Collapsible.DefaultTrigger>` | Use to tuck away **Advanced / Manual Fallback** forms when an agent-assisted or 1-click flow is primary. |
| `fields` | `grid grid-cols-2 gap-x-6 gap-y-3` with `text-kumo-default truncate` on values | **Short metadata only** (URLs, IDs, timestamps). Never put multi-sentence instructions in `fields`—values truncate with an ellipsis (`...`). |
| `secret_input` | `<SensitiveInput>` (`••••••••` read-only mask when `has_value: true`, reveal/edit on focus) | Always use for bearer tokens, API keys, and webhook secrets instead of `text_input`. |
| `checkbox` | `<Checkbox.Group legend={label}>` with `<Checkbox.Item>` children | Always use for multi-collection or multi-feature enablement instead of repeating `toggle` switches. |

---

## 2. Canonical Onboarding Blueprint (2-Column Split)

When a plugin is unconfigured (`!connection`), structure `setupPage()` as:

1. `header("<Plugin Name>")`
2. Conditional `banner("error", ...)` **only** when form validation failed.
3. 3-item `stats` bar (`Connection Status`, `Runtime / Architecture`, `Safety Posture`).
4. 2-column `columns` block:
   - **Column 1 (Guided Action):** Either an `empty` card with a primary `link` button (`1-Click Deploy to Cloudflare`) or a `code` block with the copy-paste agent pairing prompt, paired with a 3-row `table` (`badge` steps + `code` values).
   - **Column 2 (Configuration Form):** `form` with `text_input` (endpoint), `select` (model/posture), `checkbox` (enabled collections), and `secret_input` (optional/required token).

---

## 3. Canonical Connected Workspace Blueprint (`tab` + `stats`)

When connected, structure `workspacePage()` as:

1. `header("<Plugin Name>")`
2. 3-item `stats` bar (`Active Agent / Model`, `Endpoint / Task Status`, `Approval Queue`).
3. `tab` block with 3 panels:
   - **Tab 0 (`Assistant & Live Steer`):** 2-column `columns` split with the multiline prompt `form` on the left and active turn steer / latest reply / `empty` ready state on the right.
   - **Tab 1 (`Approval Queue (<n>)`):** `empty` card when `proposals.length === 0`, or structured `fields` + `actions` (`Approve action` primary / `Reject` danger) + `divider` per proposal.
   - **Tab 2 (`Collections & Connection`):** 2-column `columns` split with the `checkbox` collections form on the left and connection `fields` + `Disconnect` secondary button on the right.
