"""Shared insider Form 4 parse + Insider Conviction Score (ICS) logic."""
from __future__ import annotations

import csv
import gzip
import json
import math
import re
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
INSIDER_DIR = ROOT / "_system" / "reference" / "market-data" / "insider"
CONFIG_PATH = SCRIPTS / "insider_config.json"
DOMAIN_PATH = SCRIPTS / "insider_domain_map.json"
US_CONFIG = SCRIPTS / "us_ticker_config.json"
SEC_UA = "MarvinResearch/1.0 (marvin@oakcliff-capital.com)"
TODAY = date.today().isoformat()

DISCLAIMER = (
    "Context only. Insider activity informs scenario confidence and stance discussion; "
    "it does not auto-inflate Lawrence base IRR. Promotion requires [HUMAN REVIEW]."
)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def cik_for_ticker(ticker: str) -> str | None:
    cfg = load_json(US_CONFIG)
    entry = cfg.get(ticker.upper()) or cfg.get(ticker)
    if isinstance(entry, dict) and entry.get("cik"):
        return str(int(entry["cik"]))
    return None


def _http_get(url: str, timeout: int = 45) -> str | None:
    req = urllib.request.Request(url, headers={"User-Agent": SEC_UA})
    try:
        raw = urllib.request.urlopen(req, timeout=timeout).read()
        if raw[:2] == b"\x1f\x8b":
            raw = gzip.decompress(raw)
        return raw.decode("utf-8", errors="ignore")
    except Exception:
        return None


def _xml_text(parent: ET.Element | None, path: str) -> str | None:
    if parent is None:
        return None
    el = parent.find(path)
    if el is None:
        return None
    val = el.find("value")
    if val is not None and (val.text or "").strip():
        return val.text.strip()
    return (el.text or "").strip() or None


def _name_tokens(name: str) -> set[str]:
    return {t for t in re.sub(r"[^A-Za-z\s]", " ", name.upper()).split() if t and t not in {"JR", "SR", "III", "II"}}


def names_match(config_name: str, insider_name: str) -> bool:
    if _normalize_name(config_name) == _normalize_name(insider_name):
        return True
    a, b = _name_tokens(config_name), _name_tokens(insider_name)
    if not a or not b:
        return False
    if a == b:
        return True
    # Last-name + first-name overlap (handles "NOLAN PETER J" vs "Peter J. Nolan")
    shared = a & b
    return len(shared) >= 2 or (len(shared) >= 1 and len(a) <= 2 and len(b) <= 2)


def list_form4_filings(cik: str, limit: int = 80) -> list[dict]:
    cik_padded = f"{int(cik):010d}"
    url = f"https://data.sec.gov/submissions/CIK{cik_padded}.json"
    raw = _http_get(url)
    if not raw:
        return []
    j = json.loads(raw)
    recent = j.get("filings", {}).get("recent") or {}
    forms = recent.get("form") or []
    out: list[dict] = []
    cik_path = str(int(cik))
    for i in range(len(forms)):
        if forms[i] not in ("4", "4/A"):
            continue
        out.append({
            "filing_date": recent["filingDate"][i],
            "accession": recent["accessionNumber"][i],
            "primary": recent["primaryDocument"][i],
            "cik_path": cik_path,
        })
        if len(out) >= limit:
            break
    return out


def _normalize_name(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip().upper())


