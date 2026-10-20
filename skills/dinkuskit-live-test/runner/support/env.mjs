import { existsSync, mkdirSync, readFileSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { accessQuery } from "./mail-patterns.mjs";
import { parseSettings } from "./settings-file.mjs";

const home = join(homedir(), ".dinkus-e2e");

// This machine's settings (store, site id, test inbox) live outside the repo, in ~/.dinkus-e2e/env.
// A variable already set in the environment wins over the file.
const settingsFile = resolve(process.env.DINKUS_E2E_ENV_FILE || join(home, "env"));
if (existsSync(settingsFile)) {
  for (const [key, value] of Object.entries(parseSettings(readFileSync(settingsFile, "utf8")))) {
    if (!(process.env[key] ?? "").trim()) process.env[key] = value;
  }
}

const read = (name, fallback = "") => (process.env[name] ?? "").trim() || fallback;
const origin = value => value && new URL(value).origin;
const shellQuote = value => `'${value.replaceAll("'", "'\\''")}'`;

const runId = read("DINKUS_E2E_RUN", new Date().toISOString().replace(/[:.]/g, "-"));
// Playwright's worker process loads this file again; handing it the same run id keeps the
// screenshots, PROOF.md and Playwright's own report in one proof folder.
process.env.DINKUS_E2E_RUN = runId;
const store = origin(read("DINKUS_E2E_STORE"));
const mailAccount = read("DINKUS_E2E_MAIL_ACCOUNT");
const gogMail = resolve(dirname(fileURLToPath(import.meta.url)), "../scripts/gog-mail.sh");
const ordersAdmin = read("DINKUS_E2E_ORDERS_ADMIN", `${store}/_emdash/admin/plugins/r_gshdrqaldna3r7sn/orders`);
const ordersToComplete = read("DINKUS_E2E_ORDERS_TO_COMPLETE");

/** Everything a run needs, from the environment and the settings file; nothing secret lives here. */
export const config = {
  runId,
  settingsFile,
  mode: read("DINKUS_E2E_MODE", "full"),
  store,
  accessOrigins: read("DINKUS_E2E_ACCESS_ORIGINS").split(",").map(value => value.trim()).filter(Boolean),
  ship: origin(read("DINKUS_E2E_SHIP", "https://ship.dinkuskit.com")),
  account: origin(read("DINKUS_E2E_ACCOUNT", "https://dinkuskit.com")),
  siteId: read("DINKUS_E2E_SITE_ID"),
  // "wait" lets a person sign in to the store admin when the saved profile has no sign-in yet.
  adminSignIn: read("DINKUS_E2E_ADMIN_SIGNIN", "skip"),
  ownerEmail: read("DINKUS_E2E_OWNER_EMAIL"),
  // Finish mode: the order number (1001) or Commerce order id to finish. Empty picks the only TEST order waiting for a label.
  order: read("DINKUS_E2E_ORDER").replace(/^#/, ""),
  service: read("DINKUS_E2E_SERVICE", "GA"),
  ordersAdmin,
  // Commerce Products sits beside Commerce Orders, so a beta install's Orders setting covers both.
  productsAdmin: read("DINKUS_E2E_PRODUCTS_ADMIN", ordersAdmin.replace(/\/orders\/?$/, "/products")),
  // The Ship plugin's Shipping page in the store admin; empty finds it in the admin's menu.
  shippingAdmin: read("DINKUS_E2E_SHIPPING_ADMIN"),
  productPath: read("DINKUS_E2E_PRODUCT_PATH"),
  // Full catalog: categories x products per category of the standing catalog the test keeps on the store.
  catalog: read("DINKUS_E2E_CATALOG", "3x8"),
  // Mark as completed: Processing TEST orders (1003,1004) for the owner and then the agent to complete, instead of placing new ones.
  // Every entry is kept as written, blanks included, so the journey refuses a typo rather than placing an order in its place.
  ordersToComplete: ordersToComplete ? ordersToComplete.split(",").map(number => number.trim()) : [],
  shopper: {
    email: read("DINKUS_E2E_SHOPPER_EMAIL"),
    name: read("DINKUS_E2E_SHOPPER_NAME", "Test Shopper"),
    line1: read("DINKUS_E2E_SHOPPER_LINE1", "1600 Pennsylvania Ave NW"),
    city: read("DINKUS_E2E_SHOPPER_CITY", "Washington"),
    region: read("DINKUS_E2E_SHOPPER_REGION", "DC"),
    postalCode: read("DINKUS_E2E_SHOPPER_ZIP", "20500"),
  },
  // A shell command that prints recent mail for $DINKUS_MAIL_QUERY (bodies included), newest first.
  // Naming the test inbox in DINKUS_E2E_MAIL_ACCOUNT picks the bundled read-only gogcli script.
  mailCmd: read("DINKUS_E2E_MAIL_CMD", mailAccount ? shellQuote(gogMail) : ""),
  // The Gmail search for Cloudflare Access's one-time PIN email, when the store admin's Access app offers PIN login.
  accessMailQuery: read("DINKUS_E2E_ACCESS_MAIL_QUERY", accessQuery(store)),
  completeWaitMs: Number(read("DINKUS_E2E_COMPLETE_WAIT_SECONDS", "420")) * 1000,
  headless: read("DINKUS_E2E_HEADLESS") === "1",
  video: read("DINKUS_E2E_VIDEO") === "1",
  channel: read("DINKUS_E2E_CHANNEL", "chrome"),
  profileDir: resolve(read("DINKUS_E2E_PROFILE", join(home, "profile"))),
  runDir: resolve(read("DINKUS_E2E_PROOF", join(home, "proof")), runId),
};

mkdirSync(config.runDir, { recursive: true });
mkdirSync(config.profileDir, { recursive: true });
