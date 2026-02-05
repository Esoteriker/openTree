#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <commit-msg-file>"
  exit 1
fi

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$ROOT"

msg_file="$1"

subject="$(sed -n '/^[[:space:]]*#/d;/^[[:space:]]*$/d;1p' "$msg_file" | tr -d '\r')"

if [[ -z "$subject" ]]; then
  # Empty message is handled by git itself; skip here.
  exit 0
fi

if ! git diff --cached --name-only --diff-filter=ACMRT | grep -qx "CHANGELOG.md"; then
  echo "Changelog check failed: CHANGELOG.md is not staged."
  echo "Stage CHANGELOG.md with a new structured line before committing."
  exit 1
fi

added_lines="$(git diff --cached --unified=0 -- CHANGELOG.md | sed -n '/^+++/d;s/^+//p' || true)"

readonly ENTRY_RE='^- [0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2} [+-][0-9]{4} \| (pending|[0-9a-f]{7,40}) \| .+$'

if ! printf '%s\n' "$added_lines" | grep -Eq "$ENTRY_RE"; then
  now="$(date '+%Y-%m-%d %H:%M %z')"
  echo "Changelog format check failed."
  echo "Required format:"
  echo "- YYYY-MM-DD HH:MM +/-ZZZZ | pending|<hash> | <summary>"
  echo "Example:"
  echo "- $now | pending | $subject"
  exit 1
fi

if ! printf '%s\n' "$added_lines" | grep -Fq "| $subject"; then
  echo "Changelog content check failed."
  echo "Add one CHANGELOG.md line that ends with the exact commit subject:"
  echo "- <timestamp> | pending | $subject"
  exit 1
fi

exit 0
