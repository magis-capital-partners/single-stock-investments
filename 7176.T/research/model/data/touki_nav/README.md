# 投信総合検索ライブラリー manual import (Vicki)

Drop browser-exported CSV files here as `{fund_id}.csv` (e.g. `value_up_fund.csv`).

Required columns: `as_of`, `nav_jpy`  
Optional: `aum_jpym`, `month_ret`, `high_water_mark_jpy`

Fund code for Value Up: **9D311082** (see `mandate_funds.json` → `touki_import`).

Automated scraping of toushin-lib.fwg.ne.jp is prohibited; Marvin merges these files in `download_mandate_nav.py`.