def parse_form4_html(html: str, meta: dict) -> list[dict]:
    """Extract non-derivative transactions from SEC Form 4 HTML."""
    name_m = re.search(
        r"Name and Address of Reporting Person.*?<a[^>]*>([^<]+)</a>",
        html,
        re.S | re.I,
    )
    if not name_m:
        name_m = re.search(r"Reporting Owner.*?<td[^>]*>([A-Z][^<]{2,60})</td>", html, re.S)
    insider = (name_m.group(1) if name_m else "UNKNOWN").strip()

    rel_m = re.search(r"Officer \(give title below\).*?FormData[^>]*>([^<]+)</span>", html, re.S | re.I)
    is_director = bool(re.search(r"Director</td>\s*<td[^>]*>.*?X", html, re.S | re.I))
    is_officer = bool(re.search(r"Officer</td>\s*<td[^>]*>.*?X", html, re.S | re.I))
    is_ten = bool(re.search(r"10% Owner</td>\s*<td[^>]*>.*?X", html, re.S | re.I))
    title = (rel_m.group(1).strip() if rel_m else "") or ""

    footnotes = " ".join(re.findall(r'class="FootnoteData[^"]*">([^<]+)', html))
    is_10b5_1 = bool(re.search(r"10b5-1|Rule 10b5|planned sale", footnotes + html, re.I))
    is_proposed = bool(re.search(r"proposed sale", html, re.I))

    spans = re.findall(r'<span class="FormData[^"]*">([^<]+)</span>', html)
    txs: list[dict] = []
    i = 0
    while i < len(spans):
        if spans[i] != "Common Stock":
            i += 1
            continue
        i += 1
        if i >= len(spans):
            break
        tx_date = spans[i]
        i += 1
        if i >= len(spans) or not re.match(r"[\d,]+$", spans[i]):
            continue
        shares_s = spans[i].replace(",", "")
        i += 1
        if i >= len(spans) or spans[i] not in ("A", "D"):
            continue
        ad_code = spans[i]
        i += 1
        if i >= len(spans):
            break
        try:
            price = float(spans[i].replace(",", ""))
        except ValueError:
            i += 1
            continue
        i += 1
        shares_after = None
        if i < len(spans) and re.match(r"[\d,]+$", spans[i]):
            try:
                shares_after = int(spans[i].replace(",", ""))
            except ValueError:
                shares_after = None
            i += 1
        try:
            shares = int(float(shares_s))
        except ValueError:
            continue
        if not re.match(r"\d{2}/\d{2}/\d{4}", tx_date):
            continue
        txs.append({
            "insider": insider,
            "title": title,
            "is_director": is_director,
            "is_officer": is_officer,
            "is_ten_pct_owner": is_ten,
            "transaction_date": _mdy_to_iso(tx_date),
            "filing_date": meta.get("filing_date"),
            "shares": shares,
            "price": price,
            "value_usd": round(shares * price, 2),
            "acquired_disposed": ad_code,
            "transaction_code": "P" if ad_code == "A" else "S",
            "shares_owned_after": shares_after,
            "is_10b5_1": is_10b5_1,
            "is_proposed_sale": is_proposed,
            "accession": meta.get("accession"),
            "source_path": meta.get("source_path"),
        })
    return txs


def parse_form4_xml(xml: str, meta: dict) -> list[dict]:
    """Extract non-derivative transactions from Form 4 ownershipDocument XML."""
    try:
        root = ET.fromstring(xml.strip())
    except ET.ParseError:
        return []
    if root.tag != "ownershipDocument" and not root.find(".//ownershipDocument"):
        if root.find(".//nonDerivativeTransaction") is None:
            return []
    doc = root if root.tag == "ownershipDocument" else root.find(".//ownershipDocument")
    if doc is None:
        doc = root

    insider = _xml_text(doc, ".//rptOwnerName") or "UNKNOWN"
    rel = doc.find(".//reportingOwnerRelationship")
    is_director = (_xml_text(rel, "isDirector") or "0") == "1"
    is_officer = (_xml_text(rel, "isOfficer") or "0") == "1"
    is_ten = (_xml_text(rel, "isTenPercentOwner") or "0") == "1"
    title = _xml_text(rel, "officerTitle") or ""
    is_10b5_1 = (_xml_text(doc, "aff10b5One") or "0") == "1"

    txs: list[dict] = []
    for tx in doc.findall(".//nonDerivativeTransaction"):
        tx_date = _xml_text(tx, "transactionDate")
        if not tx_date:
            continue
        shares_s = _xml_text(tx, ".//transactionShares")
        price_s = _xml_text(tx, ".//transactionPricePerShare")
        ad_code = _xml_text(tx, ".//transactionAcquiredDisposedCode")
        if not shares_s or not ad_code:
            continue
        try:
            shares = int(float(shares_s.replace(",", "")))
            price = float(price_s.replace(",", "")) if price_s else 0.0
        except ValueError:
            continue
        after_s = _xml_text(tx, ".//sharesOwnedFollowingTransaction")
        shares_after = int(float(after_s.replace(",", ""))) if after_s else None
        txs.append({
            "insider": insider,
            "title": title,
            "is_director": is_director,
            "is_officer": is_officer,
            "is_ten_pct_owner": is_ten,
            "transaction_date": tx_date[:10],
            "filing_date": meta.get("filing_date"),
            "shares": shares,
            "price": price,
            "value_usd": round(shares * price, 2),
            "acquired_disposed": ad_code,
            "transaction_code": "P" if ad_code == "A" else "S",
            "shares_owned_after": shares_after,
            "is_10b5_1": is_10b5_1,
            "is_proposed_sale": False,
            "accession": meta.get("accession"),
            "source_path": meta.get("source_path"),
        })
    return txs


