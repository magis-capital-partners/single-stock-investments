#!/usr/bin/env python3
"""Harvest public index constituent lists into _system/reference/market-data/index/.

Offline-safe: if network fetch fails, keeps existing files and exits 0 with a note.
Also builds a portfolio-scoped membership seed from known lists + heuristics.
"""
from __future__ import annotations

import argparse
import json
import re
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "_system" / "reference" / "market-data" / "index"
REGISTRY = ROOT / "_system" / "portfolio" / "registry.json"
SEED_PATH = ROOT / "_system" / "data" / "index_memberships_seed.json"
SP500_PATH = OUT_DIR / "sp500_constituents.json"

UA = "Mozilla/5.0 (compatible; MarvinResearch/1.0; +local-dashboard)"


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path, default=None):
    if not path.exists():
        return default if default is not None else {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def fetch_text(url: str, timeout: int = 30) -> str | None:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001
        print(f"WARN: fetch failed {url}: {exc}")
        return None


def parse_wikipedia_tickers(html: str) -> list[str]:
    # Match common wiki table ticker cells / links (classic + Parsoid)
    tickers = set()
    for m in re.finditer(r">([A-Z]{1,5}(?:\.[A-Z])?)</a></td>", html):
        tickers.add(m.group(1))
    for m in re.finditer(r"\b([A-Z]{1,5})\b</td>\s*<td>", html):
        if len(m.group(1)) <= 5:
            tickers.add(m.group(1))
    for m in re.finditer(r"<td><a[^>]*>([A-Z]{1,5})</a></td>", html):
        tickers.add(m.group(1))
    # Parsoid: <td id="mw...">AAPL</td>
    for m in re.finditer(r"<td[^>]*>\s*([A-Z]{1,5}(?:\.[A-Z]{1,2})?)\s*</td>", html):
        sym = m.group(1)
        if 1 <= len(sym) <= 5:
            tickers.add(sym)
    # Drop obvious non-tickers
    stop = {"USD", "CEO", "IPO", "ETF", "USA", "NYSE", "HTML", "HTTP", "JSON", "PDF"}
    return sorted(t for t in tickers if t not in stop)


def harvest_wikipedia(slug: str, out_name: str, source_label: str) -> dict:
    url = f"https://en.wikipedia.org/wiki/{slug}"
    existing = load_json(OUT_DIR / out_name, {})
    html = fetch_text(url)
    if not html:
        if existing:
            print(f"KEEP existing {out_name}")
            return existing
        return {"as_of": date.today().isoformat(), "source": source_label, "count": 0, "tickers": []}
    tickers = parse_wikipedia_tickers(html)
    # Prefer existing if parse looks broken
    if len(tickers) < 20 and existing.get("tickers"):
        print(f"KEEP existing {out_name} (parse too small: {len(tickers)})")
        return existing
    payload = {
        "as_of": date.today().isoformat(),
        "source": source_label,
        "source_url": url,
        "count": len(tickers),
        "tickers": tickers,
        "harvested_at": now_iso(),
    }
    save_json(OUT_DIR / out_name, payload)
    print(f"WROTE {out_name} count={len(tickers)}")
    return payload


def build_seed(registry: dict, constituents: dict[str, set[str]]) -> dict:
    holdings = registry.get("holdings") or {}
    by_ticker: dict[str, dict] = {}
    for ticker, meta in holdings.items():
        memberships: list[str] = []
        exchange = (meta.get("exchange") or "").upper()
        market = meta.get("market") or ""
        company = (meta.get("company") or "").lower()

        for index_id, tickers in constituents.items():
            # Match bare US symbols; also try without suffixes
            bare = ticker.split(".")[0].upper()
            if ticker.upper() in tickers or bare in tickers:
                # Avoid false positives for non-US on US lists unless market US
                if index_id.startswith(("sp", "russell", "nasdaq", "msci_usa")) and market not in (
                    "US",
                    "OTC",
                ):
                    if market != "US":
                        continue
                memberships.append(index_id)

        # Heuristic home-market membership for exchange operators / large locals
        if market == "CA" and exchange == "TSX":
            if "tsx_composite" not in memberships and ticker in {
                "CSU",
                "ALS.TO",
                "PSK.TO",
                "X.TO",
                "ADN.TO",
                "LMN",
            }:
                memberships.append("tsx_composite")
        if market == "JP" and exchange == "TSE":
            if "topix" not in memberships:
                memberships.append("topix")
        if market == "UK" and exchange == "LSE":
            if ticker == "LSEG" and "ftse_100" not in memberships:
                memberships.append("ftse_100")
            if ticker == "RMV.L" and "ftse_250" not in memberships:
                memberships.append("ftse_250")
        if exchange == "HKEX" and "hang_seng" not in memberships:
            memberships.append("hang_seng")
        if exchange == "ASX" and ticker in {"ASX.AX"} and "asx_200" not in memberships:
            memberships.append("asx_200")
        if exchange == "NZX" and "nzx_50" not in memberships:
            memberships.append("nzx_50")
        if exchange == "SGX" and "straits_times" not in memberships:
            memberships.append("straits_times")
        if exchange == "B3" and "ibovespa" not in memberships:
            memberships.append("ibovespa")
        if exchange == "BMV" and "ipc" not in memberships and "fibra" not in company:
            memberships.append("ipc")
        if exchange == "NSE" and "nifty_500" not in memberships:
            memberships.append("nifty_500")
        if exchange in {"XETRA", "EURONEXT PARIS", "LSE"} and market in {"EU", "UK", "SE"}:
            if ticker in {"DB1.DE", "ENX.PA", "LSEG"} and "stoxx_europe_600" not in memberships:
                memberships.append("stoxx_europe_600")

        # Large US mega-caps: also tag msci_usa / russell_1000 when in SP500
        if "sp500" in memberships:
            if "russell_1000" not in memberships:
                memberships.append("russell_1000")
            if "msci_usa" not in memberships:
                memberships.append("msci_usa")
            if "msci_acwi" not in memberships:
                memberships.append("msci_acwi")
        if "nasdaq_100" in memberships and "russell_1000" not in memberships:
            memberships.append("russell_1000")

        by_ticker[ticker] = {
            "memberships": sorted(set(memberships)),
            "source": "constituent_lists_plus_heuristics",
            "as_of": date.today().isoformat(),
        }

    return {
        "as_of": date.today().isoformat(),
        "generated_at": now_iso(),
        "by_ticker": by_ticker,
        "notes": "Human-editable seed; auto-updated when provider-confirmed events pass effective date.",
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true", help="Do not fetch; rebuild seed from local files only")
    args = ap.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    constituents: dict[str, set[str]] = {}

    sp500 = load_json(SP500_PATH, {})
    if sp500.get("tickers"):
        constituents["sp500"] = {t.upper() for t in sp500["tickers"]}

    if not args.offline:
        ndx = harvest_wikipedia("Nasdaq-100", "nasdaq100_constituents.json", "wikipedia_nasdaq_100")
        constituents["nasdaq_100"] = {t.upper() for t in (ndx.get("tickers") or [])}
        # FTSE 100
        ftse = harvest_wikipedia("FTSE_100_Index", "ftse100_constituents.json", "wikipedia_ftse_100")
        constituents["ftse_100"] = {t.upper() for t in (ftse.get("tickers") or [])}
        # STOXX Europe 600 is huge; skip full harvest — membership via heuristics/seed
        # TSX Composite
        tsx = harvest_wikipedia(
            "S%26P/TSX_Composite_Index", "tsx_composite_constituents.json", "wikipedia_tsx_composite"
        )
        # wiki slug may fail; try alternate
        if not (tsx.get("tickers") or []):
            tsx = harvest_wikipedia(
                "S&P/TSX_Composite_Index", "tsx_composite_constituents.json", "wikipedia_tsx_composite"
            )
        constituents["tsx_composite"] = {t.upper() for t in (tsx.get("tickers") or [])}
    else:
        for path, key in (
            (OUT_DIR / "nasdaq100_constituents.json", "nasdaq_100"),
            (OUT_DIR / "ftse100_constituents.json", "ftse_100"),
            (OUT_DIR / "tsx_composite_constituents.json", "tsx_composite"),
        ):
            doc = load_json(path, {})
            if doc.get("tickers"):
                constituents[key] = {t.upper() for t in doc["tickers"]}

    registry = load_json(REGISTRY, {"holdings": {}})
    seed = build_seed(registry, constituents)
    save_json(SEED_PATH, seed)
    print(f"WROTE seed {SEED_PATH} tickers={len(seed.get('by_ticker') or {})}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
