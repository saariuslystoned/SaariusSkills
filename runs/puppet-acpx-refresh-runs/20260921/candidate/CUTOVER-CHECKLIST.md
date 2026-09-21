# Cutover checklist — Puppet cursor-acpx / acpx ce8c3689

## Candidate gates already closed

- [x] Bind merge/source commit `ce8c3689fe830fd5c6199a8a683dc979d180af1d`
- [x] Bind source tree `04661dbf3af3b3c2a11d16c3061b40e20ce29f4a`
- [x] Bind local tarball SHA-256 `ad9bc677a6687268010da9c57b83fd96d2d35eddafdb55a6e043fd70679cc342`
- [x] Keep ordinary pin `acpx@0.16.0` unchanged
- [x] Keep `available=false`, `synthetic_only`, no live qualification
- [x] Preserve historical `#648` artifact/path/runtime fences
- [x] Keep PR59 ownership, cleanup, body-free, and conversation-rejection contracts

## Still required before ordinary adoption

- [ ] Official npm release whose `gitHead` equals merge commit `ce8c3689fe830fd5c6199a8a683dc979d180af1d`
- [ ] Confirm published package version identity separately from this local `0.18.0` tarball
- [ ] Live Cursor/AGY candidate qualification, if that route is later authorized
- [ ] Ordinary broker/plugin pin change
- [ ] Controller/native-view/default enablement
- [ ] Public PR and human merge

Until those gates close, published `acpx@0.18.0` remains a stale npm
identity and this slice stays candidate-only.
