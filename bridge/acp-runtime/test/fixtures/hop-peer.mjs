import { writeFile } from "node:fs/promises";

const marker = process.env.SAARIUS_TEST_HOP_MARKER;
if (marker) {
  await writeFile(marker, `${JSON.stringify({
    hopArgv: process.env.SAARIUS_ACP_HOP_ARGV ?? null,
    role: process.env.SAARIUS_ACP_HOP_ROLE ?? null,
    bridgeArg: process.argv[2] ?? null,
  })}\n`);
}

process.exit(0);
