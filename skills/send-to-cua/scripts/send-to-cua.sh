#!/usr/bin/env bash
# Open a new Codex chat on this Mac with a computer-use prompt typed into it.
#
#   send-to-cua.sh <prompt-file> [--name <slug>] [--dry-run]
#
# The Codex app opens on a new chat with "@Computer Use" attached and the
# prompt in the composer. Codex does not send a deep-linked prompt by itself,
# so the owner presses Enter (and picks Full access if Codex asks). The prompt
# also lands on the clipboard, in case the composer comes up empty.
#
# Settings (environment):
#   CUA_WORKSPACE  folder the Codex chat opens in. Default: the first that
#                  exists of ~/Developer/side-quests/x-api and $HOME.
#   CUA_HOME       where prompts and reports are kept. Default: ~/.cua
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
workspace="${CUA_WORKSPACE:-}"
if [ -z "$workspace" ]; then
  for dir in "$HOME/Developer/side-quests/x-api" "$HOME"; do
    if [ -d "$dir" ]; then workspace="$dir"; break; fi
  done
fi
[ -d "$workspace" ] || { echo "send-to-cua: workspace $workspace is not a folder" >&2; exit 1; }

if [ -z "$name" ]; then
  name="$(basename "$prompt_file")"
  name="${name%.*}"
fi
name="$(printf '%s' "$name" | tr -c 'A-Za-z0-9._-' '-')"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$cua_home/outbox" "$cua_home/reports"
sent="$cua_home/outbox/$stamp-$name.md"
report="$cua_home/reports/$stamp-$name.md"

# The prompt as sent: Computer Use attached up front, the report rule at the end.
{
  printf '[@Computer Use](plugin://computer-use@openai-bundled)\n\n'
  cat "$prompt_file"
  printf '\n\n**When you finish or stop:** write your report to %s, then copy that same report to the clipboard with `pbcopy < %s`. Never put a secret value in it.\n' "$report" "$report"
} > "$sent"

url="$(python3 - "$sent" "$workspace" <<'PY'
import sys
from urllib.parse import quote

prompt = open(sys.argv[1], encoding="utf-8").read()
print("codex://new?prompt=" + quote(prompt, safe="") + "&path=" + quote(sys.argv[2], safe=""))
PY
)"

if [ "$dry_run" -eq 1 ]; then
  echo "prompt: $sent"
  echo "report: $report"
  echo "url-length: ${#url}"
  echo "$url"
  exit 0
fi

pbcopy < "$sent"
open "$url"
echo "Opened a Codex chat with Computer Use in $workspace. Press Enter there to start it."
echo "prompt: $sent"
echo "report: $report"
