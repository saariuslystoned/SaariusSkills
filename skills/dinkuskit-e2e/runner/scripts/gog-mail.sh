#!/usr/bin/env bash
# Prints the newest messages matching $DINKUS_MAIL_QUERY from the test inbox, read-only.
# Use as DINKUS_E2E_MAIL_CMD="$PWD/scripts/gog-mail.sh". Set DINKUS_MAIL_ACCOUNT / DINKUS_MAIL_CLIENT to override.
set -euo pipefail
account="${DINKUS_MAIL_ACCOUNT:-agent@smokyproduct.co}"
client="${DINKUS_MAIL_CLIENT:-smoky-agent}"
gog_ro=(gog --readonly --gmail-no-send --no-input -a "$account" --client "$client")
ids=$("${gog_ro[@]}" --json gmail search "$DINKUS_MAIL_QUERY" --max 3 | grep -oE '"id": *"[^"]+"' | sed -E 's/.*"([^"]+)"$/\1/' | awk '!seen[$0]++')
for id in $ids; do
  "${gog_ro[@]}" gmail get "$id" || true
done
