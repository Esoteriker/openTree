#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$ROOT"

base_ref="${GITHUB_BASE_REF:-main}"

git fetch origin "$base_ref:$base_ref"

changed_files="$(git diff --name-only "$base_ref...HEAD")"
if ! printf '%s\n' "$changed_files" | grep -qx "CHANGELOG.md"; then
  echo "Pull request policy failed: CHANGELOG.md must be updated."
  echo "Add at least one entry under [Unreleased] before merging."
  exit 1
fi

echo "Changelog policy check passed."