def parse_form4_submission(text: str, meta: dict) -> list[dict]:
    """Parse all ownershipDocument XML blocks inside a full SEC submission .txt."""
    txs: list[dict] = []
    for block in re.findall(r"<XML>\s*(.*?)\s*</XML>", text, re.S | re.I):
        if "ownershipDocument" not in block:
            continue
        txs.extend(parse_form4_xml(block, meta))
    if txs:
        return txs
    if "<span class=\"FormData\"" in text:
        return parse_form4_html(text, meta)
    return []


def _mdy_to_iso(mdy: str) -> str:
    try:
        return datetime.strptime(mdy, "%m/%d/%Y").date().isoformat()
    except ValueError:
        return mdy


def role_weight(tx: dict, cfg: dict) -> float:
    rw = cfg.get("role_weights") or {}
    title = (tx.get("title") or "").lower()
    if tx.get("is_ten_pct_owner"):
        return float(rw.get("ten_pct_owner", 1.3))
    if "chief executive" in title or title.strip() == "ceo":
        return float(rw.get("ceo", 1.1))
    if "chief financial" in title or "cfo" in title or "treasurer" in title:
        return float(rw.get("cfo", 0.85)) if tx.get("transaction_code") == "S" else float(rw.get("officer_buy", 0.9))
    if "chair" in title:
        return float(rw.get("chair", 1.15))
    if tx.get("is_director") and not tx.get("is_officer"):
        return float(rw.get("director", 1.0))
    if tx.get("is_officer"):
        return float(rw.get("officer_buy" if tx.get("acquired_disposed") == "A" else "officer_sell", 0.9))
    return float(rw.get("other", 0.8))


def domain_multiplier(ticker: str, insider: str, domain_cfg: dict) -> float:
    tk = domain_cfg.get("tickers", {}).get(ticker.upper()) or {}
    insiders = tk.get("insiders") or {}
    for key, spec in insiders.items():
        if names_match(key, insider):
            return float(spec.get("domain_multiplier", 1.0))
    return 1.0


def transaction_type_weight(tx: dict, cfg: dict) -> float:
    tw = cfg.get("transaction_weights") or {}
    if tx.get("is_proposed_sale"):
        return float(tw.get("planned_sale", -0.05))
    if tx.get("is_10b5_1") and tx.get("acquired_disposed") == "D":
        return float(tw.get("planned_sale", -0.05))
    if tx.get("acquired_disposed") == "A":
        return float(tw.get("buy_A", 1.0))
    return float(tw.get("sell_D", -0.25))


def conviction_delta(tx: dict) -> float:
    after = tx.get("shares_owned_after")
    shares = tx.get("shares") or 0
    if after and after > shares and tx.get("acquired_disposed") == "A":
        before = after - shares
        if before > 0:
            pct = shares / before
            return min(2.0, math.log10(1.0 + 100.0 * pct))
    return 0.3


def dollar_materiality(value_usd: float) -> float:
    if value_usd <= 0:
        return 0.0
    return min(1.5, math.log10(1.0 + value_usd / 10_000.0))


def recency_decay(tx_date: str, half_life: float, floor: float = 0.45) -> float:
    try:
        td = datetime.strptime(tx_date[:10], "%Y-%m-%d").date()
        days = max(0, (date.today() - td).days)
        return max(floor, math.exp(-days / half_life))
    except ValueError:
        return 0.5


