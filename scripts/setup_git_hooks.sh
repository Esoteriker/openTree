#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$ROOT"

git config core.hooksPath .githooks
chmod +x \
  .githooks/pre-commit \
  .githooks/commit-msg \
  .githooks/post-commit \
  scripts/secret_scan.sh \
  scripts/changelog_check.sh \
  scripts/changelog_commit_msg_check.sh \
  scripts/post_commit_summary.sh

echo "Git hooks installed."
echo "- Pre-commit: scripts/changelog_check.sh + scripts/secret_scan.sh"
echo "- Commit-msg: scripts/changelog_commit_msg_check.sh"
echo "- Post-commit: scripts/post_commit_summary.sh"
