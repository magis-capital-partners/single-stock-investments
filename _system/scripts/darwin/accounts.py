"""Per-account paths and mandate loading (Roth IRA vs taxable)."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .config import DATA_DIR, PORTFOLIO_DIR, ROOT

ACCOUNT_IDS = ("roth", "taxable")

MANDATE_FILES = {
    "roth": PORTFOLIO_DIR / "darwin_mandate_roth.json",
    "taxable": PORTFOLIO_DIR / "darwin_mandate_taxable.json",
}


@dataclass(frozen=True)
class AccountCtx:
    account_id: str
    mandate_path: Path
    portfolio_path: Path
    target_weights_path: Path
    backtest_report_path: Path
    paper_state_path: Path
    paper_history_path: Path
    adaptation_log_path: Path


def account_ctx(account_id: str) -> AccountCtx:
    aid = account_id.lower()
    if aid not in ACCOUNT_IDS:
        raise ValueError(f"Unknown account_id {account_id!r}; use one of {ACCOUNT_IDS}")
    return AccountCtx(
        account_id=aid,
        mandate_path=MANDATE_FILES[aid],
        portfolio_path=DATA_DIR / f"darwin_portfolio_{aid}.json",
        target_weights_path=PORTFOLIO_DIR / f"{aid}_target_weights.json",
        backtest_report_path=DATA_DIR / f"darwin_backtest_report_{aid}.md",
        paper_state_path=PORTFOLIO_DIR / "paper" / f"{aid}.json",
        paper_history_path=PORTFOLIO_DIR / "paper" / f"{aid}_history.jsonl",
        adaptation_log_path=PORTFOLIO_DIR / "paper" / f"{aid}_adaptations.jsonl",
    )


def load_mandate_for(account_id: str) -> dict:
    ctx = account_ctx(account_id)
    if not ctx.mandate_path.exists():
        raise FileNotFoundError(ctx.mandate_path)
    return json.loads(ctx.mandate_path.read_text(encoding="utf-8"))


def tier0_production(mandate_doc: dict) -> bool:
    return int(mandate_doc.get("tier", 0)) == 0


def tax_advantaged(mandate_doc: dict) -> bool:
    return (mandate_doc.get("account_profile") or "").lower() in (
        "ira",
        "roth",
        "roth_ira",
        "tax_advantaged",
    )
