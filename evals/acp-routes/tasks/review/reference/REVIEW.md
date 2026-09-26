```json
[
  { "function": "splitEvenly", "line": 7, "summary": "The remainder is dropped, so parts do not sum to totalCents.", "failingInput": "splitEvenly(10, 3) -> [3,3,3]" },
  { "function": "formatCents", "line": 12, "summary": "Math.floor and % mis-format negative amounts.", "failingInput": "formatCents(-5) -> \"-1.-5\"" },
  { "function": "parseAmount", "line": 21, "summary": "A one-digit fraction is read as cents instead of tenths.", "failingInput": "parseAmount(\"12.3\") -> 1203" }
]
```
