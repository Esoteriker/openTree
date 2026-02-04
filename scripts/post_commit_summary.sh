#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$ROOT"

commit_hash="$(git rev-parse --short HEAD)"
subject="$(git log -1 --pretty=%s)"
author="$(git log -1 --pretty='%an <%ae>')"
date="$(git log -1 --date=iso-local --pretty=%ad)"

mapfile -t files < <(git diff-tree --no-commit-id --name-only -r HEAD)

has_changelog=0
has_release_notes=0
for file in "${files[@]}"; do
  case "$file" in
    CHANGELOG.md)
      has_changelog=1
      ;;
    RELEASE_NOTES.md|docs/release-notes/*)
      has_release_notes=1
      ;;
  esac
done

echo
echo "Commit created: $commit_hash"
echo "Subject: $subject"
echo "Author: $author"
echo "Date: $date"
echo
echo "Files changed (${#files[@]}):"
if [[ ${#files[@]} -eq 0 ]]; then
  echo "- (none)"
else
  for file in "${files[@]:0:12}"; do
    echo "- $file"
  done
  if [[ ${#files[@]} -gt 12 ]]; then
    echo "- ..."
  fi
fi

if [[ $has_changelog -eq 0 || $has_release_notes -eq 0 ]]; then
  echo
  echo "Reminder:"
  if [[ $has_changelog -eq 0 ]]; then
    echo "- Consider updating CHANGELOG.md for user-visible changes."
  fi
  if [[ $has_release_notes -eq 0 ]]; then
    echo "- Consider updating RELEASE_NOTES.md for releases."
  fi
fi
