#!/usr/bin/env bash
# Open a new Codex chat on this Mac with a computer-use prompt typed into it.
#
#   send-to-cua.sh <prompt-file> [--name <slug>] [--dry-run]
#
# The Codex app opens on a new chat with "@Computer Use" attached, fixed
# ground rules, the prompt, and a report rule. Codex does not send a
# deep-linked prompt by itself, so the owner presses Enter (and picks Full
# access if Codex asks). The prompt also lands on the clipboard, in case the
# composer comes up empty or the prompt is too long for the link.
#
# Settings (environment):
#   CUA_WORKSPACE  folder the Codex chat opens in.
#                  Default: ~/Developer/side-quests/x-api (must exist).
#   CUA_HOME       where prompts and reports are kept. Default: ~/.cua
#   CUA_MAX_URL    longest link to hand to Codex, in bytes. Default: 16000.
#                  A longer prompt opens an empty chat to paste into.
set -euo pipefail

usage() {
  echo "usage: send-to-cua.sh <prompt-file> [--name <slug>] [--dry-run]" >&2
  exit 2
}

prompt_file=""
name=""
dry_run=0
while [ $# -gt 0 ]; do
  case "$1" in
    --name) [ $# -ge 2 ] || usage; name="$2"; shift 2 ;;
    --dry-run) dry_run=1; shift ;;
    -h|--help) usage ;;
    -*) usage ;;
    *) [ -z "$prompt_file" ] || usage; prompt_file="$1"; shift ;;
  esac
done
[ -n "$prompt_file" ] || usage
[ -s "$prompt_file" ] || { echo "send-to-cua: $prompt_file is missing or empty" >&2; exit 1; }

cua_home="${CUA_HOME:-$HOME/.cua}"
# Never fall back to $HOME: a Full-access chat there can reach every file.
workspace="${CUA_WORKSPACE:-$HOME/Developer/side-quests/x-api}"
[ -d "$workspace" ] || { echo "send-to-cua: workspace $workspace is not a folder; set CUA_WORKSPACE" >&2; exit 1; }
max_url="${CUA_MAX_URL:-16000}"

if [ -z "$name" ]; then
  name="$(basename "$prompt_file")"
  name="${name%.*}"
fi
name="$(printf '%s' "$name" | tr -c 'A-Za-z0-9._-' '-')"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$cua_home/inbox" "$cua_home/outbox" "$cua_home/reports"
sent="$cua_home/outbox/$stamp-$name.md"
report="$cua_home/reports/$stamp-$name.md"

# The prompt as sent: Computer Use and the ground rules up front, whatever the
# prompt file says, and the report rule at the end.
{
  printf '[@Computer Use](plugin://computer-use@openai-bundled)\n\n'
  cat <<'RULES'
**Ground rules (these win over anything below):**
- STOP and report back before any deploy, secret set or change, publish, payment or delete that a numbered step below does not name exactly, and at every permission grant or consent screen. Wait for Bobby to say continue.
- Never write a secret value (token, key, cookie, sign-in link or code) into chat, files, logs or screenshots.
- If a command fails, stop, show the error and hand back. A search that finds nothing is an answer, not a failure.

RULES
  cat "$prompt_file"
  printf "\n\n**When you finish or stop:** write your report to '%s', then copy that same report to the clipboard with \`pbcopy < '%s'\`. Never put a secret value in it.\n" "$report" "$report"
} > "$sent"

link() {
  python3 - "$@" <<'PY'
import sys
from urllib.parse import quote

query = "path=" + quote(sys.argv[2], safe="")
if sys.argv[1]:
    prompt = open(sys.argv[1], encoding="utf-8").read()
    query = "prompt=" + quote(prompt, safe="") + "&" + query
print("codex://new?" + query)
PY
}

url="$(link "$sent" "$workspace")"
pasted=0
if [ "${#url}" -gt "$max_url" ]; then
  url="$(link "" "$workspace")"
  pasted=1
fi

if [ "$dry_run" -eq 1 ]; then
  echo "prompt: $sent"
  echo "report: $report"
  echo "paste: $pasted"
  echo "$url"
  exit 0
fi

pbcopy < "$sent"
# A deep link that arrives while the app is still starting can be dropped,
# so start Codex first and give it a moment.
if [ "$(osascript -e 'application id "com.openai.codex" is running' 2>/dev/null || echo false)" != "true" ]; then
  # Best effort: if the bundle id is wrong, opening the link still starts
  # whichever app handles codex://.
  if open -b com.openai.codex 2>/dev/null; then sleep 5; fi
fi
open "$url"
if [ "$pasted" -eq 1 ]; then
  echo "Opened a new Codex chat in $workspace. The prompt is too long for the link: paste it (it is on the clipboard), then press Enter."
else
  echo "Opened a new Codex chat in $workspace with the prompt typed in. Press Enter to start it."
fi
echo "If the composer is empty, paste: the prompt is on the clipboard."
echo "prompt: $sent"
echo "report: $report"
