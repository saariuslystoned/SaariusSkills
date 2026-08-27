# Trailblaze in the phone skill stack

Use this reference only when Trailblaze composes with Pixel Use, PhoneProof, a
physical phone, an emulator, Android Studio, or a human mirror.

## Ownership

| Component | Owns |
| --- | --- |
| PhoneProof | Acceptance claim, exact source and APK identity, target and posture, artifact selection, redaction, consequence gates, restoration, and final verdict |
| Pixel Use | Live physical-phone observation, semantic controls, named app workflows, verified action receipts, and friction learning |
| Trailblaze | Session recording, replayable journeys, trail authoring, deterministic replay, trace reports, and CI or instrumentation execution |
| Vysor or Android Studio | Optional human viewing, development, and runner surfaces; neither is proof authority merely because it displayed the phone |

## Select a route

| Goal | Route |
| --- | --- |
| One-off physical-phone inspection or action | Pixel Use |
| One-screen visual or build/install proof | PhoneProof with the selected phone controller |
| Reusable phone journey or regression | PhoneProof + Trailblaze |
| Record stable Pixel Use semantics | PhoneProof + Trailblaze via Pixel Use |
| Emulator or Android instrumentation proof | PhoneProof + Trailblaze-native runner |
| Human watches a physical phone | Add Vysor or Android Studio as a read-only mirror |

Do not require Trailblaze for every phone proof. Require it when the behavior
must be replayed, compared across builds or devices, run from CI or Android
Studio, or retained as a reusable journey.

## Choose one mutation chain

Use exactly one of these modes per run:

### `trailblaze-native`

Trailblaze and its selected driver control the device. Pixel Use may provide a
separately authorized read-only observation, but it does not mutate during the
run.

### `trailblaze-via-pixel-use`

Trailblaze records and invokes stable Pixel Use semantic tools. Pixel Use is
the sole device controller. Trailblaze must not issue a second primitive tap,
swipe, text entry, or key event around the adapter.

If control ownership changes, end the current session and start a new proof
segment with an explicit handoff. Never let two controllers race the same UI.

## Keep recordings durable

Record stable intent and replayable semantics:

- named workflows and app-semantic actions;
- natural-language step objectives;
- stable, non-sensitive inputs;
- expected verified outcomes.

Resolve these at runtime rather than persisting them in a trail:

- Pixel Use opaque device handles;
- raw device serials or reversible device identity;
- observation leases, context tokens, and other transient capabilities;
- coordinates derived from a particular frame or posture;
- private UI text, messages, account identity, or credentials.

Bind the selected Trailblaze device to the selected Pixel Use device inside the
session. With more than one eligible phone, require an explicit route-owned
selection and fail closed if the two systems cannot prove they target the same
physical phone without publishing its identity.

Re-resolve the binding after reconnect, rotation, fold or unfold, display
change, daemon restart, or session restart.

## Close PhoneProof

In addition to the Trailblaze trail and trace, retain the PhoneProof evidence
required by the route:

- exact source revision and reviewed build artifact digest;
- target class, posture, foreground package, and controller mode;
- Trailblaze version, trail digest, replay result, and report path;
- Pixel Use receipt when Pixel Use controlled the phone;
- final phone-visible capture from the intended display when the claim is
  visual;
- human-mirror alignment result, when a mirror was used;
- restoration result and remaining gates.

Trailblaze and Pixel Use can share Android accessibility, screenshot, or ADB
substrate. Their agreement is richer evidence, not automatically independent
evidence. Require a source-blind validator or separately governed capture when
the claim calls for independence.
