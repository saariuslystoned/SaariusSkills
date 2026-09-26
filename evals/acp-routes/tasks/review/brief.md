Review `src/money.mjs` for correctness bugs. Each function's intended behaviour is stated in its doc comment; the existing tests only cover happy paths.

Do not modify anything under `src/` or `test/`. You may write scratch scripts outside those folders to probe behaviour.

Write your findings to `REVIEW.md` as a single fenced JSON code block containing an array. One object per real bug:
`{ "function": "<exported function name>", "line": <line number in src/money.mjs>, "summary": "<one sentence>", "failingInput": "<a concrete input that shows the bug>" }`

Report only bugs you are confident about; false positives count against you. Do not commit.
