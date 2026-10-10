# Plugin Surfaces And Admin UX Judgment

The mechanics of plugin formats, hooks, routes, storage, capabilities, Block
Kit and Registry publishing are upstream's: load `creating-plugins` from
the companion skills at the project's pinned release. This
reference keeps the judgment that upstream does not make for you.

## Decide distribution before writing the screen

Native packages can provide React admin components and build-time rendering;
sandboxed admin UI is described with Block Kit. Inspect the pinned version's
interfaces and runner rather than treating current docs as its API contract.

If the product requires every plugin to be Registry-enabled, maintain a small
matrix: plugin, package format, sandbox runner, UI path, storage/capabilities,
installation evidence, remaining gap. A native implementation may coexist,
but it does not satisfy the Registry column. Do not silently run a plugin
in-process and report sandbox proof.

Verify the packaged artifact and declared permissions in a clean host with the
required runner. A manifest, source import, or local workspace dependency is
insufficient. Record package/version/digest, installation method, activation
result, and actual admin operation. Separately report Registry
publication/listing; do not publish merely to prove a local build.

When the product ships through the Registry, keep native entries as developer
and test setups. Any feature that temporarily exists only natively belongs in
the plugin README's list of gaps, each with the work that closes it, so a
native-only capability is never presented as shipped.

## Package budget before implementation

Measure the baseline with the pinned official packager before adding a sandboxed
capability, then validate the candidate the same way. Record per-file emitted
bytes, total decompressed bytes, file count, enforced limits and remaining
headroom. Source size, gzip size, a successful application build and typecheck
are not substitutes for package acceptance. Inspect the emitted dependency
footprint before adding runtime libraries.

Some toolchain versions enforce a **131,072-byte (128 KiB) per-file limit**,
including the packaged backend. Recheck the resolved packager and installer for
current per-file, total and file-count limits; do not treat this as permanent.
A candidate barely below the cap passes that limit but has fragile maintenance
headroom; report the margin instead of inventing a universal reserve threshold.

Run the official bundle check inside the package build so an oversized backend
fails the build, not a later installation. The limit applies to the compiled
file the packager emits; splitting source files recovers space only when code
actually leaves that emitted file. When several open changes each add bytes,
build throwaway combination branches and choose a merge order by measured size
and dependency, since changes that fit alone can exceed the cap together.
Operator command-line tools belong in separate packages that call the plugin's
HTTP routes, so they add no bytes to the sandboxed bundle.

Prefer measured, behavior-preserving reuse over repeated speculative minifier
toggles. Do not remove localization, weaken authorization or validation, bypass
the cap, or drop promised behavior to recover space. A wider refactor or changed
product contract needs the applicable scope decision. Preserve regression proof
for existing behavior as well as the new feature.

## Reach other plugins and services through declared hosts

Check the pinned version, but do not assume one sandboxed plugin can call
another on the same site; in EmDash 1.2 it cannot. Put cross-plugin behavior
behind a hosted service and declare it: `network:request` with `allowedHosts`
listing bare hosts or `*.`-prefixed subdomain wildcards (no URLs or paths).
Unrestricted outbound access is the separate `network:request:unrestricted`
capability. Installers consent to these hosts, and changing capabilities needs
a version bump. A Registry install without the network capability cannot reach
a payment or other external service, whatever its native entry can do.

## Block Kit path

The host renders the UI; do not bundle React/Kumo browser components into a
sandboxed page, invent admin URLs, or inject DOM. Validate action/form inputs
and authorize the operation on the server even when the host supplies
authenticated dispatch and CSRF handling. Do not substitute the site's content
locale for the administrator's UI locale, or assume static manifest labels
translate automatically; report a version limitation rather than faking
support.

Block Kit is not the public page block model. In particular, sandboxed plugins
do not gain native build-time Portable Text renderers by returning admin blocks.

## Native React path

