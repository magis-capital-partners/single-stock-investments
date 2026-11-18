"""Versioned experiment policy; original shadow policies are never changed."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path

from .safety import SafetyError, integer, number, timestamp


@dataclass(frozen=True)
class Policy:
    version: str = "rs_paper_all_scoreable.v1"
    target_notional: float = 5000
    max_name_notional: float = 50000
    max_gross_notional: float = 150000
    max_names: int = 3
    nav_name_fraction: float = 0.005
    nav_gross_fraction: float = 0.015
    spx_reserve: float | None = None
    cash_buffer: float | None = None
    daily_loss_limit: float | None = None
    squeeze_loss_multiple: float = 2
    margin_stress_multiple: float = 2
    entry_window_seconds: int = 900
    quote_age_seconds: int = 2
    evidence_age_seconds: int = 30
    borrow_age_seconds: int = 1800
    max_borrow_apr: float = 1
    max_spread_bps: float = 100
    depth_fraction: float = 0.1
    stop_fraction: float = 0.2
    hold_sessions: int = 5
    pre_action_exit: bool = True
    max_financial_age_days: int = 200
    max_orders_per_session: int = 20
    entry_order_ttl_seconds: int = 30
    cover_order_ttl_seconds: int = 15
    max_cover_attempts: int = 10
    max_shares_per_order: int = 1000000

    def validate(self):
        for name in (
            "target_notional",
            "max_name_notional",
            "max_gross_notional",
            "cash_buffer",
            "spx_reserve",
            "daily_loss_limit",
            "squeeze_loss_multiple",
            "margin_stress_multiple",
            "max_borrow_apr",
            "max_spread_bps",
            "stop_fraction",
        ):
            number(getattr(self, name), name, minimum=0)
        if not 0 < self.depth_fraction <= 1 or not 0 < self.stop_fraction <= 1:
            raise SafetyError("invalid depth/stop fraction")
        if (
            not 0 < self.nav_name_fraction <= 0.005
            or not 0 < self.nav_gross_fraction <= 0.015
        ):
            raise SafetyError("NAV limits exceed paper safety envelope")
        for name in (
            "max_names",
            "hold_sessions",
            "max_orders_per_session",
            "entry_window_seconds",
            "quote_age_seconds",
            "evidence_age_seconds",
            "borrow_age_seconds",
            "max_financial_age_days",
        ):
            integer(getattr(self, name), name, minimum=1)
        if (
            self.target_notional > self.max_name_notional
            or self.max_name_notional > 50000
        ):
            raise SafetyError("name limit exceeds paper envelope")
        if self.max_gross_notional > 150000 or self.max_names > 3:
            raise SafetyError("portfolio limit exceeds paper envelope")
        if not isinstance(self.pre_action_exit, bool):
            raise SafetyError("pre_action_exit must be boolean")
        if self.spx_reserve <= 0 or self.daily_loss_limit <= 0:
            raise SafetyError("positive SPX reserve and daily loss limit required")
        if self.squeeze_loss_multiple < 2 or self.margin_stress_multiple < 2:
            raise SafetyError("stress multiples may not be below two")
        for name in (
            "entry_order_ttl_seconds",
            "cover_order_ttl_seconds",
            "max_cover_attempts",
            "max_shares_per_order",
        ):
            integer(getattr(self, name), name, minimum=1)
        return self

    @property
    def digest(self):
        return hashlib.sha256(
            json.dumps(asdict(self), sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()


class Calendar:
    def __init__(self, path=None):
        path = (
            path
            or Path(__file__).resolve().parents[3]
            / "dashboard/cloudflare/reverse-split-live/sessions.json"
        )
        self.rows = json.loads(Path(path).read_text(encoding="utf-8"))["sessions"]

    def session(self, now):
        at = timestamp(now)
        return next(
            (
                x
                for x in self.rows
                if timestamp(x["open"]) <= at < timestamp(x["close"])
            ),
            None,
        )

    def exit_at(self, entry_at, sessions):
        current = self.session(entry_at)
        if not current:
            raise SafetyError("entry outside regular session")
        index = self.rows.index(current) + sessions - 1
        if index >= len(self.rows):
            raise SafetyError("calendar coverage missing")
        from datetime import timedelta

        return (
            timestamp(self.rows[index]["close"]) - timedelta(seconds=60)
        ).isoformat()

    def before_action(self, action_day):
        previous = [x for x in self.rows if x["day"] < action_day]
        if not previous:
            raise SafetyError("pre-action calendar coverage missing")
        from datetime import timedelta

        return (timestamp(previous[-1]["close"]) - timedelta(seconds=60)).isoformat()
