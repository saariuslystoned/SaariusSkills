# Design references and adaptation boundaries

This skill adapts conceptual guidance, not upstream analyzers or personal tooling:

- Peter Steinberger, [steipete/agent-scripts skill-cleaner](https://github.com/steipete/agent-scripts/blob/d210c0a77c8f9ae5e1d939b13238a75e87cdb69a/skills/skill-cleaner/SKILL.md), revision `d210c0a77c8f9ae5e1d939b13238a75e87cdb69a`: compare duplicate bodies/canonical copies, preserve task trigger nouns, recommend before applying changes. This adaptation excludes its personal paths, default filesystem/log discovery, loaded Codex inventory and context-budget assumptions. The Python helper is repository-owned, not a port of its TypeScript analyzer.
- Vincent Koc, [vincentkoc/dotskills technical-skill-finder](https://github.com/vincentkoc/dotskills/blob/c9ca51e3a4e93fe10266d78e430c6575a5b19d30/skills/technical-skill-finder/SKILL.md), revision `c9ca51e3a4e93fe10266d78e430c6575a5b19d30` and its [scorecard](https://github.com/vincentkoc/dotskills/blob/c9ca51e3a4e93fe10266d78e430c6575a5b19d30/skills/technical-skill-finder/references/scorecard.md): compare existing coverage before proposing new work, anchor recommendations in evidence and make uncertainty explicit. This adaptation uses scoped source/caller evidence instead of mining logs; it excludes upstream personal-source discovery, runtime/artifact contracts and numerical ranking/confidence thresholds.

Both sources are MIT-licensed. Full notices follow. This directory's `LICENSE` covers repository-authored material; these acknowledgements travel with the distributable skill. No upstream runtime or private binding is required.

## agent-scripts

MIT License

Copyright (c) 2026 Peter Steinberger

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

## dotskills

MIT License

Copyright (c) 2026 Vincent Koc

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
