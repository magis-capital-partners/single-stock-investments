# Portfolio activist scan (long + short)

**Date:** 2026-07-01  
**Agent:** `short_scan_batch.py`  
**Registry:** `_system/frameworks/activist_firm_registry.json`

**Method:** `activist_reports_index.json` + local `short_reports/` markdown cache.

## Summary

| Ticker | Status | L/S | Notes |
|--------|--------|-----|-------|
| 0388.HK | no_hit | — | No activist index hits |
| 3905.T | no_hit | — | No activist index hits |
| 7176.T | no_hit | — | No activist index hits |
| 8697.T | no_hit | — | No activist index hits |
| ABX | no_hit | — | No activist index hits |
| ADN.TO | no_hit | — | No activist index hits |
| ALS.TO | no_hit | — | No activist index hits |
| AMD | no_hit | — | No activist index hits |
| AMZN | no_hit | — | No activist index hits |
| APLD | indexed | L23/S0 | 23 long, 0 short in activist index; 1 short markdown cache |
| ASX.AX | no_hit | — | No activist index hits |
| AZLCZ | no_hit | — | No activist index hits |
| B3SA3.SA | no_hit | — | No activist index hits |
| BKRB | no_hit | — | No activist index hits |
| BMYS.KL | no_hit | — | No activist index hits |
| BN | no_hit | — | No activist index hits |
| BOLSAA.MX | no_hit | — | No activist index hits |
| BSM | no_hit | — | No activist index hits |
| BUR | no_hit | — | No activist index hits |
| BVERS | no_hit | — | No activist index hits |
| BWEL | no_hit | — | No activist index hits |
| BYMA | no_hit | — | No activist index hits |
| CBOE | no_hit | — | No activist index hits |
| CBRS | no_hit | — | No activist index hits |
| CDZI | no_hit | — | No activist index hits |
| CHTR | no_hit | — | No activist index hits |
| CKX | no_hit | — | No activist index hits |
| CME | no_hit | — | No activist index hits |
| CMSG | no_hit | — | No activist index hits |
| CPRT | no_hit | — | No activist index hits |
| CRCL | no_hit | — | No activist index hits |
| CSGP | no_hit | — | No activist index hits |
| CSU | no_hit | — | No activist index hits |
| DB1.DE | no_hit | — | No activist index hits |
| DHR | no_hit | — | No activist index hits |
| DMLP | no_hit | — | No activist index hits |
| DRR.AX | no_hit | — | No activist index hits |
| ENX.PA | no_hit | — | No activist index hits |
| EVR | no_hit | — | No activist index hits |
| FNV | no_hit | — | No activist index hits |
| FRMI | no_hit | — | No activist index hits |
| FRMO | no_hit | — | No activist index hits |
| GCCO | no_hit | — | No activist index hits |
| GLXY | no_hit | — | No activist index hits |
| GOOGL | no_hit | — | No activist index hits |
| GPW.WA | no_hit | — | No activist index hits |
| GROY | no_hit | — | No activist index hits |
| HE | no_hit | — | No activist index hits |
| HEE | no_hit | — | No activist index hits |
| HKHC | no_hit | — | No activist index hits |
| HNFSA | no_hit | — | No activist index hits |
| ICE | no_hit | — | No activist index hits |
| IDA.AX | no_hit | — | No activist index hits |
| IEX.NS | no_hit | — | No activist index hits |
| KEWL | no_hit | — | No activist index hits |
| KRP | no_hit | — | No activist index hits |
| LAND | no_hit | — | No activist index hits |
| LB | no_hit | — | No activist index hits |
| LMNR | no_hit | — | No activist index hits |
| LSEG | no_hit | — | No activist index hits |
| META | no_hit | — | No activist index hits |
| MIAX | no_hit | — | No activist index hits |
| MRSH | no_hit | — | No activist index hits |
| MSB | no_hit | — | No activist index hits |
| MSTR | no_hit | — | No activist index hits |
| MTA | no_hit | — | No activist index hits |
| NBIS | no_hit | — | No activist index hits |
| NDAQ | no_hit | — | No activist index hits |
| NRP | no_hit | — | No activist index hits |
| NVDA | no_hit | — | No activist index hits |
| NZX.NZ | no_hit | — | No activist index hits |
| OR | no_hit | — | No activist index hits |
| OTCM | no_hit | — | No activist index hits |
| PBT | no_hit | — | No activist index hits |
| PCH | no_hit | — | No activist index hits |
| PCYO | no_hit | — | No activist index hits |
| PDER | no_hit | — | No activist index hits |
| PSE | no_hit | — | No activist index hits |
| PSK.TO | no_hit | — | No activist index hits |
| QDEL | no_hit | — | No activist index hits |
| RGLD | no_hit | — | No activist index hits |
| RMV.L | no_hit | — | No activist index hits |
| RPRX | no_hit | — | No activist index hits |
| RYN | no_hit | — | No activist index hits |
| S68.SI | no_hit | — | No activist index hits |
| SBR | no_hit | — | No activist index hits |
| SJT | no_hit | — | No activist index hits |
| SMR | no_hit | — | No activist index hits |
| SNOW | no_hit | — | No activist index hits |
| SOC | no_hit | — | No activist index hits |
| SPGI | no_hit | — | No activist index hits |
| STHO | no_hit | — | No activist index hits |
| TASE | no_hit | — | No activist index hits |
| TEQ.ST | no_hit | — | No activist index hits |
| TFPM | no_hit | — | No activist index hits |
| TPL | no_hit | — | No activist index hits |
| TRC | no_hit | — | No activist index hits |
| TSLA | no_hit | — | No activist index hits |
| VOXR | no_hit | — | No activist index hits |
| VTRS | no_hit | — | No activist index hits |
| WBI | no_hit | — | No activist index hits |
| WPM | no_hit | — | No activist index hits |
| WRLC | no_hit | — | No activist index hits |
| X.TO | no_hit | — | No activist index hits |
| XP | no_hit | — | No activist index hits |

## Maintenance

- Re-run scan: `python _system/scripts/scan_activist_sources.py`
- Re-run index: `python _system/scripts/short_scan_batch.py`
- Save markdown summaries: `{TICKER}/third-party-analyses/short_reports/{firm}_{date}.md`
- Reconcile in `{TICKER}/research/adversarial_{date}.md`

