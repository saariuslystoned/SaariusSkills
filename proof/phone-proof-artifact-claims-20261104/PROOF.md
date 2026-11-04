# PhoneProof artifact and claim boundaries

Base: `3c176f392220c3e34a67b3fe250342600596d9b0`.
Scope: `skills/phone-proof/SKILL.md` and its existing
`references/proof-contract.md`. The commit containing this packet identifies
the source revision. This is documentation validation, not device or runtime proof.

The proof contract now checks installed APK identity, isolates synthetic debug
fixtures from release artifacts, and separates emulator observations from
physical or live integration claims. The entrypoint links these checks into the
existing install/proof workflow. No helper, device controller, admission rule,
package manifest, or automatic invocation setting changes.

## Scenario review

- Installer reports success, but the installed APK differs: identity fails;
  the version label cannot substitute for digest comparison.
- Base APK matches, but a selected split differs or is missing: the complete
  selected install set must match. An app-bundle digest is not a base-APK digest.
- The authorized route cannot inspect installed files: identity remains blocked;
  the text grants no additional access.
- The task only inspects an installed app: no rebuild or install is required;
  observed app identity and the unverified build are explicit.
- A debug fixture renders success without exercising a service: it proves
  presentation only. A release package containing its component or entry point
  fails isolation even if the source was placed in a debug directory.
- A foldable emulator passes layout checks: the actual hinge, sensor, cutout,
  and device-specific input claims still need the relevant physical observations.
- The assigned route starts on a physical device: no emulator-first or new
  parked-device admission policy is introduced.

Accepted additions: the three scoped proof checks above. Rejected scope:
mandatory emulator-first ordering, a second ADB helper, private device or
service identities, new lease gates, and automatic device mutations.

## Validation

- Skill Creator `quick_validate.py`: pass (isolated PyYAML environment).
- Existing `test_phone_proof.py`: 19 passed.
- Existing `test_packaging.py`: 26 passed.
- `git diff --check`: pass.

No new tests mirror the prose. Existing helper and packaging behavior remains
unchanged. Live device proof is not claimed or needed for this documentation-only
change. CI and external review belong to the PR's exact source head; merge remains
an owner decision.
