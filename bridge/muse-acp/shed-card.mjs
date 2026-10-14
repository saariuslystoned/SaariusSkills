import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { isSessionId } from "./shed-sessions.mjs";

export const CARD_PREFIX = "/c/";
export const CARD_ASSETS_PREFIX = "/c/assets/";

const ASSETS_DIR = path.join(path.dirname(fileURLToPath(import.meta.url)), "card-assets");

// Data table mapping each harness key to its display name and static logo asset.
// Adding a harness = adding a row here + its PNG logo in card-assets/.
export const HARNESS_CARD_TABLE = Object.freeze({
  antigravity: Object.freeze({
    harness: "antigravity",
    displayName: "Antigravity",
    logoAsset: "antigravity.png",
    logoPath: "/c/assets/antigravity.png",
  }),
  muse: Object.freeze({
    harness: "muse",
    displayName: "Muse",
    logoAsset: "muse.png",
    logoPath: "/c/assets/muse.png",
  }),
  generic: Object.freeze({
    harness: "generic",
    displayName: "Unknown",
    logoAsset: "generic.png",
    logoPath: "/c/assets/generic.png",
  }),
});

export const CARD_ASSET_FILES = Object.freeze(
  Object.fromEntries(
    Object.values(HARNESS_CARD_TABLE).map((entry) => [entry.logoAsset, entry.logoAsset]),
  ),
);

const DEFAULT_REPO_LABEL = "Shed";
const UNCONFIRMED_MODEL = "unconfirmed";
const SAFE_REPO_PATTERN = /^[A-Za-z0-9._-]{1,100}\/[A-Za-z0-9._-]{1,100}$/;
const SAFE_MODEL_PATTERN = /^[A-Za-z0-9._:/\-[\]= ]{1,120}$/;

const assetCache = new Map();

export function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

export function resolveHarnessCardEntry(harness) {
  if (typeof harness === "string") {
    const normalized = harness.trim().toLowerCase();
    if (Object.hasOwn(HARNESS_CARD_TABLE, normalized) && normalized !== "generic") {
      return HARNESS_CARD_TABLE[normalized];
    }
  }
  return HARNESS_CARD_TABLE.generic;
}

function sanitizeRepoLabel(repo) {
  if (typeof repo !== "string") return DEFAULT_REPO_LABEL;
  const trimmed = repo.trim();
  return SAFE_REPO_PATTERN.test(trimmed) ? trimmed : DEFAULT_REPO_LABEL;
}

function sanitizeModelLabel(model) {
  if (typeof model !== "string") return UNCONFIRMED_MODEL;
  const trimmed = model.trim();
  if (!trimmed || trimmed.toLowerCase() === "unknown") return UNCONFIRMED_MODEL;
  return SAFE_MODEL_PATTERN.test(trimmed) ? trimmed : UNCONFIRMED_MODEL;
}

// Builds the strict, minimal card model from a session view (or null/unknown).
// Unknown valid session IDs produce the exact same generic card structure as a
// session with unconfirmed metadata, avoiding any existence oracle across the
// UUID space. Only repo, harness, and model are read; prompts, transcripts,
// summaries, branches, diffs, and caller/requestedBy fields are never touched.
export function buildCardModel(sessionId, view) {
  if (!isSessionId(sessionId)) {
    throw new Error("Invalid sessionId");
  }
  const rawHarness = view && typeof view === "object"
    ? (view.harness ?? view.task?.harness)
    : undefined;
  const entry = resolveHarnessCardEntry(rawHarness);
  const repo = sanitizeRepoLabel(view?.task?.repo);
  const model = sanitizeModelLabel(view?.task?.model ?? view?.model);
  const title = `${repo} \u2014 ${entry.displayName}`;
  const description = `harness: ${entry.displayName}, model: ${model}`;
  const image = entry.logoPath;
  const redirectPath = `/s/${sessionId}`;
  return {
    sessionId,
    repo,
    harness: entry.harness,
    harnessDisplayName: entry.displayName,
    model,
    title,
    description,
    image,
    redirectPath,
  };
}

