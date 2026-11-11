"""Shared, unit-explicit mining revenue identities. Context only."""
from __future__ import annotations

import math


def fee_adjusted_breakeven(total_daily_usd: float, issued_btc_daily: float,
                          fee_daily_usd: float) -> float:
    """Fixed-dollar historical fees offset costs; they do not increase issuance."""
    if not all(math.isfinite(v) for v in (total_daily_usd, issued_btc_daily, fee_daily_usd)):
        raise ValueError("mining inputs must be finite")
    if total_daily_usd < 0 or issued_btc_daily <= 0 or fee_daily_usd < 0:
        raise ValueError("cost/fees must be nonnegative and issuance positive")
    return max(0.0, total_daily_usd - fee_daily_usd) / issued_btc_daily


def reward_economics(cost_per_issued_btc: float, subsidy_btc: float,
                     fee_btc_per_block: float, price_usd: float,
                     blocks_per_day: float = 144.0) -> dict:
    """Forward fees are BTC/block, so breakeven solves P*(subsidy+fees)=cost.

    Dollar security revenue is conditional on the explicitly supplied price.
    Cost per newly issued BTC remains unchanged by transfers of existing BTC.
    """
    values = (cost_per_issued_btc, subsidy_btc, fee_btc_per_block, price_usd, blocks_per_day)
    if not all(math.isfinite(v) and v >= 0 for v in values) or subsidy_btc <= 0 or blocks_per_day <= 0:
        raise ValueError("invalid reward economics")
    reward = subsidy_btc + fee_btc_per_block
    return {
        "production_cost_usd": round(cost_per_issued_btc, 2),
        "fee_adjusted_breakeven_usd": round(cost_per_issued_btc * subsidy_btc / reward, 2),
        "subsidy_btc_per_block": subsidy_btc,
        "fee_btc_per_block": fee_btc_per_block,
        "issued_btc_per_day": subsidy_btc * blocks_per_day,
        "fee_share_pct": round(100 * fee_btc_per_block / reward, 3),
        "subsidy_revenue_daily_usd": round(blocks_per_day * subsidy_btc * price_usd, 2),
        "fee_revenue_daily_usd": round(blocks_per_day * fee_btc_per_block * price_usd, 2),
        "security_revenue_daily_usd": round(blocks_per_day * reward * price_usd, 2),
        "price_assumption_usd": price_usd,
    }