def price_edge(buy_price: float, spot: float | None) -> float:
    if not spot or spot <= 0 or not buy_price or buy_price <= 0:
        return 0.0
    if buy_price >= spot:
        return 0.25
    gap = (spot - buy_price) / buy_price
    if gap > 0.10:
        return -0.15
    return 0.0


def cluster_bonus(txs: list[dict], cfg: dict) -> float:
    buys = [t for t in txs if t.get("acquired_disposed") == "A"]
    if len(buys) < 2:
        return 0.0
    window = int(cfg.get("cluster_window_days", 14))
    dates = sorted(datetime.strptime(t["transaction_date"][:10], "%Y-%m-%d").date() for t in buys)
    insiders = {t["insider"] for t in buys}
    if len(insiders) >= 2:
        span = (dates[-1] - dates[0]).days
        if span <= window:
            return float(cfg.get("cluster_bonus_2_insiders", 0.4))
    if len(buys) >= 3 and (dates[-1] - dates[0]).days <= window:
        return float(cfg.get("cluster_bonus_3_events", 0.6))
    return 0.0


def score_transactions(
    ticker: str,
    txs: list[dict],
    spot: float | None,
    cfg: dict | None = None,
    domain_cfg: dict | None = None,
) -> dict:
    cfg = cfg or load_json(CONFIG_PATH)
    domain_cfg = domain_cfg or load_json(DOMAIN_PATH)
    half_life = float(cfg.get("recency_half_life_days", 120))
    recency_floor = float(cfg.get("recency_floor", 0.45))
    sale_cap = float(cfg.get("sale_negative_cap", 1.0))

    buy_score = 0.0
    sell_score = 0.0
    scored_rows: list[dict] = []

    for tx in txs:
        if tx.get("acquired_disposed") == "A":
            # Open-market buys only; skip grants/awards with no price.
            if not tx.get("price") or float(tx.get("price") or 0) <= 0:
                continue
            base = transaction_type_weight(tx, cfg)
            if base <= 0:
                continue
            rw = role_weight(tx, cfg)
            dm = domain_multiplier(ticker, tx["insider"], domain_cfg)
            cd = conviction_delta(tx)
            dm_usd = dollar_materiality(tx.get("value_usd") or 0)
            rec = recency_decay(tx["transaction_date"], half_life, recency_floor)
            pe = price_edge(tx.get("price") or 0, spot)
            contrib = base * rw * dm * (1.0 + cd + dm_usd) * rec * (1.0 + pe)
            buy_score += contrib
            scored_rows.append({**tx, "contrib": round(contrib, 3), "kind": "buy"})
        elif tx.get("acquired_disposed") == "D":
            base = transaction_type_weight(tx, cfg)
            rw = role_weight(tx, cfg)
            rec = recency_decay(tx["transaction_date"], half_life, recency_floor)
            contrib = base * rw * rec
            sell_score += contrib
            scored_rows.append({**tx, "contrib": round(contrib, 3), "kind": "sell"})

    sell_score = max(sell_score, -sale_cap)
    cluster = cluster_bonus(txs, cfg)
    raw = buy_score + sell_score + cluster
    ics = max(0.0, min(10.0, round(raw * 1.15, 2)))

    band = "negligible"
    for b in cfg.get("ics_bands") or []:
        if ics <= float(b.get("max", 10)):
            band = b.get("label", band)
            break

    net_buy = sum(t.get("value_usd") or 0 for t in txs if t.get("acquired_disposed") == "A")
    net_sell = sum(t.get("value_usd") or 0 for t in txs if t.get("acquired_disposed") == "D")

    scenario = scenario_confidence(ics, net_buy, net_sell, cfg)
    bull_support = bull_case_support_level(ics, txs, domain_cfg, ticker)

    return {
        "ics": ics,
        "band": band,
        "buy_score": round(buy_score, 3),
        "sell_score": round(sell_score, 3),
        "cluster_bonus": cluster,
        "net_buy_usd": round(net_buy, 2),
        "net_sell_usd": round(net_sell, 2),
        "scenario_confidence": scenario,
        "bull_case_support": bull_support,
        "transactions_scored": scored_rows,
    }


