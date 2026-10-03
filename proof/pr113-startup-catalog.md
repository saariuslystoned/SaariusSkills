# PR113 startup catalog verification

The published ACPx 0.19.4 fixture scheduled a catalog notification after the
session creation response with a zero-delay timer. That did not guarantee the
notification arrived after session binding and before the initial model choice.
The same fixture failed in opposite directions on Linux: an added model was
missing, while a removed model remained selectable.

The repair preserves real published-package coverage across all three bridges:

- CLI `exec` selects an advertised initial model and rejects an absent model
  without a setter or prompt.
- An established public runtime receives a catalog addition or removal before
  a mode-change reply, then proves the resulting status and model selection.
  Removal rejects selection without sending a model setter.

The fixture sends the update and reply in one write after `ensureSession`
returns. Tests retain strict outcomes, process exit checks, and the pinned
package version. No production code, dependency, assertion timeout, or CI
configuration changed. These checks do not claim delivery inside ACPx's private
session-creation window.

Cursor ACP job `a0848552-a355-4a96-8ea0-b6923a6942fd` completed with cleanup
proven. Local Node 24.21.0 passed published controls 27/27 and the full shared
runtime suite 178/178. Exact-head Linux Node 22.13 CI and independent review
remain required. Raw diagnostic evidence stays private.
