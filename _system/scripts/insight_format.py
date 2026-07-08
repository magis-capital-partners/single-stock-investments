"""Shared helpers for ticker insight selection and letter display formatting."""
from __future__ import annotations

import re

PORTFOLIO_WIDE_SOURCES = frozenset({"macro", "theme"})

OWNERSHIP_SOURCES = frozenset({"superinvestor_letter", "insider", "specialist_13f"})

TICKER_SPECIFIC_SOURCES = frozenset(
    {
        "superinvestor_letter",
        "insider",
        "specialist_13f",
        "filing",
        "news",
        "third_party",
        "sumzero_research",
        "earnings",
    }
)

ACTION_LABELS = {
    "add": "added",
    "trim": "trimmed",
    "new": "initiated",
    "short": "shorted",
    "discussed": "discussed",
    "hold": "holds",
}


def is_portfolio_wide(row: dict) -> bool:
    return row.get("source") in PORTFOLIO_WIDE_SOURCES


def is_ticker_specific(row: dict) -> bool:
    return row.get("source") in TICKER_SPECIFIC_SOURCES


def split_insight_rows(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    specific = [r for r in rows if is_ticker_specific(r)]
    portfolio = [r for r in rows if is_portfolio_wide(r)]
    return specific, portfolio


def is_letter_table_debris(text: str) -> bool:
    """Detect OCR/table dumps (percent grids, ticker lists) masquerading as commentary."""
    if not text or len(text.strip()) < 24:
        return False
    pct_hits = len(re.findall(r"\(\d{1,3}%\)", text))
    ticker_hits = len(re.findall(r"\b[A-Z][A-Z0-9]{0,4}(?:\.[A-Z]{1,2})?\b", text))
    alpha_ratio = sum(ch.isalpha() for ch in text) / max(len(text), 1)
    if pct_hits >= 3 and ticker_hits >= 4 and len(re.findall(r"[a-z]{4,}", text)) <= 2:
        return True
    if pct_hits >= 4 and ticker_hits >= 6:
        return True
    if pct_hits >= 8:
        return True
    if ticker_hits >= 12 and alpha_ratio < 0.55:
        return True
    return False


def extract_relevant_sentence(text: str, ticker: str, max_len: int = 280) -> str:
    if not text:
        return ""
    clean = re.sub(r"\s+", " ", text.strip())
    tk = str(ticker).upper()
    parts = re.split(r"(?<=[.!?])\s+", clean)
    for sentence in parts:
        upper = sentence.upper()
        if tk in upper or f"TSX:{tk}" in upper or f"{tk}.CN" in upper or f"{tk}.TO" in upper:
            return sentence[:max_len]
    return clean[:max_len]


def format_letter_position(
    *,
    ticker: str,
    fund: str,
    action: str = "discussed",
    quarter: str | None = None,
    letter_date: str | None = None,
    commentary: str = "",
) -> tuple[str, str]:
    action_label = ACTION_LABELS.get(str(action or "discussed"), str(action or "discussed"))
    period = quarter or (str(letter_date)[:7] if letter_date else "")
    title = f"{fund} · {action_label} · {ticker}"
    if period:
        title = f"{title} · {period}"

    if is_letter_table_debris(commentary):
        summary = (
            f"{fund} letter references {ticker} in a holdings or exposure table. "
            "Open the letter extract for the full context."
        )
    elif commentary.strip():
        summary = extract_relevant_sentence(commentary, ticker)
    else:
        summary = f"{fund} {action_label} {ticker} in the latest indexed letter."

    return title, summary[:320]


def format_letter_claim(ticker: str, fund: str, action: str, quarter: str | None, commentary: str) -> str:
    _, summary = format_letter_position(
        ticker=ticker,
        fund=fund,
        action=action,
        quarter=quarter,
        commentary=commentary,
    )
    return summary