def scenario_confidence(ics: float, net_buy: float, net_sell: float, cfg: dict) -> dict:
    priors = cfg.get("scenario_priors") or {"bear": 0.2, "base": 0.55, "bull": 0.25}
    tilt_cfg = cfg.get("scenario_tilt") or {}
    bull_delta = min(
        float(tilt_cfg.get("bull_cap", 0.15)),
        float(tilt_cfg.get("bull_per_ics_point_above_4", 0.025)) * max(0.0, ics - 4.0),
    )
    bear_delta = 0.0
    if net_sell > net_buy * 2 and ics < 4:
        bear_delta = min(
            float(tilt_cfg.get("bear_cap", 0.1)),
            float(tilt_cfg.get("bear_per_ics_point_below_4", 0.02)) * max(0.0, 4.0 - ics),
        )
    weights = {
        "bear": priors.get("bear", 0.2) + bear_delta,
        "base": priors.get("base", 0.55) - bull_delta - bear_delta,
        "bull": priors.get("bull", 0.25) + bull_delta,
    }
    total = sum(weights.values()) or 1.0
    weights = {k: round(v / total, 3) for k, v in weights.items()}
    return {
        "priors": priors,
        "tilted": weights,
        "bull_delta": round(bull_delta, 3),
        "bear_delta": round(bear_delta, 3),
        "note": "Scenario weights are qualitative confidence only; Lawrence base IRR unchanged.",
    }


def bull_case_support_level(ics: float, txs: list[dict], domain_cfg: dict, ticker: str) -> str:
    domain_mult_max = 1.0
    for tx in txs:
        if tx.get("acquired_disposed") == "A":
            domain_mult_max = max(domain_mult_max, domain_multiplier(ticker, tx["insider"], domain_cfg))
    if ics >= 8 and domain_mult_max >= 2.0:
        return "exceptional"
    if ics >= 6 and domain_mult_max >= 1.5:
        return "strong"
    if ics >= 4:
        return "moderate"
    return "none"


def fetch_transactions_for_ticker(ticker: str, window_days: int = 365) -> list[dict]:
    cik = cik_for_ticker(ticker)
    if not cik:
        return []
    cutoff = date.today() - timedelta(days=window_days)
    filings = list_form4_filings(cik, limit=100)
    all_txs: list[dict] = []
    for f in filings:
        try:
            fd = datetime.strptime(f["filing_date"][:10], "%Y-%m-%d").date()
        except ValueError:
            continue
        if fd < cutoff:
            continue
        nodash = f["accession"].replace("-", "")
        sub_url = f"https://www.sec.gov/Archives/edgar/data/{f['cik_path']}/{nodash}/{f['accession']}.txt"
        meta = {
            "filing_date": f["filing_date"],
            "accession": f["accession"],
            "source_path": sub_url,
        }
        content = _http_get(sub_url)
        if content:
            parsed = parse_form4_submission(content, meta)
            if parsed:
                all_txs.extend(parsed)
                time.sleep(0.12)
                continue
        doc_url = f"https://www.sec.gov/Archives/edgar/data/{f['cik_path']}/{nodash}/{f['primary']}"
        html = _http_get(doc_url)
        if not html:
            continue
        meta["source_path"] = doc_url
        all_txs.extend(parse_form4_html(html, meta))
        time.sleep(0.12)
    return all_txs


def write_transactions_csv(ticker: str, txs: list[dict]) -> Path:
    INSIDER_DIR.mkdir(parents=True, exist_ok=True)
    path = INSIDER_DIR / f"{ticker.upper()}_transactions.csv"
    fields = [
        "insider", "title", "transaction_date", "filing_date", "shares", "price",
        "value_usd", "acquired_disposed", "transaction_code", "shares_owned_after",
        "is_10b5_1", "is_director", "is_officer", "accession", "source_path",
    ]
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for tx in sorted(txs, key=lambda t: (t.get("transaction_date") or "", t.get("insider") or ""), reverse=True):
            w.writerow(tx)
    return path


def read_transactions_csv(ticker: str) -> list[dict]:
    path = INSIDER_DIR / f"{ticker.upper()}_transactions.csv"
    if not path.exists():
        return []
    rows: list[dict] = []
    with path.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            for key in ("shares", "shares_owned_after"):
                if row.get(key):
                    try:
                        row[key] = int(float(row[key]))
                    except ValueError:
                        pass
            for key in ("price", "value_usd"):
                if row.get(key):
                    try:
                        row[key] = float(row[key])
                    except ValueError:
                        pass
            for key in ("is_10b5_1", "is_director", "is_officer"):
                if key in row:
                    row[key] = str(row[key]).lower() in ("1", "true", "yes")
            rows.append(row)
    return rows


