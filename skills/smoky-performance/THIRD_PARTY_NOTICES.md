# Third-party notice

Adapted from `openclaw-performance` in
[OpenClaw](https://github.com/openclaw/openclaw/blob/85c39026a90f58164595249f69c311ed71b44df8/.agents/skills/openclaw-performance/SKILL.md),
revision `85c39026a90f58164595249f69c311ed71b44df8` (observed 2026-11-05).

The preserved test-runtime and CI references also credit these OpenClaw sources:

- [`openclaw-test-performance`](https://github.com/openclaw/openclaw/blob/99c28bd1862dbb0234887a1550ef2ef577bd40d5/.agents/skills/openclaw-test-performance/SKILL.md),
  revision `99c28bd1862dbb0234887a1550ef2ef577bd40d5`.
- [`openclaw-ci-limits`](https://github.com/openclaw/openclaw/blob/33f8c93b5032bd2d6e3d999d38bcd3c0b3930c2d/.agents/skills/openclaw-ci-limits/SKILL.md),
  revision `33f8c93b5032bd2d6e3d999d38bcd3c0b3930c2d`.

The adaptation retains work counts, comparable measurements, removing wasted
work before caching, and checking effects across metrics. It integrates the
existing SaariusSkills CI/test performance references and one-command capture
helper. The helper keeps its serialized receipt schema for compatibility.
OpenClaw workloads, numeric thresholds and repository policy are not bundled.

Local additions are covered by the accompanying `LICENSE`. The applicable
upstream MIT notice follows.

MIT License

Copyright (c) 2026 OpenClaw Foundation

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
