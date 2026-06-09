# 投信総合検索ライブラリー manual import (Vicki)

Drop browser-exported CSV files here as `{fund_id}.csv`.

Required columns: `as_of`, `nav_jpy`  
Optional: `aum_jpym`, `month_ret`, `high_water_mark_jpy`

| fund_id | Touki code | Fund |
|---------|------------|------|
| `value_up_fund` | **9D311082** | シンプレクス・ジャパン・バリューアップ |
| `orka_fund` | **9D326847** | シンプレクス謳歌 (verify in library) |

ETF style proxies (`1321.T`, `2516.T`, `1306.T`) are pulled automatically via yfinance in `download_mandate_nav.py`.

Automated scraping of toushin-lib.fwg.ne.jp is prohibited; Marvin merges CSVs in `download_mandate_nav.py`.
