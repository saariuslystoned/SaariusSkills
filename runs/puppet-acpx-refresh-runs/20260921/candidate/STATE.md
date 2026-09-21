# Puppet acpx candidate refresh state

- status: candidate_only; unreleased; draft PR #60
- repo: saariuslystoned/SaariusSkills
- worktree: `/Users/bobbybones/Developer/worktrees/saariusskills-acpx-refresh-20260921`
- branch: `codex/puppet-acpx-refresh-20260921`
- base: SaariusSkills main `faa332ca8b3eb7da6662f127d6e3a55056f3db9d`
- proof_root: `runs/puppet-acpx-refresh-runs/20260921/candidate`
- available: false
- ordinary_launch: unavailable
- qualification: synthetic_only
- live_or_provider_action: none
- public_pr: https://github.com/saariuslystoned/SaariusSkills/pull/60 (draft)
- production_enabled: false

## Provenance

- source: https://github.com/openclaw/acpx/commit/ce8c3689fe830fd5c6199a8a683dc979d180af1d
- status: merged_unreleased
- merge/source commit: `ce8c3689fe830fd5c6199a8a683dc979d180af1d` (`#672`)
- source tree: `04661dbf3af3b3c2a11d16c3061b40e20ce29f4a`
- PR head: `c64b2751f0b8ca6e9d5613e98f7ed87f778de1b5`
- PR base: `7879505dcf79448cd71cafd82a21aa6c937a3f3e`
- stale published npm gitHead: `8699be1b6428fa7584acc6f07d87f5aec8945f58`
- candidate package version: `0.18.0` (local exact-source tarball)
- published npm version: `acpx@0.18.0` does not contain the merge
- ordinary production pin: `acpx@0.16.0`
- artifact: `runs/puppet-acpx-refresh-runs/20260921/artifacts/acpx-0.18.0.tgz`
- artifact SHA-256: `ad9bc677a6687268010da9c57b83fd96d2d35eddafdb55a6e043fd70679cc342`
- candidate runtime root: `runs/puppet-acpx-refresh-runs/20260921/runtime`
- historical fence: `#648` / `ac22c3c8f6d077b542f19524afbe5409e46c56e8` / `fe9ba256...` remains rejected

## Owner verification

- implementation commit: `4a560197607197a45abfeb537f5f841457a73db2`
- Python: 23 passed, 0 skipped
- bridge: 64 passed, 0 skipped
- artifact digest and upstream #672 head/base/merge tuple reverified

Integrity is the tarball digest, not a hash of descriptive metadata.
