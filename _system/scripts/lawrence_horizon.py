"""Shared Lawrence owner-cash DCF horizon (years)."""
from __future__ import annotations

LAWRENCE_HORIZON_YEARS = 7

# Growth phase split: years 1–5 use growth_y1_5; years 6–horizon use growth_y6_10.
GROWTH_PHASE1_END_YEAR = 5

RETURN_LABEL = f"{LAWRENCE_HORIZON_YEARS}yr IRR"
SYNTHESIS_LABEL = f"{LAWRENCE_HORIZON_YEARS}yr IRR (total synthesis)"
IMPLIED_IRR_LABEL = f"Implied {LAWRENCE_HORIZON_YEARS}yr IRR"
