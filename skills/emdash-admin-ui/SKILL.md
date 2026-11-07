---
name: emdash-admin-ui
description: Design and build opinionated, Kumo-native EmDash CMS admin pages, editor side-panels, and dashboard widgets across both Registry Block Kit (`@emdash-cms/blocks/server`) and native React (`@cloudflare/kumo` + Lingui). Eliminates flat full-width form dumps in favor of structured `stats` KPI cards, 2-column `columns` splits, Kumo `tab` underline workspaces, `empty` hero onboarding cards, `table` badge/code checklists, `secret_input`, and `checkbox` groups.
---

# EmDash Admin UI (`emdash-admin-ui`)

Design and implement EmDash CMS admin pages, editor side-panels (`admin.editorPanels`), and dashboard widgets that feel like first-party Cloudflare Kumo surfaces rather than unstyled vertical form dumps.

---

## 1. Choose the Surface Track (`Block Kit` vs. `Native React Kumo`)

| Track | When to Use | Renderer & Primitives | Reference |
| --- | --- | --- | --- |
| **Registry / Sandboxed Block Kit** (`@emdash-cms/blocks/server`) | **Default for all Registry-installable plugins** (`emdash-plugin.jsonc`). No plugin JS runs in the browser; the host renders JSON blocks through `@cloudflare/kumo`. | `stats`, `columns`, `tab`, `empty`, `table` (`badge`, `code`, `element`), `accordion`, `code`, `form` (`secret_input`, `checkbox`, `combobox`, `select`, `text_input`). | [references/block-kit-composition.md](references/block-kit-composition.md) |
| **Trusted Native React Kumo** (`@cloudflare/kumo` + `@lingui/macro`) | Only when a host-integrated native admin extension requires custom interactive canvas/drag-and-drop or bespoke Kumo dialogs not expressible in Block Kit, and any Registry gap is explicitly recorded. | `<Tabs variant="underline">`, `<Empty>`, `<Banner>`, `<Input>`, `<SensitiveInput>`, `<Checkbox.Group>`, `<Badge>`, `<Collapsible>`, `<TimeseriesChart>`. | [references/kumo-native-admin.md](references/kumo-native-admin.md) |

---

## 2. The 7 Opinionated Block Kit Composition Rules

Upstream `@emdash-cms/blocks` maps each block type directly to a `@cloudflare/kumo` primitive with specific layout constraints (see [references/block-kit-composition.md](references/block-kit-composition.md)). Most "ugly" plugin admin pages fail because they stack a `banner`, `fields`, and a full-width `form` vertically at the root. Follow these 7 rules on every Block Kit screen:

1. **Never Place a Full-Width Setup Form at Root Level — Use a 2-Column `columns` Split:**
   - A root-level `form` stretches `100%` of the admin viewport (`1200px–1440px`), turning text inputs into awkward full-screen bars.
   - Always place forms inside a 2-column `columns` block (`grid grid-cols-2 gap-4`):
     - **Left column:** Onboarding action (`empty` hero card or `code` pairing prompt) + a 3-row setup checklist `table`.
     - **Right column:** The compact `form` (`~50%` viewport width).

2. **Anchor Every Page with a 3-Card `stats` Row (Bordered Kumo KPI Cards):**
   - In `@emdash-cms/blocks`, `stats` is the primary block that renders bordered Kumo surface cards (`rounded-lg border border-kumo-line p-4` with `text-2xl font-bold`, `description`, and `trend` indicator).
   - Place a 3-item `stats` block directly below `header(...)` on both onboarding and connected workspace views to establish visual rhythm and surface key status (`Connection Status`, `Active Model / Runtime`, `Approval Queue`).

3. **Use Kumo `empty` (`size: "base"` or `"lg"`) for Onboarding & Zero-States — Not Blue Info Banners:**
   - Reserve `banner` for **actual runtime errors (`variant: "error"`), active in-flight warnings (`variant: "alert"`), or transient replies**.
   - Never open a setup page with a default blue `banner` explaining what the plugin is. Use an `empty` block (`icon: Package duotone`, `title`, `description`, `command_line`, `actions: [{ type: "link", appearance: "primary", ... }]`) so 1-Click Deploy or primary onboarding actions render inside a centered Kumo hero card.

