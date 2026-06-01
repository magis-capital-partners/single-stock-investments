# Horizon Kinetics — curated extracts

Text extracts from the full HK vault for Marvin's **Tier 3 mental models** (equity yield curve, predictive attributes, time arbitrage).

**Full vault (400+ PDFs):** `C:\Users\werdn\Documents\Investing\Horizon Kinetics\hk_pdfs\` (Windows) · `HK_PDFS_ROOT` or `/opt/cursor/hk_pdfs` (cloud)  
**Ticker index:** `_system/reference/investment-wisdom/hk_ticker_index.json` — run `scan_hk_sources.py {TICKER}` before deep dives  
**Framework:** `_system/frameworks/hk_cross_reference.md` · `_system/frameworks/mental_models.md`

These are **text extracts** (not PDFs) copied from `hk_pdfs/book/build/text/` for agent readability.

## Automatic refresh

```bash
python _system/scripts/refresh_hk_extracts.py
```

Runs before every HK scan (`marvin_cloud_refresh.py`, `scan_third_party_sources.py --with-hk`). When the vault is available, copies **only changed** files per `hk_extract_manifest.json`. Writes status to `extract_refresh_status.json`.

| File | Source | Use when |
|------|--------|----------|
| `Stahl-Equity-Yield-Curve-extract.txt` | Compilation of Murray Stahl's Writings (© 2011 HK) | Plotting equity yield curve; time arbitrage mechanics |
| `HK-Q1-2025-Commentary-extract.txt` | Q1 2025 Market Commentary (Apr 2025) | Predictive attributes; SJT, Mesabi, HE case studies |
| `HK-Q3-2025-Commentary-extract.txt` | Q3 2025 Market Commentary (Oct 2025) | SJT NPI deficit; royalty trusts |
| `HK-Q1-2026-Commentary-extract.txt` | Q1 2026 Market Commentary (Apr 2026) | Royalty trust market-structure discounts |
| `Stahl-Worth-The-Time-Predictive-Attributes-extract.txt` | Worth The Time interview (Feb 2024) | Predictive vs descriptive attributes |

**Shelf PDFs (Stahl essays):** `_system/reference/investment-wisdom/stahl/`

## Manual refresh (Windows)

When vault is local only and cloud has no copy:

```powershell
$hk = "C:\Users\werdn\Documents\Investing\Horizon Kinetics\hk_pdfs\book\build\text"
$dest = "_system/reference/investment-wisdom/horizon-kinetics"
Copy-Item "$hk\Q1-2025-Horizon-Kinetics-Commentary_Final.txt" "$dest\HK-Q1-2025-Commentary-extract.txt"
# … or run refresh_hk_extracts.py with HK_PDFS_ROOT set
```

After manual copy, commit updated extracts so cloud agents read the latest in-repo text even without vault access.
