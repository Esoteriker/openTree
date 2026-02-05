#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$ROOT"

CHANGELOG_FILE="${1:-CHANGELOG.md}"
if [[ ! -f "$CHANGELOG_FILE" ]]; then
  echo "Missing changelog file: $CHANGELOG_FILE"
  exit 1
fi

unreleased_line="$(grep -n '^## \[Unreleased\]' "$CHANGELOG_FILE" | head -1 | cut -d: -f1 || true)"
if [[ -z "$unreleased_line" ]]; then
  echo "Unable to find '## [Unreleased]' in $CHANGELOG_FILE"
  exit 1
fi

total_lines="$(wc -l < "$CHANGELOG_FILE" | tr -d ' ')"
next_header_line="$(awk -v start="$unreleased_line" 'NR > start && /^## \[/ { print NR; exit }' "$CHANGELOG_FILE")"
if [[ -z "$next_header_line" ]]; then
  next_header_line=$((total_lines + 1))
fi

before_file="$(mktemp)"
unreleased_file="$(mktemp)"
release_file="$(mktemp)"
after_file="$(mktemp)"
output_file="$(mktemp)"

cleanup() {
  rm -f "$before_file" "$unreleased_file" "$release_file" "$after_file" "$output_file"
}
trap cleanup EXIT

if (( unreleased_line > 1 )); then
  sed -n "1,$((unreleased_line - 1))p" "$CHANGELOG_FILE" > "$before_file"
fi
sed -n "$((unreleased_line + 1)),$((next_header_line - 1))p" "$CHANGELOG_FILE" > "$unreleased_file"
if (( next_header_line <= total_lines )); then
  sed -n "${next_header_line},\$p" "$CHANGELOG_FILE" > "$after_file"
fi

# Keep a Changelog placeholders are allowed, but they are not releasable items.
if ! grep -Eq '^- ' "$unreleased_file"; then
  echo "No bullet entries found under [Unreleased]. Nothing to release."
  exit 10
fi
if ! grep -E '^- ' "$unreleased_file" | grep -vqE '^- _None yet\._$'; then
  echo "Only placeholder entries found under [Unreleased]. Nothing to release."
  exit 10
fi

sed '/^- _None yet\._$/d' "$unreleased_file" > "$release_file"

latest_version="$(grep -E '^## \[[0-9]+\.[0-9]+\.[0-9]+\]' "$CHANGELOG_FILE" | head -1 | sed -E 's/^## \[([0-9]+\.[0-9]+\.[0-9]+)\].*/\1/' || true)"
if [[ -z "$latest_version" ]]; then
  next_version="0.1.0"
else
  IFS='.' read -r major minor patch <<< "$latest_version"
  next_version="$major.$minor.$((patch + 1))"
fi

today="$(date '+%Y-%m-%d')"

{
  cat "$before_file"
  printf "## [Unreleased]\n\n"
  printf "### Added\n- _None yet._\n\n"
  printf "### Changed\n- _None yet._\n\n"
  printf "### Fixed\n- _None yet._\n\n"
  printf "## [%s] - %s\n" "$next_version" "$today"
  cat "$release_file"
  printf "\n"
  cat "$after_file"
} > "$output_file"

# Collapse long blank runs while preserving readability.
awk 'BEGIN { blank=0 } { if ($0=="") { blank++; if (blank<=2) print; next } blank=0; print }' "$output_file" > "$CHANGELOG_FILE"

echo "Created release section [$next_version] from [Unreleased]."
