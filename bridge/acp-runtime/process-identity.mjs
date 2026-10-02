import { execFile as execFileCallback } from "node:child_process";
import { promisify } from "node:util";

const execFile = promisify(execFileCallback);
// Records without this marker have no proven timezone. Never reinterpret them.
const PREFIX = "ps-utc-v1:";
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function canonicalUtc(value) {
  return typeof value === "string" && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.000Z$/.test(value) &&
    Number.isFinite(Date.parse(value)) && new Date(value).toISOString() === value;
}

export function parseUtcProcessStart(output) {
  if (typeof output !== "string") return undefined;
  const match = /^(?:Sun|Mon|Tue|Wed|Thu|Fri|Sat)\s+(\w{3})\s+(\d{1,2})\s+(\d{2}:\d{2}:\d{2})\s+(\d{4})$/.exec(output.trim());
  if (!match) return undefined;
  const month = MONTHS.indexOf(match[1]);
  if (month < 0) return undefined;
  const utc = `${match[4]}-${String(month + 1).padStart(2, "0")}-${match[2].padStart(2, "0")}T${match[3]}.000Z`;
  return canonicalUtc(utc) ? `${PREFIX}${utc}` : undefined;
}

export function compareProcessStartTimes(expected, observed) {
  const valid = (value) => typeof value === "string" && value.startsWith(PREFIX) && canonicalUtc(value.slice(PREFIX.length));
  if (!valid(expected) || !valid(observed)) return "unknown";
  return expected === observed ? "matching" : "different";
}

export async function inspectProcessIdentity(pid, run = execFile, exists = (target) => process.kill(target, 0)) {
  if (!Number.isSafeInteger(pid) || pid <= 0) return { status: "unknown" };
  try {
    exists(pid);
  } catch (error) {
    if (error?.code === "ESRCH") return { status: "missing" };
    if (error?.code !== "EPERM") return { status: "unknown" };
  }
  try {
    const { stdout } = await run("ps", ["-p", String(pid), "-o", "lstart="], {
      encoding: "utf8", timeout: 2_000, maxBuffer: 4 * 1024,
      env: { LC_ALL: "C", TZ: "UTC", PATH: process.env.PATH ?? "/usr/bin:/bin" },
    });
    const startTime = parseUtcProcessStart(stdout);
    return startTime ? { status: "alive", startTime } : { status: "unknown" };
  } catch {
    try {
      exists(pid);
      return { status: "unknown" };
    } catch (error) {
      return error?.code === "ESRCH" ? { status: "missing" } : { status: "unknown" };
    }
  }
}
