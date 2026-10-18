import { execFileSync } from "node:child_process";
import { existsSync, readFileSync, rmSync } from "node:fs";
import { createHash } from "node:crypto";
import { crc32, inflateSync } from "node:zlib";
import { dirname } from "node:path";

/** Render the downloaded label's first page. A missing renderer is a failed proof step. */
export function renderLabelPdf(file, { platform = process.platform, run = execFileSync } = {}) {
  const image = `${file}.png`;
  // A picture left by an earlier run in a reused proof folder must not count as this run's.
  rmSync(image, { force: true });
  if (readFileSync(file).subarray(0, 5).toString() !== "%PDF-") throw new Error("The label is not a PDF.");
  try {
    if (platform === "linux") {
      run("pdftoppm", ["-f", "1", "-singlefile", "-scale-to", "1400", "-png", file, file], { stdio: "ignore", timeout: 30_000 });
    } else if (platform === "darwin") {
      run("qlmanage", ["-t", "-s", "1400", "-o", dirname(file), file], { stdio: "ignore", timeout: 30_000 });
    } else {
      throw new Error("unsupported platform");
    }
  } catch {
    throw new Error(`Could not render the label PDF on ${platform}. ${platform === "linux" ? "Install Poppler's pdftoppm." : "A working PDF renderer is required."}`);
  }
  if (!existsSync(image)) throw new Error("The PDF renderer produced no label picture.");
  const bytes = readFileSync(image);
  const { width, height } = decodedPngSize(bytes);
  return { image, width, height, sha256: createHash("sha256").update(bytes).digest("hex") };
}

const PNG_SIGNATURE = Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]);
// Channels and allowed bit depths for each PNG color type.
const COLORS = { 0: [1, [1, 2, 4, 8, 16]], 2: [3, [8, 16]], 3: [1, [1, 2, 4, 8]], 4: [2, [8, 16]], 6: [4, [8, 16]] };

/** Walk every chunk and inflate the pixel data, so a header-only or truncated file is refused. */
export function decodedPngSize(bytes) {
  const invalid = () => new Error("The PDF renderer produced an invalid label picture.");
  if (bytes.length < 8 || !bytes.subarray(0, 8).equals(PNG_SIGNATURE)) throw invalid();
  let header, ended = false;
  const data = [];
  for (let at = 8; !ended;) {
    if (at + 12 > bytes.length) throw invalid();
    const length = bytes.readUInt32BE(at);
    const type = bytes.toString("latin1", at + 4, at + 8);
    if (at + 12 + length > bytes.length) throw invalid();
    const body = bytes.subarray(at + 8, at + 8 + length);
    if (crc32(bytes.subarray(at + 4, at + 8 + length)) !== bytes.readUInt32BE(at + 8 + length)) throw invalid();
    if (!header && type !== "IHDR") throw invalid();
    if (type === "IHDR") {
      if (length !== 13) throw invalid();
      header = { width: body.readUInt32BE(0), height: body.readUInt32BE(4), depth: body[8], color: body[9], interlace: body[12] };
      // Compression and filter method 0 are the only ones PNG defines; interlace is 0 or 1.
      if (body[10] !== 0 || body[11] !== 0 || header.interlace > 1) throw invalid();
    }
    else if (type === "IDAT") data.push(body);
    else if (type === "IEND") ended = true;
    at += 12 + length;
  }
  const [channels, depths] = (header && COLORS[header.color]) ?? [];
  if (!header?.width || !header.height || !channels || !depths.includes(header.depth) || !data.length) throw invalid();
  let pixels;
  try { pixels = inflateSync(Buffer.concat(data)); } catch { throw invalid(); }
  const rowBytes = Math.ceil((header.width * channels * header.depth) / 8);
  // Interlaced rows are split into seven passes; for those a clean inflate is the check.
  if (header.interlace === 0) {
    if (pixels.length !== header.height * (rowBytes + 1)) throw invalid();
    // Each row starts with its filter type, and PNG defines only 0 to 4.
    for (let row = 0; row < header.height; row++) if (pixels[row * (rowBytes + 1)] > 4) throw invalid();
  }
  return { width: header.width, height: header.height };
}
