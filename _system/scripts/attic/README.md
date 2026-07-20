# Attic — retired one-shot scripts

Scripts parked here are excluded from CI rebuild profiles and are kept only
for historical reference. Do not wire them into workflows. See
`docs/RETIRED.md` for the retirement log.

| Script | Why retired |
|---|---|
| `migrate_to_registry.py` | One-shot migration to `_system/portfolio/registry.json` (completed). |
| `vic_local_intake.py` | Legacy VIC local intake; superseded by registry-driven onboarding. |
| `migrate_drive_pdf_store_layout.py` | One-shot Drive PDF store layout migration (completed). |
| `migrate_economic_value_config.py` | One-shot economic-value config migration (completed). |
| `plan_drive_reorg.py` | One-shot Drive reorg planner (reorg completed 2026-06). |
| `organize_drive_orphan_folders.py` | One-shot Drive orphan folder cleanup (completed). |
| `marvin_batch_drain.py` (+ test) | Batch PR drain helper; its automerge dispatch was removed and no workflow invokes it. |
