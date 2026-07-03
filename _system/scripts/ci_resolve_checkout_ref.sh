#!/usr/bin/env bash
# Resolve the git ref ci_checkout_workspace.sh should fetch.
#
# GitHub sets GITHUB_REF_NAME=228/merge on pull_request events, but
# `git fetch origin 228/merge` fails — the fetchable ref is either the PR
# head branch (GITHUB_HEAD_REF) or pull/N/merge (from GITHUB_REF).
resolve_checkout_ref() {
  local ref_input="${1:-}"

  if [ -n "$ref_input" ]; then
    printf '%s' "$ref_input"
    return 0
  fi

  if [ "${GITHUB_EVENT_NAME:-}" = "pull_request" ] && [ -n "${GITHUB_HEAD_REF:-}" ]; then
    printf '%s' "$GITHUB_HEAD_REF"
    return 0
  fi

  if [ -n "${GITHUB_REF:-}" ] && [[ "$GITHUB_REF" == refs/pull/* ]]; then
    printf '%s' "${GITHUB_REF#refs/}"
    return 0
  fi

  if [ -n "${GITHUB_REF_NAME:-}" ]; then
    printf '%s' "$GITHUB_REF_NAME"
    return 0
  fi

  printf '%s' "main"
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  resolve_checkout_ref "${1:-}"
fi
