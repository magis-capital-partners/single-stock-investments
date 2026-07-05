#!/usr/bin/env bash
# Legacy wrapper — prefer cloud_setup_research_vault.sh
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
exec bash "$SCRIPT_DIR/cloud_setup_research_vault.sh"
