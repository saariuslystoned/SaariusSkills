Build a small, accessible, sortable and filterable jobs table.

1. Implement the two exports in `src/table.mjs` exactly as specified in the comment at the top of that file. They must be pure functions that run in Node and in the browser.
2. Wire `index.html` (which already loads `data/jobs.json` rendering code stub) so that: clicking a column header's button sorts by that column (toggling ascending/descending), a text input filters rows as you type, and the table re-renders using `renderTable`. Use a `<script type="module">`. Make it look clean with a small inline `<style>` block that works in light and dark mode.

No dependencies, no build step. Do not change files under `test/`, `data/` or `package.json`. Run `node --test` before you finish. Do not commit.
