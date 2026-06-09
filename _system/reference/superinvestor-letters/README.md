# Superinvestor letters

Structured extracts for the Insights layer. **Raw PDFs stay local** (copyright); commit `insights.json` + `letters_index.json` only.

## Drop workflow (automated — preferred)

Configured Dropbox folders in `sources.json`. Fetch + extract + build in one command:

```bash
python _system/scripts/fetch_superinvestor_letters.py --all --build
python _system/scripts/fetch_superinvestor_letters.py --quarter 2026Q2 --build
```

Mechanism: Dropbox shared folders return a **zip** when `dl=1` is appended to the share URL (~189 PDFs for 2026 Q1).

## Manual drop (fallback)

1. Download letters manually → `INCOMING/` (or `2026Q1/`, `2026Q2/`).
2. Extract text locally (keep `.txt` alongside PDF; PDFs gitignored).
3. Run:

```bash
python _system/scripts/build_superinvestor_insights.py
python _system/scripts/build_insights.py
python _system/scripts/relevance_calibration_check.py
```

## Files

| File | Committed | Purpose |
|------|-----------|---------|
| `INCOMING/` | no (gitignored) | Human drop zone |
| `2026Q1/*.txt` | yes (text extracts) | Parsed letter text |
| `2026Q1/*.pdf` | no | Raw letters |
| `insights.json` | yes | Structured themes/positions |
| `letters_index.json` | yes | Index for UI |
| `manifest.csv` | yes | Audit trail |

## Schema

See `_system/proposals/persona_lens_consensus_2026-06-08.md` § Insights layer.
