#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$ROOT"

has_changelog_update() {
  printf '%s\n' "$1" | grep -qx "CHANGELOG.md"
}

pr_changed_files_from_api() {
  python3 - <<'PY'
import json
import os
import sys
from urllib.request import Request, urlopen

event_path = os.getenv("GITHUB_EVENT_PATH")
repo = os.getenv("GITHUB_REPOSITORY")
token = os.getenv("GITHUB_TOKEN", "")

if not event_path or not repo:
    sys.exit(2)

with open(event_path, "r", encoding="utf-8") as f:
    event = json.load(f)

pr = event.get("pull_request") or {}
number = pr.get("number")
if not number:
    sys.exit(2)

url = f"https://api.github.com/repos/{repo}/pulls/{number}/files?per_page=100"
headers = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}
if token:
    headers["Authorization"] = f"Bearer {token}"

files = []
while url:
    req = Request(url, headers=headers)
    with urlopen(req) as r:
        payload = json.loads(r.read().decode("utf-8"))
        files.extend(item.get("filename", "") for item in payload)
        link = r.headers.get("Link", "")
    next_url = ""
    if link:
        for part in link.split(","):
            part = part.strip()
            if 'rel="next"' in part:
                next_url = part[part.find("<") + 1 : part.find(">")]
                break
    url = next_url

print("\n".join(f for f in files if f))
PY
}

changed_files=""
if [[ "${GITHUB_EVENT_NAME:-}" == "pull_request" && -n "${GITHUB_EVENT_PATH:-}" ]]; then
  changed_files="$(pr_changed_files_from_api || true)"
fi

if [[ -z "$changed_files" ]]; then
  base_ref="${GITHUB_BASE_REF:-main}"
  git fetch origin "$base_ref:$base_ref"
  changed_files="$(git diff --name-only "$base_ref...HEAD")"
fi

if ! has_changelog_update "$changed_files"; then
  echo "Pull request policy failed: CHANGELOG.md must be updated."
  echo "Add at least one entry under [Unreleased] before merging."
  exit 1
fi

echo "Changelog policy check passed."
