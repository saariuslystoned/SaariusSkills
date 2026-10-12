import { execFile as execFileCallback } from "node:child_process";
import { realpath, stat } from "node:fs/promises";
import path from "node:path";
import { promisify } from "node:util";
import { BridgeError } from "./broker.mjs";

const execFile = promisify(execFileCallback);

export const REMOTE_REPO_OWNERS_ENV = "SAARIUS_ACP_REMOTE_REPO_OWNERS";
export const REMOTE_ORIGIN_OWNERS_ENV = "SAARIUS_ACP_REMOTE_ORIGIN_OWNERS";
const OWNER_PATTERN = /^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$/;

// Parses "owner-a,owner-b" into a lowercase set. Remote mode refuses to
// start without at least one owner: a remote caller must never reach an
// arbitrary directory on the shed.
export function parseRepoOwners(raw) {
  const owners = String(raw ?? "")
    .split(/[\s,]+/)
    .map((value) => value.trim())
    .filter(Boolean);
  if (owners.length === 0) {
    throw new BridgeError(
      "REMOTE_REPO_OWNERS_REQUIRED",
      `${REMOTE_REPO_OWNERS_ENV} must list at least one GitHub owner for remote-shed mode`,
    );
  }
  for (const owner of owners) {
    if (!OWNER_PATTERN.test(owner)) {
      throw new BridgeError("REMOTE_REPO_OWNERS_INVALID", `${REMOTE_REPO_OWNERS_ENV} entry is not a GitHub owner`, { owner });
    }
  }
  return new Set(owners.map((owner) => owner.toLowerCase()));
}

// Optional owner list (e.g. Origin namespaces); empty means none allowed.
export function parseOptionalOwners(raw, envName = REMOTE_ORIGIN_OWNERS_ENV) {
  if (!String(raw ?? "").trim()) return new Set();
  try {
    return parseRepoOwners(raw);
  } catch {
    throw new BridgeError("REMOTE_REPO_OWNERS_INVALID", `${envName} entry is not a valid owner`);
  }
}

// Extracts the namespace from an origin.cursor.com remote URL, else null.
export function originOwnerFromRemote(url) {
  const match = String(url ?? "").trim().match(/^https:\/\/(?:[^@/]+@)?origin\.cursor\.com\/(?:git\/)?([^/]+)\/[^/]+?(?:\.git)?\/?$/i);
  return match ? match[1].toLowerCase() : null;
}

// Extracts the owner from a github.com remote URL (https, ssh, scp-like).
// Returns null for any other host.
export function githubOwnerFromRemote(url) {
  const value = String(url ?? "").trim();
  const patterns = [
    /^https:\/\/(?:[^@/]+@)?github\.com\/([^/]+)\/[^/]+?(?:\.git)?\/?$/i,
    /^ssh:\/\/git@github\.com(?::\d+)?\/([^/]+)\/[^/]+?(?:\.git)?\/?$/i,
    /^git@github\.com:([^/]+)\/[^/]+?(?:\.git)?$/i,
  ];
  for (const pattern of patterns) {
    const match = value.match(pattern);
    if (match) return match[1].toLowerCase();
  }
  return null;
}

async function git(args, cwd) {
  const { stdout } = await execFile("git", args, { cwd, timeout: 10_000, maxBuffer: 64 * 1024 });
  return stdout.trim();
}

// Remote-shed workspace admission: the workspace must be an absolute
// directory that is the top level of a git checkout whose every remote
// points at github.com/<allowed owner>/... .
export function createRepoOwnerGuard({ env = process.env, owners, originOwners, runGit = git } = {}) {
  const allowed = owners ? new Set([...owners].map((o) => o.toLowerCase())) : parseRepoOwners(env[REMOTE_REPO_OWNERS_ENV]);
  const allowedOrigin = originOwners ? new Set([...originOwners].map((o) => o.toLowerCase())) : parseOptionalOwners(env[REMOTE_ORIGIN_OWNERS_ENV]);
  return async function guardWorkspace(workspace) {
    if (typeof workspace !== "string" || !path.isAbsolute(workspace)) {
      throw new BridgeError("REMOTE_WORKSPACE_INVALID", "remote-shed workspace must be an absolute path on the shed");
    }
    let resolved;
    try {
      resolved = await realpath(workspace);
      if (!(await stat(resolved)).isDirectory()) throw new Error("not a directory");
    } catch {
      throw new BridgeError("REMOTE_WORKSPACE_INVALID", "remote-shed workspace is not an existing directory on the shed", { workspace });
    }
    let topLevel;
    let remotes;
    try {
      topLevel = await realpath(await runGit(["rev-parse", "--show-toplevel"], resolved));
      const names = (await runGit(["remote"], resolved)).split(/\s+/).filter(Boolean);
      remotes = [];
      for (const name of names) {
        for (const url of (await runGit(["remote", "get-url", "--all", name], resolved)).split(/\n/).filter(Boolean)) {
          remotes.push(url);
        }
      }
    } catch {
      throw new BridgeError("REMOTE_WORKSPACE_NOT_REPO", "remote-shed workspace must be a git checkout", { workspace });
    }
    if (topLevel !== resolved) {
      throw new BridgeError("REMOTE_WORKSPACE_NOT_REPO_ROOT", "remote-shed workspace must be the repository root", { workspace });
    }
    if (remotes.length === 0) {
      throw new BridgeError("REMOTE_REPO_OWNER_REFUSED", "remote-shed workspace has no GitHub remote", { workspace });
    }
    for (const url of remotes) {
      const owner = githubOwnerFromRemote(url);
      const originOwner = owner ? null : originOwnerFromRemote(url);
      if (originOwner && allowedOrigin.has(originOwner)) continue;
      if (!owner || !allowed.has(owner)) {
        throw new BridgeError("REMOTE_REPO_OWNER_REFUSED", "remote-shed workspace remote is not an allowed GitHub owner", {
          workspace,
          owner,
          allowedOwners: [...allowed],
        });
      }
    }
    return resolved;
  };
}