export function renderCardHtml(sessionId, view) {
  const card = buildCardModel(sessionId, view);
  const title = escapeHtml(card.title);
  const description = escapeHtml(card.description);
  const image = escapeHtml(card.image);
  const redirectPath = escapeHtml(card.redirectPath);
  const refreshContent = escapeHtml(`0; url=${card.redirectPath}`);
  return [
    "<!doctype html>",
    '<html lang="en">',
    "<head>",
    '<meta charset="utf-8">',
    `<title>${title}</title>`,
    '<meta name="robots" content="noindex">',
    `<meta property="og:title" content="${title}">`,
    `<meta name="twitter:title" content="${title}">`,
    `<meta property="og:description" content="${description}">`,
    `<meta property="og:image" content="${image}">`,
    `<meta http-equiv="refresh" content="${refreshContent}">`,
    "</head>",
    "<body>",
    `<p><a href="${redirectPath}">${redirectPath}</a></p>`,
    "</body>",
    "</html>",
    "",
  ].join("\n");
}

function cardSecurityHeaders(contentType) {
  return {
    "content-type": contentType,
    "x-robots-tag": "noindex, nofollow, noarchive, nosnippet",
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "no-referrer",
    "content-security-policy": "default-src 'none'; img-src 'self'; style-src 'none'; script-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
  };
}

async function loadCardAsset(assetName) {
  if (!Object.hasOwn(CARD_ASSET_FILES, assetName)) return null;
  const fileName = CARD_ASSET_FILES[assetName];
  if (assetCache.has(fileName)) return assetCache.get(fileName);
  const bytes = await readFile(path.join(ASSETS_DIR, fileName));
  assetCache.set(fileName, bytes);
  return bytes;
}

// Existence-oracle policy:
// 1. Malformed IDs (anything not matching SESSION_ID_PATTERN, raw percent-encoding,
//    dot-segments, or carrying a query string) return a constant 404 "not found\n"
//    without reflecting input.
// 2. Valid UUIDs always return 200 with a card page. If the session ID is
//    unknown (viewSession returns null or is not configured), the generic
//    fallback card ("Shed — Unknown", "harness: Unknown, model: unconfirmed",
//    "/c/assets/generic.png") is served so valid UUIDs have no existence oracle.
export async function handleCard(req, res, url, { viewSession } = {}) {
  const send = (status, body, contentType = "text/plain; charset=utf-8", extraHeaders = {}) => {
    res.writeHead(status, {
      ...cardSecurityHeaders(contentType),
      "cache-control": "no-store, max-age=0",
      ...extraHeaders,
    }).end(req.method === "HEAD" ? undefined : body);
  };

  if (req.method !== "GET" && req.method !== "HEAD") {
    return send(405, "method not allowed\n", "text/plain; charset=utf-8", { allow: "GET, HEAD" });
  }

  const rawUrl = String(req.url ?? "");
  if (url.search || rawUrl.includes("?") || rawUrl.includes("%") || rawUrl.includes("..") || rawUrl !== url.pathname) {
    return send(404, "not found\n");
  }

  if (url.pathname.startsWith(CARD_ASSETS_PREFIX)) {
    const assetName = url.pathname.slice(CARD_ASSETS_PREFIX.length);
    if (!Object.hasOwn(CARD_ASSET_FILES, assetName)) {
      return send(404, "not found\n");
    }
    try {
      const png = await loadCardAsset(assetName);
      if (!png) return send(404, "not found\n");
      return send(200, png, "image/png", {
        "cache-control": "public, max-age=3600",
        "content-length": String(png.length),
      });
    } catch {
      return send(404, "not found\n");
    }
  }

  if (!url.pathname.startsWith(CARD_PREFIX)) {
    return send(404, "not found\n");
  }

  const sessionId = url.pathname.slice(CARD_PREFIX.length);
  if (!isSessionId(sessionId)) {
    return send(404, "not found\n");
  }

  let view = null;
  if (typeof viewSession === "function") {
    try {
      view = await viewSession(sessionId);
    } catch {
      view = null;
    }
  }

  const html = renderCardHtml(sessionId, view);
  return send(200, html, "text/html; charset=utf-8");
}
