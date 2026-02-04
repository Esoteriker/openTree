#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$ROOT"

# High-confidence secret patterns to keep false positives low.
readonly SECRET_PATTERN='(AKIA[0-9A-Z]{16}|ASIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{35}|ghp_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{20,}|xox[baprs]-[A-Za-z0-9-]{10,}|-----BEGIN (RSA|EC|OPENSSH|DSA)? ?PRIVATE KEY-----)'

declare -a suspicious_name_hits=()
declare -a secret_hits=()

while IFS= read -r -d '' file; do
  [[ -f "$file" ]] || continue

  case "$file" in
    *.pem|*.p12|*.pfx|*.key|*.env|*.env.*|*id_rsa*|*id_dsa*|*credentials*)
      suspicious_name_hits+=("$file")
      ;;
  esac

  if hit="$(grep -nHIE --binary-files=without-match "$SECRET_PATTERN" "$file" || true)"; then
    :
  fi
  if [[ -n "${hit:-}" ]]; then
    secret_hits+=("$hit")
  fi
done < <(git ls-files -z --cached --others --exclude-standard)

if [[ ${#suspicious_name_hits[@]} -gt 0 || ${#secret_hits[@]} -gt 0 ]]; then
  echo "Secret scan failed."
  if [[ ${#secret_hits[@]} -gt 0 ]]; then
    echo
    echo "Potential credential content found:"
    printf '%s\n' "${secret_hits[@]}"
  fi
  if [[ ${#suspicious_name_hits[@]} -gt 0 ]]; then
    echo
    echo "Potential sensitive file names found:"
    printf '%s\n' "${suspicious_name_hits[@]}"
  fi
  echo
  echo "If these are safe placeholders, rotate or replace them before committing."
  exit 1
fi

echo "Secret scan passed."
