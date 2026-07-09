# Biotech Quant Research Library

Curated research on **quantitative biotech investing**: specialist 13F consensus,
spend-based value, insider/short signals, and peer (clinical-trial) momentum.

**Path:** `_system/reference/biotech-quant/`

Supports the Insights → Research memory → **Biotech** tab and the ownership
pipeline under `_system/reference/market-data/ownership/`. See:

- `_system/proposals/verdad_biotech_quant_methodology_2026-07-09.md`
- `FACTOR_SPEC.json` (machine-readable factor weights and gates)
- `SYNTHESIS.md` (distilled findings; **not** promoted to `MEMORY.md`)

## Layout

```
biotech-quant/
├── README.md              ← this file (catalog + how to use)
├── SYNTHESIS.md           ← distilled Verdad + podcast rules
├── FACTOR_SPEC.json       ← factor defs, weights, banned metrics, status
├── papers/                ← primary PDFs + download helpers
│   └── secondary/         ← HTML/markdown digests (attribution only)
├── methodology/           ← our factor cookbook notes
└── _text/                 ← text extracts for grep/build scripts
```

Regenerate text extracts after adding a PDF:

```bash
python _system/scripts/extract_biotech_quant_text.py
```

## Primary sources (`papers/`)

| File | Cite | Contribution | Status |
|------|------|--------------|--------|
| `verdad_biotech_investing_2026.pdf` | Obenshain, Rasmussen & Wintner, Verdad Capital 2026 | Full white paper: specialist quality, spend value, peer momentum, L/S construction | download via `_download.sh` |
| `verdad_the_waste_land.md` | Verdad serial essay | Sector structure: failure rates, low correlation, why quant can work | archived |
| `verdad_the_inferno.md` | Verdad serial essay | Specialist / insider / short “expert” signals | archived |
| `verdad_the_golden_tree_of_life.md` | Verdad serial essay | Rebuild value + momentum; blended factor model | archived |

## Secondary digests (`papers/secondary/`)

| File | Cite | Contribution | Status |
|------|------|--------------|--------|
| `biotechedge_verdad_part1.md` | BiotechEdge digest of Verdad Part 1 | Quintile tables for specialist / insider / short | context only |
| `biotechedge_verdad_part2.md` | BiotechEdge digest of Verdad Part 2 | Spend value, peer momentum, blended 38 ppt spread | context only |
| `buysidedigest_verdad_podcast.md` | Buyside Digest / YAVP transcript notes | Specialist definition (>50% biotech), consensus > hero-picking | context only |
| `swedroe_verdad_digest.md` | Larry Swedroe Substack digest | Accessible summary of Verdad factors | context only |

## Tier

All materials in this library are **context tier** until a human adds an approved
row in `_system/frameworks/third_party_sources.md`. They may inform
`biotech_overlay` and methodology claims; they must **not** enter base Lawrence IRR
without approval.
