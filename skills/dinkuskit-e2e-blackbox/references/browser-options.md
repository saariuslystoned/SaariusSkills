# Cloudflare browser options

**Optional/deferred research, not the selected execution route.** This historical
assessment is not a current prerequisite. Read [current status](current-status.md)
first; any new qualification needs its own assigned scope and admission.

Documentation assessment October15,2026; these options have not been live-qualified by this route. The existing passing probe ran Chromium inside a Crabbox Cloudflare container. It did not use Browser Run or the Agents SDK.

An explicitly requested live qualification stopped at credential preflight: the inspected registry has no enrolled Browser Run fixed consumer. No Browser Run API authentication attempt, managed browser or new lease was created. This is a missing approved route, not evidence that the Cloudflare account lacks the service. The official CDP route requires `Browser Rendering - Edit` permission; an existing delegated container token cannot substitute for it. Qualify the intended account and approved consumer before attempting the tests below.

## Browser Run: next useful qualification

[Browser Run](https://www.cloudflare.com/products/browser-run/) hosts managed browsers and supports Playwright/Puppeteer. Its [Playwright CDP guide](https://developers.cloudflare.com/browser-run/cdp/playwright/) documents connecting ordinary Node Playwright to the hosted browser. A possible composition retains upstream Crabbox's Cloudflare container as the test-program executor, while the test code controls Browser Run Chromium through the official API. This is an application integration to qualify, not a new Crabbox provider or a feature already proven by the container probe.

This can remove per-runner Chromium installation and separate browser lifetime from disposable test compute. It adds a Browser Run capability/authentication boundary. Use the enrolled fixed consumer and intended account; do not put browser-control tokens or bearer Live View URLs in command arguments, prompts, traces, logs or public profiles.

Qualification: run the same owned public fixture and artifact assertions, reconnect from a second test process, verify identity/profile separation and permitted evidence capture, then test supported merchant authentication reuse. Compare complexity and elapsed time with the already-proven container browser. An easier installation alone does not prove a more reliable merchant acceptance route.

## Persistent Browser: useful session continuity, bounded lifetime

The [Agents SDK persistent Browser](https://developers.cloudflare.com/agents/tools/browser/) retains tabs, cookies and logins while its remote Browser Run session remains alive, including across Durable Object hibernation. The documented default idle lifetime is10minutes. On expiry/crash it starts a replacement and returns `restarted:true`; old login state is lost. It is not permanent browser-profile storage or automatic reauthentication.

The same Browser shares cookies/logins across its tab scopes. Allocate separate Browser instances for distinct merchant/admin identities; a separate tab is not identity isolation. Native Live View can support a deliberate initial human login/handoff into the same browser. Treat its URLs as bearer credentials and display them only through the trusted authenticated operator UI, never to the model or retained evidence.

The persistent Browser currently supports Chromium. Its public Browser/CDP APIs can serve a custom harness; adopting Pi Durable or moving the coding agent into Workers is not a prerequisite. Qualification must include reconnecting to the live session and deliberately replacing/expiring it, then proving the enrolled renewal path without another human setup. Never claim “no more logins” from continuity between two turns alone. Recording is optional and sensitive; leave it off through authentication unless an approved safe capture policy exists.

## Kitesurf: defer for the main acceptance journey

[Kitesurf](https://developers.cloudflare.com/browser-run/kitesurf/) is a lighter, stateless agent browser. Cloudflare's docs explicitly exclude long-running authenticated persistent sessions and trade away pixel-perfect Chromium rendering. Their documented comparison also shows lower CPU/memory does not imply lower wall time.

Use Chromium for the primary merchant/login/payment/PDF acceptance route. Kitesurf may later help one-shot public content/screenshot checks after site-specific compatibility is measured. Its beta and feature differences should not introduce another moving browser engine before the baseline real-provider journey passes.

## Promotion rule

Keep the currently qualified container route intact while these options are evaluated. Switching browser backend is a selected profile change with its own source, account, authentication, evidence and two-run qualification. No additional deployment, permission grant, account change or background service is authorized by this documentation assessment.