def update_manifest(ticker: str, txs: list[dict], *, error: str | None = None) -> Path:
    manifest_path = INSIDER_DIR / "manifest.json"
    manifest = load_json(manifest_path)
    manifest.setdefault("tickers", {})
    manifest["as_of"] = TODAY
    buys = [t for t in txs if t.get("acquired_disposed") == "A"]
    sells = [t for t in txs if t.get("acquired_disposed") == "D"]
    manifest["tickers"][ticker.upper()] = {
        "as_of": TODAY,
        "transaction_count": len(txs),
        "buy_count": len(buys),
        "sell_count": len(sells),
        "csv": f"insider/{ticker.upper()}_transactions.csv",
        "latest_buy": max((t.get("transaction_date") for t in buys), default=None),
        "error": error,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest_path


def spot_from_valuation(ticker: str) -> float | None:
    vp = ROOT / ticker / "research" / "valuation.json"
    if not vp.exists():
        return None
    try:
        val = load_json(vp)
        p = (val.get("inputs") or {}).get("price")
        return float(p) if p is not None else None
    except (TypeError, ValueError):
        return None


def build_insider_signal(ticker: str, txs: list[dict] | None = None) -> dict | None:
    cfg = load_json(CONFIG_PATH)
    window = int(cfg.get("window_days", 365))
    if txs is None:
        txs = fetch_transactions_for_ticker(ticker, window)
    if not txs:
        return None
    cutoff = (date.today() - timedelta(days=window)).isoformat()
    txs = [t for t in txs if (t.get("transaction_date") or "") >= cutoff]
    if not txs:
        return None
    spot = spot_from_valuation(ticker)
    scored = score_transactions(ticker, txs, spot, cfg)
    top_buys = sorted(
        [t for t in scored["transactions_scored"] if t.get("kind") == "buy"],
        key=lambda x: x.get("contrib", 0),
        reverse=True,
    )[:5]
    top_sells = sorted(
        [t for t in scored["transactions_scored"] if t.get("kind") == "sell"],
        key=lambda x: abs(x.get("contrib", 0)),
        reverse=True,
    )[:5]

    hooks: list[str] = []
    if scored["cluster_bonus"] > 0:
        hooks.append("Multiple insiders bought within cluster window")
    for tb in top_buys[:2]:
        dm = domain_multiplier(ticker, tb["insider"], load_json(DOMAIN_PATH))
        if dm >= 1.5:
            hooks.append(f"{tb['insider']}: domain-relevant open-market buy (×{dm})")

    return {
        "as_of": TODAY,
        "disclaimer": DISCLAIMER,
        "in_base_irr": False,
        "window_days": window,
        "ics": scored["ics"],
        "band": scored["band"],
        "bull_case_support": scored["bull_case_support"],
        "scenario_confidence": scored["scenario_confidence"],
        "factors": {
            "buy_score": scored["buy_score"],
            "sell_score": scored["sell_score"],
            "cluster_bonus": scored["cluster_bonus"],
            "net_buy_usd": scored["net_buy_usd"],
            "net_sell_usd": scored["net_sell_usd"],
            "price_today": spot,
        },
        "top_buys": [
            {
                "insider": t["insider"],
                "date": t["transaction_date"],
                "shares": t["shares"],
                "price": t["price"],
                "value_usd": t["value_usd"],
                "shares_owned_after": t.get("shares_owned_after"),
                "contrib": t.get("contrib"),
            }
            for t in top_buys
        ],
        "top_sells": [
            {
                "insider": t["insider"],
                "date": t["transaction_date"],
                "shares": t["shares"],
                "price": t["price"],
                "value_usd": t["value_usd"],
                "is_10b5_1": t.get("is_10b5_1"),
                "contrib": t.get("contrib"),
            }
            for t in top_sells
        ],
        "narrative_hooks": hooks,
        "transaction_count": len(txs),
    }
