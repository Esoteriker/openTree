#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$ROOT"

staged_files=()
while IFS= read -r file; do
  [[ -n "$file" ]] || continue
  staged_files+=("$file")
done < <(git diff --cached --name-only --diff-filter=ACMRT)

if [[ ${#staged_files[@]} -eq 0 ]]; then
  exit 0
fi

for file in "${staged_files[@]}"; do
  if [[ "$file" == "CHANGELOG.md" ]]; then
    exit 0
  fi
done

echo "Changelog check failed: CHANGELOG.md was not updated."
echo "Please add a changelog entry for this commit."
exit 1
