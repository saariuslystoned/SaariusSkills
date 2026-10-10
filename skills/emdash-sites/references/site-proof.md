# Sites, Migrations, And Demos

## Prove the editable site

A static landing page on HTTPS is useful publication, but does not establish an
operational CMS. For a requested editable site, prove this connected flow:

1. Sign in through the intended administrator flow with an authorized identity.
2. Open the actual editor, change synthetic content, save and preview it.
3. Publish and verify the corresponding public route and rendered content.
4. Reload or restart the relevant runtime and verify the intended persistence.

Record which process restarted and which storage survived. Do not seed content
again during a persistence test. A missing test login route, signin redirect, or
mock principal is not successful administrator proof. Never expose first-admin
bootstrap or test authentication as a production access mechanism.

For UI changes capture desktop and narrow-viewport evidence, including the
actual interaction. When a stylesheet review raises an issue, inspect computed
layout and behavior; an earlier rule may be overridden later. Do not dismiss a
finding without reproducing or disproving its effect.

## Diagnose the fixture before changing the product

On a runtime-startup failure, inspect the first concrete error, listener
ownership, resolved runtime and native-module compatibility. A port collision
is not evidence of a product defect; an ABI mismatch may require the supported
runtime rather than rebuilding shared dependencies. Run fixed-port fixtures
serially, or use distinct ports only when the entire fixture supports them.
Stop only processes owned by the task, never an unrelated listener.

Use the active environment's process, network and browser tools; this procedure
does not require a particular harness, operating system, machine path or Node
patch version. Keep those details in the target repository's local instructions,
and declare the supported Node range in `package.json` `engines` so an
unsupported runtime fails at install. EmDash 1.2 declares Node `>=22.16`; an
older runtime can break local SQLite before any product code runs.
After recovery, repeat the actual installed behavior: server startup or HTTP 200
alone is not successful proof.

## Migrate content without another framework

Before retiring a legacy block package, inventory its consumers: dependencies,
imports, plugin registration, seeds, stored content, editor schemas, renderers,
and deployed sites. Map required behavior to the pinned upstream page/content
APIs. Site-specific rendering components are fine; recreating a parallel block
framework defeats the migration.

Prove both a fresh install and representative migrated content. Preserve content
and a concrete rollback route before removing compatibility code. A package
version upgrade is not evidence that old content or dependencies disappeared.
Archive/delete the old repository only with separate authorization, after the
consumer work is complete.

## Template and demo integrity

Use the actual paired template/plugin artifacts. Record immutable revisions,
versions and hashes; avoid proving only workspace links that consumers cannot
install. Test the documented clean-install path with synthetic content and
ordinary user setup instructions. Include where the user edits pages, configures
the plugin, and opens the storefront.

A public demo should say what works today. Mark test checkout clearly and keep
real charges, fulfillment and customer notifications out of the demonstration
unless separately authorized. Do not expose an unprotected admin to make a
demo convenient. Verify marketing links against the actual destination and
capability; a demo with browse/cart only must not imply completed purchase proof.

## Publication evidence

Before an authorized deployment, establish route ownership and the exact build
being sent. Inventory generated output, especially reused output directories:
stale or unexpected files can survive an exporter and get published. Use an
owned fresh output location or a safe explicit regeneration contract, not broad
cleanup of unrelated files.

After publication, verify actual HTTPS routes and the expected rendered build.
Record deployment identity separately from the source merge. Retain any known
CMS, installation or transaction gaps instead of declaring the entire site done.
