#!/usr/bin/env bash
# Shared helpers for research-vault CI checkout.

# Strip embedded HTTPS credentials and trailing whitespace from a repo URL secret.
normalize_repo_url() {
  local url="$1"
  url="${url//$'\r'/}"
  url="${url//$'\n'/}"
  if [[ "$url" =~ ^https://[^/@]+@(.+)$ ]]; then
    url="https://${BASH_REMATCH[1]}"
  elif [[ "$url" =~ ^https://[^/@]+:[^/@]+@(.+)$ ]]; then
    url="https://${BASH_REMATCH[1]}"
  fi
  printf '%s' "$url"
}

# Trim trailing newlines from token secrets pasted into GitHub Actions.
trim_clone_token() {
  local token="$1"
  token="${token//$'\r'/}"
  token="${token//$'\n'/}"
  printf '%s' "$token"
}
