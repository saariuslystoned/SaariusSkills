import { execFileSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { dirname } from "node:path";

/** Render the downloaded label's first page. A missing renderer is a failed proof step. */
export function renderLabelPdf(file, { platform = process.platform, run = execFileSync } = {}) {
  const image = `${file}.png`;
  if (existsSync(image)) throw new Error("The label picture already exists; use a fresh proof folder.");
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
  if (bytes.length < 24 || !bytes.subarray(0, 8).equals(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]))
      || !bytes.readUInt32BE(16) || !bytes.readUInt32BE(20)) throw new Error("The PDF renderer produced an invalid label picture.");
  return { image, width: bytes.readUInt32BE(16), height: bytes.readUInt32BE(20), sha256: createHash("sha256").update(bytes).digest("hex") };
}
