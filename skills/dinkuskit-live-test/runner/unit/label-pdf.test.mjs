import assert from "node:assert/strict";
import test from "node:test";
import { mkdtempSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { renderLabelPdf } from "../support/label-pdf.mjs";

function fixture(fn) {
  const directory = mkdtempSync(join(tmpdir(), "label-render-"));
  const file = join(directory, "label with spaces.pdf");
  writeFileSync(file, "%PDF-1.4\nsynthetic renderer contract");
  try { fn(file); } finally { rmSync(directory, { recursive: true, force: true }); }
}
function png(file) {
  const bytes = Buffer.alloc(24);
  Buffer.from([137,80,78,71,13,10,26,10]).copy(bytes); bytes.writeUInt32BE(933,16); bytes.writeUInt32BE(1400,20);
  writeFileSync(file + ".png", bytes);
}

test("Linux renders one bounded first page with argv, not shell interpolation", () => fixture(file => {
  let called;
  const result = renderLabelPdf(file, { platform: "linux", run: (...args) => { called = args; png(file); } });
  assert.deepEqual(called, ["pdftoppm", ["-f","1","-singlefile","-scale-to","1400","-png",file,file], { stdio:"ignore", timeout:30000 }]);
  assert.equal(result.image, file + ".png"); assert.equal(result.width,933); assert.equal(result.height,1400);
  assert.match(result.sha256, /^[a-f0-9]{64}$/);
}));
test("macOS keeps Quick Look rendering", () => fixture(file => {
  let command;
  renderLabelPdf(file, { platform:"darwin", run: name => { command=name; png(file); } });
  assert.equal(command,"qlmanage");
}));
test("missing Linux renderer is a visible failure", () => fixture(file => {
  assert.throws(() => renderLabelPdf(file, { platform:"linux", run:()=>{ throw Error("ENOENT"); } }), /Install Poppler/);
}));
test("no output, invalid output and stale output cannot claim a rendered label", () => {
  fixture(file => assert.throws(() => renderLabelPdf(file,{platform:"linux",run:()=>{}}), /no label picture/));
  fixture(file => assert.throws(() => renderLabelPdf(file,{platform:"linux",run:()=>writeFileSync(file+".png","not an image")}), /invalid label picture/));
  fixture(file => { png(file); assert.throws(() => renderLabelPdf(file), /already exists/); });
});
test("non-PDF input is refused before running anything", () => fixture(file => {
  writeFileSync(file,"not a PDF");
  assert.throws(() => renderLabelPdf(file,{run:()=>assert.fail("renderer invoked")}), /not a PDF/);
}));
