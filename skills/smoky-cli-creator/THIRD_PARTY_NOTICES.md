# CLI design influences

This skill selectively adapts design guidance, not executable code or a generator dependency:

- Matt Van Horn and Trevin Chow's [cli-printing-press](https://github.com/mvanhorn/cli-printing-press/tree/26d1e3ffed0e957547b1fe2e90607a9aa4845a6b), inspected at `26d1e3ffed0e957547b1fe2e90607a9aa4845a6b`: [PIPELINE.md](https://github.com/mvanhorn/cli-printing-press/blob/26d1e3ffed0e957547b1fe2e90607a9aa4845a6b/docs/PIPELINE.md), [PATTERNS.md](https://github.com/mvanhorn/cli-printing-press/blob/26d1e3ffed0e957547b1fe2e90607a9aa4845a6b/docs/PATTERNS.md), and [GOLDEN.md](https://github.com/mvanhorn/cli-printing-press/blob/26d1e3ffed0e957547b1fe2e90607a9aa4845a6b/docs/GOLDEN.md). Influences: discover alternatives before creation, distinguish mechanical inventory from judgment, test real workflows and generated output, and use contract-shaped deterministic fixtures selectively. Its Go/Cobra stack, SQLite/cache architecture, MCP generation, numerical scorecards, nine-phase pipeline, ledgers and ship/install rules are not adopted.
- Peter Steinberger's [agent-scripts create-cli](https://github.com/steipete/agent-scripts/blob/d210c0a77c8f9ae5e1d939b13238a75e87cdb69a/skills/create-cli/SKILL.md), inspected at `d210c0a77c8f9ae5e1d939b13238a75e87cdb69a`. Influences: compact interface specification, help/arguments, streams, errors, unattended behavior and configuration precedence. Its spec-only boundary applies to design-only requests here, not to separately authorized implementation.
- [Command Line Interface Guidelines](https://clig.dev/) by Aanand Prasad, Ben Firshman, Carl Tashian and Eva Parish: [source inspected at `697d6a29fc8c93d3981a755c0c7683507ad39c3e`](https://github.com/cli-guidelines/cli-guidelines/blob/697d6a29fc8c93d3981a755c0c7683507ad39c3e/content/_index.md). Also consulted the [condensed CLI guidelines reference](https://github.com/steipete/agent-scripts/blob/d210c0a77c8f9ae5e1d939b13238a75e87cdb69a/skills/create-cli/references/cli-guidelines.md), which credits clig.dev. These are background references for human-friendly, composable interfaces; no guide prose is reproduced. The guide is licensed under [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/), as stated in its [pinned README](https://github.com/cli-guidelines/cli-guidelines/blob/697d6a29fc8c93d3981a755c0c7683507ad39c3e/README.md); the MIT notices below do not cover the guide or its condensed reference.

The core is framework- and harness-neutral. These sources do not confer action permissions, replace repository contracts or prescribe private credential conventions.

## MIT notices for adapted guidance

Copyright (c) 2026 Matt Van Horn and Trevin Chow

Copyright (c) 2026 Peter Steinberger

The following MIT terms cover only the cli-printing-press material and agent-scripts `skills/create-cli/SKILL.md` credited above, not the CLI guidelines or its condensed reference:

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
