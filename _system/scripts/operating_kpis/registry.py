"""Adapter registry. One entry per issuer.

To add an issuer:

1. Write ``operating_kpis/{ticker_lower}.py`` with a parser that accepts
   document text or bytes and returns ``make_point`` rows. No network in the
   parser.
2. Add a ``fetch(fetched_at) -> tuple[list[dict], list[dict]]`` function.
   The second list is source records (``status`` of ``ok`` or ``blocked``).
3. Append ``(ticker, fetch)`` to ``ADAPTERS`` below.

The fetcher writes ``_system/reference/market-data/operating_kpis/{TICKER}.json``.
"""
from __future__ import annotations

from operating_kpis.cboe import fetch_cboe
from operating_kpis.cme import fetch_cme
from operating_kpis.ice import fetch_ice
from operating_kpis.miax import fetch_miax
from operating_kpis.occ import fetch_occ
from operating_kpis.filings import fetch_filing_kpis
from operating_kpis.psk import fetch_psk
from functools import partial

# (ticker, fetch). Order is the nightly order.
ADAPTERS: list[tuple[str, object]] = [
    ("MIAX", fetch_miax),
    ("CBOE", fetch_cboe),
    ("CME", fetch_cme),
    ("ICE", fetch_ice),
    ("OCC", fetch_occ),
    ("FNV", partial(fetch_filing_kpis, "FNV")),
    ("WPM", partial(fetch_filing_kpis, "WPM")),
    ("RGLD", partial(fetch_filing_kpis, "RGLD")),
    ("TPL", partial(fetch_filing_kpis, "TPL")),
    ("PSK.TO", fetch_psk),
]
