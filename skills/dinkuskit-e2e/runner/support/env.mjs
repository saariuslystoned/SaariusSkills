import { mkdirSync } from "node:fs";
import { homedir } from "node:os";
import { join, resolve } from "node:path";

const read = (name, fallback = "") => (process.env[name] ?? "").trim() || fallback;
const origin = value => new URL(value).origin;

const runId = read("DINKUS_E2E_RUN", new Date().toISOString().replace(/[:.]/g, "-"));
const store = origin(read("DINKUS_E2E_STORE", "https://e2e.sm0ky.dev"));

/** Everything a run needs, from the environment; nothing secret lives here. */
export const config = {
  runId,
  mode: read("DINKUS_E2E_MODE", "full"),
  store,
  ship: origin(read("DINKUS_E2E_SHIP", "https://ship.dinkuskit.com")),
  account: origin(read("DINKUS_E2E_ACCOUNT", "https://dinkuskit.com")),
  siteId: read("DINKUS_E2E_SITE_ID"),
  ownerEmail: read("DINKUS_E2E_OWNER_EMAIL"),
  // Finish mode: the order number (1001) or Commerce order id to finish. Empty picks the only TEST order waiting for a label.
  order: read("DINKUS_E2E_ORDER").replace(/^#/, ""),
  service: read("DINKUS_E2E_SERVICE", "GA"),
  ordersAdmin: read("DINKUS_E2E_ORDERS_ADMIN", `${store}/_emdash/admin/plugins/r_gshdrqaldna3r7sn/orders`),
  productPath: read("DINKUS_E2E_PRODUCT_PATH"),
  shopper: {
    email: read("DINKUS_E2E_SHOPPER_EMAIL"),
    name: read("DINKUS_E2E_SHOPPER_NAME", "Test Shopper"),
    line1: read("DINKUS_E2E_SHOPPER_LINE1", "1600 Pennsylvania Ave NW"),
    city: read("DINKUS_E2E_SHOPPER_CITY", "Washington"),
    region: read("DINKUS_E2E_SHOPPER_REGION", "DC"),
    postalCode: read("DINKUS_E2E_SHOPPER_ZIP", "20500"),
  },
  // A shell command that prints recent mail for $DINKUS_MAIL_QUERY (bodies included), newest first.
  mailCmd: read("DINKUS_E2E_MAIL_CMD"),
  completeWaitMs: Number(read("DINKUS_E2E_COMPLETE_WAIT_SECONDS", "420")) * 1000,
  headless: read("DINKUS_E2E_HEADLESS") === "1",
  channel: read("DINKUS_E2E_CHANNEL", "chrome"),
  profileDir: resolve(read("DINKUS_E2E_PROFILE", join(homedir(), ".dinkus-e2e", "profile"))),
  runDir: resolve(read("DINKUS_E2E_PROOF", "proof"), runId),
};

mkdirSync(config.runDir, { recursive: true });
mkdirSync(config.profileDir, { recursive: true });
