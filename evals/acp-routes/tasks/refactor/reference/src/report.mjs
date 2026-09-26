import { parseCsv } from "./parse.mjs";
import { aggregate } from "./aggregate.mjs";
import { formatMarkdown } from "./format.mjs";

export function buildReport(text) {
  return formatMarkdown(aggregate(parseCsv(text)));
}
