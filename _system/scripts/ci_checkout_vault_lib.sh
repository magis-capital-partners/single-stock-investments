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

# Build an HTTPS remote URL that authenticates with RESEARCH_VAULT_CLONE_TOKEN.
# Prefer x-access-token basic auth over "Authorization: bearer" so classic PATs,
# fine-grained PATs, and gh OAuth tokens (gho_*) all work for clone/fetch/push.
vault_authenticated_url() {
  local url token rest
  url="$(normalize_repo_url "${1:-${RESEARCH_VAULT_REPO_URL:-https://github.com/magis-capital-partners/research-vault.git}}")"
  token="$(trim_clone_token "${RESEARCH_VAULT_CLONE_TOKEN:-}")"
  if [ -z "$token" ]; then
    printf '%s' "$url"
    return 0
  fi
  case "$url" in
    https://*)
      rest="${url#https://}"
      printf 'https://x-access-token:%s@%s' "$token" "$rest"
      ;;
    *)
      printf '%s' "$url"
      ;;
  esac
}

# Deprecated: bearer headers reject gh OAuth tokens. Prefer vault_authenticated_url.
git_vault_auth_args() {
  local token
  token="$(trim_clone_token "${RESEARCH_VAULT_CLONE_TOKEN:-}")"
  if [ -n "$token" ]; then
    echo "-c"
    echo "http.extraHeader=AUTHORIZATION: bearer ${token}"
  fi
}