4. **Organize Connected Workspaces with Kumo `tab` Underline Navigation:**
   - Do not stack Prompt Form + Active Task Steer + Pending Approvals + Collection Settings + Disconnect Button in one long vertical scroll.
   - Wrap connected workspace views in a `tab` block (`<Tabs variant="underline">`) with 3 focused panels:
     1. **`Assistant & Live Steer`** (2-column `columns` split: prompt form on the left, live status/steer or `empty` ready card on the right).
     2. **`Approval Queue (<count>)`** (`WAITING_FOR_HUMAN` approval cards, or a clean `empty` card when zero proposals are pending).
     3. **`Collections & Connection`** (2-column `columns` split: collection `checkbox` group on the left, connection metadata + `Disconnect` button on the right).

5. **Never Abuse `fields` for Step-by-Step Instructions — Use a `table` with `badge` and `code` Formats:**
   - `fields` renders a borderless 2-column grid with `truncate` (`text-kumo-default truncate`), clipping any instruction longer than one short phrase.
   - For setup steps (`1. Deploy` → `2. Domains Tab` → `3. Connect`), use a 3-row `table` with `format: "badge"` on the step column and `format: "code"` on the action/setting column. Reserve `fields` strictly for short key/value metadata (`Gateway`, `Agent ID`, `Target Entry`).

6. **Use `secret_input` for Tokens/Keys and `checkbox` Groups for Multi-Collection Toggles:**
   - Never use `text_input` for API keys, bearer tokens, or webhook secrets; use `secret_input` so `@emdash-cms/blocks` renders Kumo's `<SensitiveInput>` (`••••••••` mask + reveal toggle).
   - Never render `N` separate `toggle` switches with repetitive labels (`Enable Editor Side-Panel on "Pages"`, `Enable Editor Side-Panel on "Posts"`, ...); use a single `checkbox` element (`<Checkbox.Group legend="Enable Editor Side-Panel on Collections">`).

7. **Editor Side-Panels (`admin.editorPanels`) Stay Single-Column and Context-Dense:**
   - Editor side-panels render inside a narrow drawer alongside the document editor (`route.ui.entry`). Never put `columns` or `tab` blocks inside an editor side-panel; use a compact 2-item `fields` header (`Agent / Model`, `Entry`) followed by a single `form` (`multiline: true` instruction input + primary submit).

---

## 3. Local Dev Verification (`localhost` Dev-Bypass & Encryption Key)

When previewing or verifying EmDash admin UI locally (`astro dev`):

1. **Valid `EMDASH_ENCRYPTION_KEY` Format:**
   - Any plugin that writes `type: "secret"` settings via `ctx.settings.compareAndSet()` requires `EMDASH_ENCRYPTION_KEY` formatted as `"emdash_enc_v1_"` followed by 43 base64url characters (32 bytes), e.g. generated via `emdash secrets generate` or:
     ```bash
     node -e 'console.log("emdash_enc_v1_" + Buffer.alloc(32, 7).toString("base64url"))'
     ```
   - Passing a raw hex string causes `settings/compareAndSet` to fail with HTTP 400 (`EMDASH_ENCRYPTION_KEY entry is malformed`).
2. **Passkey Dev-Bypass on `localhost`:**
   - Unless WebAuthn/Passkeys are under test, seed and sign in via `GET http://localhost:<port>/_emdash/api/setup/dev-bypass` and `GET http://localhost:<port>/_emdash/api/auth/dev-bypass?redirect=/_emdash/admin`.
3. **Restart `astro dev` After Rebuilding `dist/plugin.mjs`:**
   - `@emdash-cms/sandbox-workerd/sandbox` caches the compiled plugin bundle in its in-memory `workerd` instance; restart `astro dev` after `emdash-plugin build` so the live browser reflects updated Block Kit layouts.
