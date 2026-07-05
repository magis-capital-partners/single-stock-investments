#!/usr/bin/env bash
# One-time migration: extract sensitive reference corpora into a sibling research-vault repo.
#
# Usage (from ops repo root):
#   bash _system/scripts/migrate_extract_vault.sh
#   bash _system/scripts/migrate_extract_vault.sh --target ../research-vault
#
# After extraction:
#   1. cd ../research-vault && git init && git add -A && git commit
#   2. Create private GitHub repo magis-capital-partners/research-vault and push
#   3. bash _system/scripts/migrate_remove_vault_from_ops.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TARGET="${1:-$ROOT/../research-vault}"

if [[ "${1:-}" == "--target" ]]; then
  TARGET="${2:?target path required}"
fi

mkdir -p "$TARGET"

copy_tree() {
  local src_name="$1"
  local dest_name="${2:-$src_name}"
  local src="$ROOT/_system/reference/$src_name"
  local dest="$TARGET/$dest_name"
  if [ -d "$src" ]; then
    echo "Copying $src_name -> $dest_name/"
    mkdir -p "$(dirname "$dest")"
    rsync -a --delete "$src/" "$dest/"
  else
    echo "Skip missing $src"
  fi
}

echo "Extracting vault content to $TARGET"

copy_tree "superinvestor-letters" "superinvestor-letters"
copy_tree "investment-wisdom" "investment-wisdom"
copy_tree "sumzero-research" "sumzero-research"

DROPBOX_SRC="$ROOT/_system/dropbox_ingestion"
if [ -d "$DROPBOX_SRC" ]; then
  echo "Copying dropbox_ingestion -> dropbox-ingestion/"
  rsync -a "$DROPBOX_SRC/" "$TARGET/dropbox-ingestion/"
fi

TEMPLATE="$ROOT/_system/migration/research-vault-template"
if [ -d "$TEMPLATE" ]; then
  for f in README.md .gitignore; do
    if [ -f "$TEMPLATE/$f" ] && [ ! -f "$TARGET/$f" ]; then
      cp "$TEMPLATE/$f" "$TARGET/$f"
    fi
  done
fi

python3 - <<PY
import json, os, sys
sys.path.insert(0, os.path.join("$ROOT", "_system", "scripts"))
os.environ["RESEARCH_VAULT_ROOT"] = "$TARGET"
from vault_paths import vault_status
print(json.dumps(vault_status(), indent=2))
PY

echo ""
echo "Vault extract complete: $TARGET"
echo "Next: init git in target, push to magis-capital-partners/research-vault, then run migrate_remove_vault_from_ops.sh"
