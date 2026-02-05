#!/usr/bin/env bash
set -euo pipefail

# pre-push receives refs on stdin:
# <local ref> <local sha> <remote ref> <remote sha>
while read -r _local_ref _local_sha remote_ref _remote_sha; do
  if [[ "$remote_ref" == "refs/heads/main" ]]; then
    echo "Push blocked: direct pushes to main are disabled in this clone."
    echo "Use a feature branch and open a pull request."
    exit 1
  fi
done

exit 0
