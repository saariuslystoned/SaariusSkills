# Cutover checklist — Puppet cursor-acpx / acpx #648

This candidate is experimental and unreleased. Ordinary route behavior stays
`available=false`. Do not treat local artifact proof as an npm release.

## Closed in this slice

- [x] Bind merge/source commit `ac22c3c8f6d077b542f19524afbe5409e46c56e8`
- [x] Distinguish PR head `8de4219c4e87af4dbbc468f0056970d2cda343a2`
- [x] Distinguish PR base `4e4dcf5bdf4689509169861fefe5cea3a334d5f8`
- [x] Distinguish stale published npm gitHead `8699be1b6428fa7584acc6f07d87f5aec8945f58`
- [x] Bind local tarball SHA-256 `fe9ba256bc562b01bff007a2e63017a28daebb2dbc460806a6e7ad0f58d32d29`
- [x] Reject metadata-hash integrity
- [x] Keep ordinary production pin `acpx@0.16.0`
- [x] Keep `available()` / ordinary launch false
- [x] Keep qualification `synthetic_only`
- [x] Keep fs/terminal callback controls explicitly disabled
- [x] Materialize exact artifact under task-owned runtime root only
- [x] Exercise actual public `createAcpRuntime` with a synthetic ACP peer
- [x] Prove one bounded completion without durable prompt/response bodies
- [x] Keep binary artifact out of the review diff; retain exact local digest proof
- [x] No public PR
- [x] No shared-plugin or production-pin change

## Remaining human gates

- [ ] Official npm release whose `gitHead` equals merge commit `ac22c3c8f6d077b542f19524afbe5409e46c56e8`
- [ ] Confirm published package version identity separately from this local `0.18.0` tarball
- [ ] Explicit decision to change the ordinary bridge/production pin off `0.16.0`
- [ ] Independent live Cursor ACP qualification against the merged runtime
- [ ] Independently observed halt, retained-owner, and cleanup proof on a live merged runtime
- [ ] Human approval to set `available()` / ordinary launch true
- [ ] Human approval to change shared plugins or production pins
- [ ] Public PR / production enablement, if ever authorized

Until those gates close, published `acpx@0.18.0` remains a stale npm
identity and must not be treated as the merged source.
