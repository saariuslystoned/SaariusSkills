#!/usr/bin/env node
// Prints the newest messages matching $DINKUS_MAIL_QUERY from the test inbox, read-only, through
// the Gmail API. The runner uses it as DINKUS_E2E_MAIL_CMD where gogcli isn't signed in, such as
// on a GitHub runner. The key comes from DINKUS_E2E_GMAIL_CLIENT_ID, DINKUS_E2E_GMAIL_CLIENT_SECRET
// and DINKUS_E2E_GMAIL_REFRESH_TOKEN; scripts/gmail-authorize.mjs makes it once.
import { accessToken, searchMail } from "../support/gmail.mjs";

const need = name => {
  const value = (process.env[name] ?? "").trim();
  if (!value) throw new Error(`${name} is not set.`);
  return value;
};

try {
  const token = await accessToken({
    clientId: need("DINKUS_E2E_GMAIL_CLIENT_ID"),
    clientSecret: need("DINKUS_E2E_GMAIL_CLIENT_SECRET"),
    refreshToken: need("DINKUS_E2E_GMAIL_REFRESH_TOKEN"),
  });
  for (const text of await searchMail(token, need("DINKUS_MAIL_QUERY"))) process.stdout.write(`${text}\n\n`);
} catch (error) {
  process.stderr.write(`${error.message}\n`);
  process.exit(1);
}
