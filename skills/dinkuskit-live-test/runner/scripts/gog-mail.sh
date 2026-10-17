#!/usr/bin/env bash
# Prints the newest messages matching $DINKUS_MAIL_QUERY from the test inbox, read-only.
# The runner uses it when DINKUS_E2E_MAIL_ACCOUNT names the inbox gogcli is signed in to;
# DINKUS_E2E_GOG_CLIENT picks a named gogcli OAuth client.
set -euo pipefail
account="${DINKUS_E2E_MAIL_ACCOUNT:?set DINKUS_E2E_MAIL_ACCOUNT to the test inbox}"
gog_ro=(gog --readonly --gmail-no-send --no-input -a "$account")
if [[ -n "${DINKUS_E2E_GOG_CLIENT:-}" ]]; then gog_ro+=(--client "$DINKUS_E2E_GOG_CLIENT"); fi
# Search messages, not threads: Gmail threads repeat sign-in emails, and `gmail get <threadId>` returns only the oldest one.
ids=$("${gog_ro[@]}" --json gmail messages search "$DINKUS_MAIL_QUERY" --max 3 | grep -oE '"id": *"[^"]+"' | sed -E 's/.*"([^"]+)"$/\1/' | awk '!seen[$0]++')
for id in $ids; do
  "${gog_ro[@]}" gmail get "$id" || true
done