[Upstream contributor conventions](https://github.com/emdash-cms/emdash/blob/913cb1bb9b7f08c3ff0d258b4420e53835b6a58e/AGENTS.md)
use Cloudflare Kumo controls and semantic styling, with Lingui for user-facing
admin text. Apply those conventions in a compatible native integration; inspect
the host's exported interfaces instead of importing private monorepo files.

- Use Kumo buttons, inputs, dialogs and feedback rather than handcrafted copies.
  Preserve the host's theme, focus behavior and layout. Use the supported link
  control; avoid nesting an interactive button inside an anchor.
- Localize labels, validation, toasts and accessible names with Lingui. Resolve
  messages in the active locale rather than caching translated text globally.
- Use logical direction-aware spacing/alignment. Check a real narrow viewport,
  dark mode and an RTL locale for changed UI. Verify readability, focus and form
  errors, not just that the component renders.
- Follow the target repo's catalog extraction/build workflow. Upstream's
  automated catalog policy is not automatically a downstream plugin policy.

Kumo does not make a standalone lab page a native EmDash experience. Show the
screen inside the actual admin navigation, with meaningful empty/loading/error
states and an understandable primary action.

## Mount a usable capability

Register navigation, authorized handlers and persistence as one supported
capability. If a host must opt into a service composition, keep the default UI
unavailable until that composition exists. Named adapter exports alone do not
mean their routes are mounted. Test the default installation as well as the
fully configured host, and keep domain rules behind both UI adapters identical.

## Pinned upstream corrections (`creating-plugins`)

The verbatim vendor mirror contains these known mechanical defects. Packaged
`creating-plugins` references already apply the corrections below deterministically.
This explanation preserves their rationale; project-resolved versions still take
precedence. Never hand-edit the vendor mirror.

### 1. Sandboxed vs. native route handler signatures

**Affected packaged references** (original excerpts remain in the repository vendor mirror):
- `../../creating-plugins/references/block-kit.md` (sandboxed admin form handler)
- `../../creating-plugins/references/block-kit.md` (native Portable Text `optionsRoute`)

**Critical Distinction:**
As specified in [upstream API route documentation](https://docs.emdashcms.com/plugins/creating-plugins/api-routes/):
- **Sandboxed route handlers** receive two arguments: `(routeCtx, ctx)`. The first argument is `SandboxedRouteContext` (`routeCtx`), containing `input`, `request`, and `requestMeta`. The second argument is `SandboxedPluginContext` (`ctx`), containing `kv`, `storage`, `http`, `settings`, and `log`.
- **Native route handlers** receive one combined context: `async (ctx) =>`. All route context properties (`ctx.input`, `ctx.request`) and plugin services (`ctx.storage`, `ctx.kv`) reside on that single `ctx` object.

**Sandboxed Defect:** Upstream's sandboxed Block Kit form snippet declares `handler: async (ctx) =>` and attempts to access `ctx.kv.set()`. In the sandboxed runtime, declaring only `(ctx)` binds `routeCtx` to `ctx`, leaving `ctx.kv` undefined and throwing a runtime `TypeError`.
**Correction for Sandboxed Routes:** Declare two arguments `async (routeCtx, ctx) =>`. Read interactions from `routeCtx.input` and access storage/KV services via `ctx.kv`.

**Native Confirmation:** Upstream's Portable Text dynamic `optionsRoute` example is a **native** integration (`admin.portableTextBlocks[]`). Its original single-argument signature `async (ctx) =>` reading `ctx.storage.cards.query()` was correct. Do not pass two arguments to native handlers, as the second parameter is undefined under the native dispatcher.

#### Sandboxed Block Kit form handler example

```typescript
import type { BlockInteraction } from "@emdash-cms/blocks";

routes: {
  admin: {
    handler: async (routeCtx, ctx) => {
      // First argument (routeCtx) contains parsed interaction payload in input
      const interaction = routeCtx.input as BlockInteraction;

      if (interaction.type === "page_load") {
        return {
          blocks: [
            { type: "header", text: "My Plugin Settings" },
            {
              type: "form",
              block_id: "settings",
              fields: [
                { type: "text_input", action_id: "api_url", label: "API URL" },
                { type: "toggle", action_id: "enabled", label: "Enabled", initial_value: true },
              ],
              submit: { label: "Save", action_id: "save" },
            },
          ],
        };
      }

      if (interaction.type === "form_submit" && interaction.action_id === "save") {
        // Second argument (ctx) provides plugin context (kv, storage, etc.)
        await ctx.kv.set("settings", interaction.values);
        return {
          blocks: [/* updated blocks */],
          toast: { message: "Settings saved", type: "success" },
        };
      }
    },
  },
}
```

#### Native dynamic options (`optionsRoute`) handler example

```typescript
// Native plugin routes receive one combined context: async (ctx) =>
// storage
cards: { indexes: ["title"] },

// routes
"cards/list": {
  handler: async (ctx) => {
    // Single combined context provides both route input and plugin storage
    const _input = ctx.input;
    const result = await ctx.storage.cards.query({ limit: 100 });
    return { items: result.items.map((card) => ({ id: card.id, name: card.data.title })) };
  },
},

// admin.portableTextBlocks[].fields
{ type: "select", action_id: "cardId", label: "Card", options: [], optionsRoute: "cards/list" }
```

### 2. Email delivery hook (`email:deliver`) status verification and sender

**Affected packaged reference** (original excerpt remains in the repository vendor mirror):
- `../../creating-plugins/references/hooks.md` (email transport handler)

**Defect:** Upstream's transport example executes `await ctx.http!.fetch(...)` and discards the returned WHATWG `Response`. When an email provider rejects the request (e.g., 401 Unauthorized or 500 Internal Server Error), `fetch()` resolves normally rather than throwing. The handler returns `void`, causing EmDash to falsely treat delivery as successful, dispatch `email:afterSend`, and report success. Additionally, the [Resend Send Email API](https://resend.com/docs/api-reference/emails/send-email) requires a `from` sender field, which upstream omitted.

**Correction:**
1. **Configured verified sender**: Read the verified sender via `await ctx.settings.get("from")`. The sender address must be configured by the domain operator (e.g. verified sending domain in Resend); never insert real identities into code. If the `from` setting is missing, throw a sanitized configuration error immediately rather than sending an invalid request.
2. **Payload format**: Include `from` in the JSON request body along with recipient and content fields.
3. **Status verification**: The handler must check `response.ok` (HTTP status 200–299). On failure, it must throw a sanitized error. To prevent leaking credentials, user emails, or sensitive service metadata into logs or UI, the thrown error must NEVER include the provider response body, authorization tokens, or recipient/sender addresses. Return successfully only after a verified 2xx response.

#### Corrected email transport example

```typescript
// emdash-plugin.jsonc: declares hooks.email-transport:register and network:request,
// with api.resend.com in allowedHosts.
"email:deliver": {
  exclusive: true,
  handler: async ({ message }, ctx) => {
    const apiKey = await ctx.settings.get("apiKey");
    // Operator must configure a verified sender domain; never insert real identity
    const from = await ctx.settings.get("from");
    if (!from) {
      throw new Error("Email delivery failed: missing configured 'from' sender address");
    }

    const response = await ctx.http!.fetch("https://api.resend.com/emails", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${apiKey}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        from,
        to: message.to,
        cc: message.cc,
        reply_to: message.replyTo,
        subject: message.subject,
        text: message.text,
      }),
    });

    if (!response.ok) {
      // Throw sanitized error: status code only. Never include provider body,
      // authorization token, or recipient/sender address.
      throw new Error(`Email delivery failed with HTTP status ${response.status}`);
    }
  },
},
```
