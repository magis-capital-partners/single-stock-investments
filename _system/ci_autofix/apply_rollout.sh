#!/usr/bin/env bash
set -euo pipefail

echo "This rollout path is deprecated because its static bundles predate the shared LLM admission gate." >&2
echo "Use _system/ci_autofix/install_org_repos.ps1, which installs the current gate, policy, ledger, and pinned dependencies." >&2
exit 2
