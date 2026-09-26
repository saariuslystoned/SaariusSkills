This repository has a bug report: `paginate()` in `src/paginate.mjs` returns the wrong page contents and wrong page counts. The function's contract is documented in the comment at the top of that file.

Fix `src/paginate.mjs` so it follows its documented contract exactly. Keep the fix small. Do not change the files under `test/` or `package.json`, and do not add dependencies. Run `node --test` before you finish. Do not commit.
