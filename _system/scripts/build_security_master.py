#!/usr/bin/env python3
"""Build _system/reference/securities/security_master.json.

Seeds from our book (holdings + watchlist + ticker folders + registry company
names), then harvests Tier-A explicit ticker syntax across the whole letter
corpus so the matcher can see securities beyond our own book. This is what
makes a real cross-fund consensus possible.

No paid data feed required. Optionally enriches names from a local copy of
SEC company_tickers.json if present at _system/reference/securities/sec_company_tickers.json.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

import letter_matching as lm  # noqa: E402
from vault_paths import letters_root  # noqa: E402

LETTERS_ROOT = letters_root()
SECURITIES_DIR = ROOT / "_system" / "reference" / "securities"
MASTER_PATH = SECURITIES_DIR / "security_master.json"
QUARANTINE_PATH = SECURITIES_DIR / "security_master_quarantine.json"
SEC_TICKERS_PATH = SECURITIES_DIR / "sec_company_tickers.json"
REGISTRY_PATH = ROOT / "_system" / "portfolio" / "registry.json"
SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"

MANUAL_ALIASES: dict[str, list[str]] = {
    "GOOGL": ["Google", "Alphabet"],
    "BKRB": ["Berkshire", "Berkshire Hathaway"],
    "0388.HK": ["HKEX", "Hong Kong Exchanges and Clearing", "Hong Kong Exchanges"],
    "8697.T": ["JPX", "Japan Exchange Group"],
    "LSEG": ["London Stock Exchange", "London Stock Exchange Group"],
    "HKHC": ["Horizon Kinetics"],
    "META": ["Meta Platforms", "Facebook"],
    "AMZN": ["Amazon"],
    "NVDA": ["Nvidia"],
    "AMD": ["Advanced Micro Devices"],
    "TSLA": ["Tesla"],
    "TVK": ["TerraVest Industries"],
}


def load_json(path: Path):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def refresh_sec_tickers() -> None:
    """Refresh the official SEC symbol reference used to validate US equities."""
    user_agent = os.environ.get(
        "SEC_USER_AGENT", "Magis Capital research engineering contact@magiscapital.com"
    )
    request = urllib.request.Request(
        SEC_TICKERS_URL,
        headers={"User-Agent": user_agent},
    )
    with urllib.request.urlopen(request, timeout=45) as response:
        raw = response.read()
    # Validate before replacing the local cache.
    payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, dict) or len(payload) < 1000:
        raise RuntimeError("SEC company ticker response failed validation")
    SECURITIES_DIR.mkdir(parents=True, exist_ok=True)
    SEC_TICKERS_PATH.write_text(json.dumps(payload, separators=(",", ":")) + "\n", encoding="utf-8")


def load_book() -> dict[str, dict]:
    """Map known ticker -> {company, in_book}."""
    book: dict[str, dict] = {}
    reg = load_json(REGISTRY_PATH)
    if isinstance(reg, dict):
        for bucket in ("holdings", "watchlist"):
            for tk, meta in (reg.get(bucket) or {}).items():
                book[str(tk).upper()] = {
                    "company": str((meta or {}).get("company") or ""),
                    "in_book": True,
                }
    for p in ROOT.iterdir():
        if not p.is_dir() or p.name.startswith((".", "_")):
            continue
        if (p / "INDEX.csv").exists() or (p / "research" / "valuation.json").exists():
            tk = p.name.upper()
            book.setdefault(tk, {"company": "", "in_book": True})
            book[tk]["in_book"] = True
    return book


def numeric_base(ticker: str) -> str | None:
    base = ticker.split(".", 1)[0]
    if base.isdigit():
        return base.lstrip("0") or base
    return None


def exchange_of(ticker: str) -> str:
    if "." in ticker:
        return ticker.split(".", 1)[1].upper()
    return ""


def company_name_before(text: str, span_start: int) -> str:
    pre = re.sub(r"\s+", " ", text[max(0, span_start - 70):span_start])
    m = re.search(r"((?:[A-Z][A-Za-z&.\-]+\s+){0,4}[A-Z][A-Za-z&.\-]+)\s*[\(\$]?\s*$", pre)
    name = (m.group(1).strip() if m else "")[:80]
    # single-word captures are unreliable ("Software", "AgentForce"); fall back
    # to the ticker for display rather than store a misleading name.
    if len(name.split()) < 2:
        return ""
    return name


# These explicit rules always MINT a new security.
STRONG_HARVEST_RULES = {"dollar", "paren_exch", "exch_prefix", "dotted"}
ALLOWED_DOTTED_SUFFIXES = {
    "HK", "T", "TO", "L", "LS", "AX", "DE", "PA", "AS", "MI", "ST", "HE",
    "OL", "CO", "WA", "SA", "MX", "NS", "KL", "SI", "BK", "TW", "KS",
}

MANUAL_SECURITY_METADATA: dict[str, dict] = {
    # LandBridge began trading under LB in 2024.  Earlier LB references belong
    # to L Brands and must not overlap the current portfolio security.
    "LB": {"valid_from": "2024-06-28"},
}
CANONICAL_SYMBOL_OVERRIDES = {
    "ACHC.O": "ACHC",  # Reuters venue suffix
    "HKCH": "HKHC",    # recurring OCR/transposition for Horizon Kinetics
    "TVK.TO": "TVK",   # letter convention uses TSE:TVK
}


def canonical_harvest_symbol(symbol: str) -> str:
    canon = symbol.upper().replace("-", ".")
    canon = CANONICAL_SYMBOL_OVERRIDES.get(canon, canon)
    if canon.endswith((".O", ".N")):
        canon = canon.rsplit(".", 1)[0]
    return canon


def paren_company_is_real(text: str, span_start: int, symbol: str) -> bool:
    """Guard for harvesting ``Company Name (TICKER)`` while rejecting prose
    acronym definitions, country tags, and benchmark indices.

    Requires only one preceding capitalized company word so list-style mentions
    like ``Broadcom (AVGO), Ciena (CIEN)`` are captured; precision is carried by
    the acronym test, benchmark-word/code filters, and plausibility gate."""
    return lm.parenthetical_is_ticker(text, span_start, symbol, min_words=1)


def skip_harvest_symbol(canon: str, master: dict[str, dict]) -> bool:
    """Reject junk harvest candidates (sentence initials, digit-leading labels,
    numeric foreign tickers already present in the book under a padded form)."""
    if not canon or canon[0].isdigit():
        return True
    if lm.is_benchmark(canon):
        return True
    if not lm.plausible_harvest_symbol(canon):
        return True
    if "." in canon:
        base, suffix = canon.split(".", 1)
        if suffix not in ALLOWED_DOTTED_SUFFIXES:
            return True
        if base.isalpha() and len(base) < 2:
            return True  # e.g. "A.B", "A.T" sentence initials
        if base.isdigit():
            nb = base.lstrip("0") or base
            for tk, meta in master.items():
                if exchange_of(tk) == suffix.upper() and (meta.get("numeric_base") == nb):
                    return True  # dedupe 388.HK against book 0388.HK
    return False


def scan_letters() -> list[Path]:
    files: list[Path] = []
    for ext in ("*.txt", "*.md"):
        files.extend(LETTERS_ROOT.rglob(ext))
    return sorted({f.resolve() for f in files})


def build() -> dict:
    book = load_book()
    master: dict[str, dict] = {}

    for ticker, meta in book.items():
        aliases = list(MANUAL_ALIASES.get(ticker, []))
        master[ticker] = {
            "name": meta.get("company") or ticker,
            "exchange": exchange_of(ticker),
            "aliases": aliases,
            "numeric_base": numeric_base(ticker),
            "is_word_collision": lm.is_word_collision(ticker),
            "in_book": True,
            "source": "book",
            "entity_type": "equity",
            "validation_status": "manual",
            **MANUAL_SECURITY_METADATA.get(ticker, {}),
        }

    # ensure manual-alias-only tickers exist even if not in book
    for ticker, aliases in MANUAL_ALIASES.items():
        if ticker not in master:
            master[ticker] = {
                "name": aliases[0] if aliases else ticker,
                "exchange": exchange_of(ticker),
                "aliases": list(aliases),
                "numeric_base": numeric_base(ticker),
                "is_word_collision": lm.is_word_collision(ticker),
                "in_book": False,
                "source": "manual",
                "entity_type": "equity",
                "validation_status": "manual",
                **MANUAL_SECURITY_METADATA.get(ticker, {}),
            }

    sec = load_json(SEC_TICKERS_PATH)
    sec_by_symbol: dict[str, str] = {}
    if isinstance(sec, dict):
        for row in sec.values():
            if isinstance(row, dict) and row.get("ticker"):
                sec_by_symbol[str(row["ticker"]).upper()] = str(row.get("title") or "")

    # harvest explicit symbols from corpus
    harvested = 0
    harvested_names: dict[str, str] = {}
    for path in scan_letters():
        text = path.read_text(encoding="utf-8", errors="ignore")
        for hit in lm.extract_explicit_symbols(text):
            sym = hit["symbol"]
            if hit["numeric"]:
                continue  # numeric harvest needs an exchange-qualified canonical ticker we can't infer
            if hit["rule"] not in STRONG_HARVEST_RULES:
                if hit["rule"] == "paren_company" and paren_company_is_real(text, hit["span"][0], sym):
                    pass  # guarded company-paren harvest
                else:
                    continue  # weak parenthetical rules mint acronym junk
            canon = canonical_harvest_symbol(sym)
            if skip_harvest_symbol(canon, master):
                continue
            # if it resolves to an existing book symbol, skip
            existing = None
            for tk in master:
                if tk == canon or tk.split(".", 1)[0] == canon:
                    existing = tk
                    break
            if existing:
                continue
            if canon in master:
                continue
            name = sec_by_symbol.get(canon) or company_name_before(text, hit["span"][0])
            if name and len(name) > len(harvested_names.get(canon, "")):
                harvested_names[canon] = name
            if canon not in master:
                syntax_validated = (
                    "." in canon
                    and canon.split(".", 1)[1] in ALLOWED_DOTTED_SUFFIXES
                    and hit["rule"] == "dotted"
                )
                validated = canon in sec_by_symbol or syntax_validated
                master[canon] = {
                    "name": harvested_names.get(canon) or canon,
                    "exchange": exchange_of(canon),
                    "aliases": [],
                    "numeric_base": numeric_base(canon),
                    "is_word_collision": lm.is_word_collision(canon),
                    "in_book": False,
                    "source": "harvested",
                    "entity_type": "equity" if validated else "unvalidated",
                    "validation_status": "validated" if validated else "quarantined",
                }
                harvested += 1
            else:
                if harvested_names.get(canon) and master[canon]["name"] in ("", canon):
                    master[canon]["name"] = harvested_names[canon]

    # backfill any name improvements for harvested tickers
    for canon, name in harvested_names.items():
        if canon in master and master[canon].get("source") == "harvested" and name:
            master[canon]["name"] = name

    payload = dict(sorted(master.items()))
    SECURITIES_DIR.mkdir(parents=True, exist_ok=True)
    MASTER_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    quarantined = {
        ticker: meta
        for ticker, meta in payload.items()
        if meta.get("validation_status") == "quarantined"
    }
    QUARANTINE_PATH.write_text(json.dumps(quarantined, indent=2) + "\n", encoding="utf-8")
    in_book = sum(1 for v in master.values() if v.get("in_book"))
    validated = sum(1 for v in master.values() if v.get("validation_status") in {"validated", "manual"})
    print(
        f"Wrote {MASTER_PATH.relative_to(ROOT)}: {len(master)} securities "
        f"({in_book} in-book, {validated} validated/manual, "
        f"{len(quarantined)} quarantined, {harvested} harvested from letters)"
    )
    return payload


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh-sec", action="store_true")
    args = parser.parse_args()
    if args.refresh_sec or not SEC_TICKERS_PATH.exists():
        refresh_sec_tickers()
    build()
