#!/usr/bin/env python3
"""Build dashboard/data/index_membership.json — eligibility scorecards + confirmed events."""
from __future__ import annotations

import argparse
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys_path_insert = str(ROOT / "_system" / "scripts")
import sys

sys.path.insert(0, sys_path_insert)

from index_event_extract import extract_index_events, _is_style_or_subset_index  # noqa: E402
from index_flow_impact import (  # noqa: E402
    attach_float_impact,
    demand_shock_from_float_impact,
    load_aum_registry,
)
from index_market_inputs import load_fundamentals_cache, market_inputs_for_ticker  # noqa: E402

DATA_DIR = ROOT / "_system" / "data"
REF_INDEX = ROOT / "_system" / "reference" / "market-data" / "index"
OUT_PATH = ROOT / "dashboard" / "data" / "index_membership.json"
DOCS_OUT = ROOT / "docs" / "data" / "index_membership.json"
REGISTRY = ROOT / "_system" / "portfolio" / "registry.json"
NEWS_PATH = ROOT / "dashboard" / "data" / "portfolio_news.json"
ANNOUNCEMENTS = DATA_DIR / "index_announcements.jsonl"
REVIEWS_PENDING = ROOT / "_system" / "reviews" / "pending"
REVIEWS_APPROVED = ROOT / "_system" / "reviews" / "approved"

# Review / archive title screen (recall for aged headlines; extract is still the gate)
_ARCHIVE_EVENTISH = re.compile(
    r"(added to|joins? |joining |removed from|deleted from|dropped from|"
    r"reclassif|reshuffl|Top 50|Nasdaq-100 Exit|in the Dow|Russell|"
    r"S&P/TSX|Midcap|Defensive|Index Reclass|index shift|index moves?)",
    re.I,
)
_REVIEW_LINE_RE = re.compile(
    r"\*\*([A-Z0-9.\-]+)\*\*\s*·\s*`([^`]+)`.*?\[([^\]]+)\]",
    re.I,
)
_REVIEW_DATE_RE = re.compile(r"news_(\d{4}-\d{2}-\d{2})\.md")

STATUS_ENUM = {"member", "inclusion_candidate", "deletion_risk", "ineligible", "n_a"}
CONF_ENUM = {"rules_only", "news_unconfirmed", "provider_confirmed"}
INDEX_NEWS_CATEGORIES = {"index_inclusion", "index_addition", "index_deletion"}
DEFAULT_MAX_CANDIDATE_DISTANCE_PCT = 15.0
NASDAQ_EXCLUDE_TICKERS = {"NDAQ", "CBOE", "CME", "ICE", "MIAX", "SPGI", "MCO"}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path, default=None):
    if not path.exists():
        return default if default is not None else {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    m = re.match(r"^(\d{4}-\d{2}-\d{2})", str(value).strip())
    if not m:
        return None
    return date.fromisoformat(m.group(1))


def days_until(d: date | None, today: date) -> int | None:
    if d is None:
        return None
    return (d - today).days


def load_announcements() -> list[dict]:
    if not ANNOUNCEMENTS.exists():
        return []
    rows = []
    for line in ANNOUNCEMENTS.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def append_announcement(row: dict, *, existing: list[dict] | None = None) -> bool:
    """Append if not duplicate (exact key or same triple within 14 days). Returns True if written."""
    ANNOUNCEMENTS.parent.mkdir(parents=True, exist_ok=True)
    rows = existing if existing is not None else load_announcements()
    key = (
        row.get("ticker"),
        row.get("index"),
        row.get("action"),
        row.get("effective") or row.get("announced"),
    )
    ann_d = parse_date(row.get("announced"))
    for e in rows:
        ek = (e.get("ticker"), e.get("index"), e.get("action"), e.get("effective") or e.get("announced"))
        if ek == key:
            return False
        if (
            e.get("ticker") == row.get("ticker")
            and e.get("index") == row.get("index")
            and e.get("action") == row.get("action")
            and ann_d
        ):
            ed = parse_date(e.get("announced") or e.get("effective"))
            if ed and abs((ann_d - ed).days) <= 14:
                return False
    with ANNOUNCEMENTS.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    rows.append(row)
    return True


def rewrite_announcements(rows: list[dict]) -> None:
    ANNOUNCEMENTS.parent.mkdir(parents=True, exist_ok=True)
    body = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
    ANNOUNCEMENTS.write_text(body, encoding="utf-8")


def memberships_lookup(seed: dict) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for t, entry in (seed.get("by_ticker") or {}).items():
        out[t] = set(entry.get("memberships") or [])
    return out


def harvest_news_announcements(
    news_doc: dict,
    today: date,
    *,
    seed: dict,
    company_names: dict[str, str],
    purge: bool = False,
) -> list[dict]:
    """Subject-gated harvest. Precision over recall; no default index/action."""
    harvested: list[dict] = []
    existing: list[dict] = [] if purge else load_announcements()
    # Keep provider_confirmed rows across purge
    if purge:
        existing = [e for e in load_announcements() if e.get("confidence") == "provider_confirmed"]
        rewrite_announcements(existing)

    for item in news_doc.get("items") or news_doc.get("articles") or news_doc.get("news") or []:
        title = item.get("title") or ""
        summary = item.get("summary") or ""
        tickers = item.get("tickers") or ([item.get("ticker")] if item.get("ticker") else [])
        tickers = [t for t in tickers if t]
        if not tickers:
            continue
        # Subject extract is the gate. Any category may contribute if extract matches
        # (Copart reclass headlines often land in management).
        announced = item.get("published_utc") or item.get("published") or item.get("date") or today.isoformat()
        announced = str(announced)[:10]
        harvested.extend(
            _try_append_extracted(
                title=title,
                summary=summary,
                tickers=tickers,
                company_names=company_names,
                announced=announced,
                source_url=item.get("url") or item.get("link"),
                source_type="news",
                seed=seed,
                existing=existing,
            )
        )
    return harvested


def _try_append_extracted(
    *,
    title: str,
    summary: str,
    tickers: list[str],
    company_names: dict[str, str],
    announced: str,
    source_url: str | None,
    source_type: str,
    seed: dict,
    existing: list[dict],
) -> list[dict]:
    """Run subject extract + membership gates; append quality-gated rows. Returns new rows."""
    mem = memberships_lookup(seed)
    events = extract_index_events(
        title,
        summary,
        candidate_tickers=tickers,
        company_names={t: company_names.get(t, "") for t in tickers},
    )
    out: list[dict] = []
    for ev in events:
        ticker = ev["ticker"]
        index_id = ev["index"]
        action = ev["action"]
        current = mem.get(ticker) or set()
        if action == "delete" and index_id not in current:
            if not re.search(r"\b(exit|removed|deleted|dropped)\b", title, re.I):
                continue
        style_subset = bool(ev.get("style_subset")) or (
            action == "reclassify" and _is_style_or_subset_index(title)
        )
        row = {
            "ticker": ticker,
            "index": index_id,
            "action": action,
            "announced": announced,
            "effective": None,
            "source_url": source_url,
            "source_type": source_type,
            "confidence": "news_unconfirmed",
            "title": title,
            "style_subset": style_subset,
            # Style/factor subset moves are tracked but never Confirmed parent events
            "quality_gated": (not style_subset)
            and not (action == "reclassify" and _is_style_or_subset_index(title)),
        }
        if append_announcement(row, existing=existing):
            out.append(row)
    return out


def lint_announcement_conflicts(rows: list[dict], seed: dict | None = None) -> list[str]:
    """Return human-readable warnings for impossible parent membership pairs."""
    from collections import defaultdict

    warnings: list[str] = []
    by_key: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        if not r.get("quality_gated") and r.get("confidence") != "provider_confirmed":
            continue
        key = (r.get("ticker"), r.get("index"), r.get("announced") or r.get("effective"))
        by_key[key].append(r)
    for key, evs in by_key.items():
        actions = {e.get("action") for e in evs}
        if "add" in actions and "delete" in actions:
            warnings.append(
                f"conflict add+delete for {key[0]} / {key[1]} on {key[2]}"
            )
    by_add: dict[tuple, set[str]] = defaultdict(set)
    for r in rows:
        if r.get("action") != "add":
            continue
        if not r.get("quality_gated") and r.get("confidence") != "provider_confirmed":
            continue
        by_add[(r.get("ticker"), r.get("announced"))].add(r.get("index"))
    mutex = [
        {"russell_1000", "russell_2000"},
        {"ftse_100", "ftse_250"},
        {"sp500", "sp400"},
        {"sp500", "sp600"},
        {"sp400", "sp600"},
    ]
    for key, idxs in by_add.items():
        for pair in mutex:
            if pair.issubset(idxs):
                warnings.append(
                    f"mutex dual-add {key[0]} on {key[1]}: {sorted(pair)}"
                )
    mem = memberships_lookup(seed) if seed else {}
    for r in rows:
        t = r.get("ticker")
        idx = r.get("index")
        if (
            r.get("action") == "add"
            and t
            and idx
            and idx in (mem.get(t) or set())
            and (r.get("quality_gated") or r.get("confidence") == "provider_confirmed")
        ):
            warnings.append(f"add targets already-member {t} / {idx}")
        if r.get("action") == "reclassify" and not r.get("style_subset"):
            title = r.get("title") or ""
            if not re.search(
                r"from\s+.*russell|russell\s*2000.*1000|russell\s*1000.*2000", title, re.I
            ):
                warnings.append(
                    f"reclassify without style_subset or explicit pair: {t} / {idx}"
                )
    return warnings


def retag_announcements_style_subset() -> int:
    """One-time / idempotent: re-run titles through extractor; set style_subset on each row."""
    path = ANNOUNCEMENTS
    if not path.exists():
        return 0
    lines = path.read_text(encoding="utf-8").splitlines()
    changed = 0
    out_lines: list[str] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            out_lines.append(line)
            continue
        title = row.get("title") or ""
        ticker = row.get("ticker")
        if not title or not ticker:
            out_lines.append(json.dumps(row, ensure_ascii=False))
            continue
        events = extract_index_events(title, "", candidate_tickers=[ticker])
        style = False
        for ev in events:
            if ev.get("ticker") == ticker and (
                ev.get("index") == row.get("index") or not row.get("index")
            ):
                style = bool(ev.get("style_subset"))
                break
        if not style:
            style = _is_style_or_subset_index(title) or (
                (row.get("action") == "reclassify")
                and not re.search(r"\brussell\s*1000\b|\brussell\s*2000\b", title, re.I)
            )
        prev = bool(row.get("style_subset"))
        row["style_subset"] = style
        if style:
            row["quality_gated"] = False
        if prev != style:
            changed += 1
        out_lines.append(json.dumps(row, ensure_ascii=False))
    path.write_text("\n".join(out_lines) + ("\n" if out_lines else ""), encoding="utf-8")
    return changed


def harvest_archive_announcements(
    *,
    seed: dict,
    company_names: dict[str, str],
    holdings_tickers: set[str] | None = None,
) -> list[dict]:
    """
    Recover aged index events from news-review markdown and per-ticker news_index.json.

    Live portfolio_news.json ages out; AMD/WEST/ALS.TO/CSGP-style headlines often live
    only in reviews or ticker archives. Same subject-gated extract as live harvest.
    """
    tickers = holdings_tickers or set(company_names)
    existing = load_announcements()
    harvested: list[dict] = []
    seen_titles: set[str] = set()

    # 1) Pending + approved news review digests
    review_dirs = [p for p in (REVIEWS_PENDING, REVIEWS_APPROVED) if p.is_dir()]
    for rev_dir in review_dirs:
        for path in sorted(rev_dir.glob("news_*.md")):
            dm = _REVIEW_DATE_RE.search(path.name)
            announced = dm.group(1) if dm else date.today().isoformat()
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for line in text.splitlines():
                if not _ARCHIVE_EVENTISH.search(line):
                    continue
                m = _REVIEW_LINE_RE.search(line)
                if not m:
                    continue
                t, _cat, title = m.group(1), m.group(2), m.group(3)
                if t not in tickers or title in seen_titles:
                    continue
                seen_titles.add(title)
                harvested.extend(
                    _try_append_extracted(
                        title=title,
                        summary="",
                        tickers=[t],
                        company_names=company_names,
                        announced=announced,
                        source_url=None,
                        source_type="news_review_archive",
                        seed=seed,
                        existing=existing,
                    )
                )

    # 2) Per-ticker research news archives (CSGP Nasdaq exit, etc.)
    for ticker in sorted(tickers):
        news_path = ROOT / ticker / "research" / "news" / "news_index.json"
        if not news_path.exists():
            continue
        try:
            doc = json.loads(news_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for item in doc.get("items") or doc.get("articles") or []:
            title = item.get("title") or ""
            if not title or not _ARCHIVE_EVENTISH.search(title):
                continue
            if title in seen_titles:
                continue
            seen_titles.add(title)
            summary = item.get("summary") or ""
            announced = str(
                item.get("published_utc") or item.get("published") or item.get("date") or ""
            )[:10] or date.today().isoformat()
            item_tickers = item.get("tickers") or [ticker]
            item_tickers = [t for t in item_tickers if t in tickers] or [ticker]
            harvested.extend(
                _try_append_extracted(
                    title=title,
                    summary=summary,
                    tickers=item_tickers,
                    company_names=company_names,
                    announced=announced,
                    source_url=item.get("url") or item.get("link"),
                    source_type="ticker_news_archive",
                    seed=seed,
                    existing=existing,
                )
            )

    return harvested


def applicable_indices(meta: dict, rules: dict) -> list[str]:
    market = meta.get("market") or ""
    exchange = (meta.get("exchange") or "").upper()
    out = []
    for index_id, spec in (rules.get("indices") or {}).items():
        markets = spec.get("markets") or []
        exchanges = [e.upper() for e in (spec.get("exchanges") or [])]
        if markets and market not in markets:
            # allow US OTC only for ineligible path via security type, not scorecards
            continue
        if exchanges and exchange and exchange not in exchanges:
            # still allow if market matches and exchanges list is advisory for home indices
            if index_id in {"msci_acwi", "msci_usa", "stoxx_europe_600", "russell_1000", "russell_2000"}:
                pass
            elif market in markets and not exchanges:
                pass
            elif exchange not in exchanges:
                continue
        out.append(index_id)
    # Always attach russell + sp families for US listed
    if market == "US" and exchange not in {"OTC PINK", "PRIVATE", "OTC"}:
        for idx in ("sp500", "sp400", "sp600", "russell_1000", "russell_2000", "msci_usa", "msci_acwi"):
            if idx not in out:
                out.append(idx)
        if exchange == "NASDAQ":
            if "nasdaq_100" not in out:
                out.append("nasdaq_100")
    return out


def check_result(passed: bool | None, value, threshold, reason: str | None = None) -> dict:
    return {
        "pass": passed,
        "value": value,
        "threshold": threshold,
        "reason": reason,
    }


def scorecard_sp(
    index_id: str,
    spec: dict,
    mi: dict,
    is_member: bool,
    *,
    max_cand_dist: float = DEFAULT_MAX_CANDIDATE_DISTANCE_PCT,
) -> dict:
    checks: dict[str, dict] = {}
    mcap = mi.get("market_cap_usd")
    missing = list(mi.get("missing") or [])
    dist: float | None = None

    if index_id == "sp500":
        thr = spec.get("min_company_mcap_usd")
        if mcap is None:
            checks["market_cap"] = check_result(None, None, thr, "missing market_cap")
        else:
            checks["market_cap"] = check_result(mcap >= thr, mcap, thr)
            dist = ((mcap - thr) / thr) * 100.0 if thr else None
    else:
        band = spec.get("band_usd") or [0, 0]
        lo, hi = band[0], band[1]
        if mcap is None:
            checks["market_cap"] = check_result(None, None, band, "missing market_cap")
        else:
            in_band = lo <= mcap <= hi
            checks["market_cap"] = check_result(in_band, mcap, band)
            if mcap < lo:
                dist = ((mcap - lo) / lo) * 100.0
            elif mcap > hi:
                dist = ((mcap - hi) / hi) * 100.0
            else:
                dist = -min(abs(mcap - lo), abs(hi - mcap)) / ((hi - lo) or 1) * 100.0

    float_pct = mi.get("float_pct")
    min_float = spec.get("min_float_pct")
    if float_pct is None:
        checks["float"] = check_result(None, None, min_float, "missing float_pct")
    else:
        checks["float"] = check_result(float_pct >= min_float, float_pct, min_float)

    ep = mi.get("earnings_positive")
    if ep is None:
        checks["earnings_positive"] = check_result(None, mi.get("earnings_note"), True, "missing earnings")
    else:
        checks["earnings_positive"] = check_result(bool(ep), ep, True, mi.get("earnings_note"))

    exch = (mi.get("exchange") or "").upper()
    allowed = [e.upper() for e in (spec.get("exchanges") or [])]
    if not exch:
        checks["exchange"] = check_result(None, None, allowed, "missing exchange")
    else:
        checks["exchange"] = check_result(exch in allowed, exch, allowed)

    adv = mi.get("adv_dollar")
    if adv is None or mcap is None or float_pct is None:
        checks["liquidity"] = check_result(None, None, spec.get("liquidity_ratio_min"), "missing adv or float")
    else:
        float_mcap = mcap * float_pct
        ratio = (adv * 252) / float_mcap if float_mcap else None
        checks["liquidity"] = check_result(
            ratio is not None and ratio >= float(spec.get("liquidity_ratio_min") or 1.0),
            ratio,
            spec.get("liquidity_ratio_min"),
        )

    return finalize_scorecard(
        index_id, checks, is_member, dist, missing, max_cand_dist=max_cand_dist, floor_only=(index_id == "sp500")
    )


def scorecard_mcap_min(
    index_id: str,
    spec: dict,
    mi: dict,
    is_member: bool,
    key: str = "min_mcap_usd",
    *,
    max_cand_dist: float = DEFAULT_MAX_CANDIDATE_DISTANCE_PCT,
    excluded: bool = False,
) -> dict:
    checks: dict[str, dict] = {}
    mcap = mi.get("market_cap_usd")
    thr = spec.get(key)
    dist = None
    if excluded:
        checks["excluded"] = check_result(False, mi.get("ticker"), "denylist", "excluded from index eligibility")
    if thr is None:
        checks["market_cap"] = check_result(None, mcap, None, "no public cutoff encoded; membership-seed only")
    elif mcap is None:
        checks["market_cap"] = check_result(None, None, thr, "missing market_cap")
    else:
        checks["market_cap"] = check_result(mcap >= thr, mcap, thr)
        dist = ((mcap - thr) / thr) * 100.0
    exch = (mi.get("exchange") or "").upper()
    allowed = [e.upper() for e in (spec.get("exchanges") or [])]
    if allowed:
        if not exch:
            checks["exchange"] = check_result(None, None, allowed, "missing exchange")
        else:
            checks["exchange"] = check_result(exch in allowed, exch, allowed)
    # Min-mcap families are floor_only: clearing the floor ≠ candidacy
    return finalize_scorecard(
        index_id,
        checks,
        is_member,
        dist,
        mi.get("missing") or [],
        max_cand_dist=max_cand_dist,
        floor_only=True,
    )


def scorecard_russell(
    index_id: str,
    spec: dict,
    mi: dict,
    is_member: bool,
    universe_ranks: dict[str, int],
    *,
    max_cand_dist: float = DEFAULT_MAX_CANDIDATE_DISTANCE_PCT,
    breakpoint_mcap: float | None = None,
    breakpoint_source: str = "config",
    band_usd: list[float] | None = None,
) -> dict:
    """
    Seed membership is ground truth for member.
    Candidacy uses dated Russell breakpoint mcap (config), not portfolio-median proxy.
    """
    checks: dict[str, dict] = {}
    mcap = mi.get("market_cap_usd")
    ticker = mi.get("ticker")
    rank = universe_ranks.get(ticker)
    dist = None
    rank_method = "config_breakpoint" if breakpoint_source == "config" else "portfolio_proxy_fallback"

    if mcap is None:
        checks["market_cap"] = check_result(None, None, "total_market_cap", "missing market_cap")
    else:
        checks["market_cap"] = check_result(True, mcap, "observed")

    band = band_usd or spec.get("band_usd") or []
    band_low = float(band[0]) if len(band) >= 1 else None
    band_high = float(band[1]) if len(band) >= 2 else None

    if is_member:
        checks["rank"] = check_result(True, rank, "seed_member", "membership from seed")
        dist = 0.0
    elif breakpoint_mcap and mcap:
        dist = ((float(mcap) - float(breakpoint_mcap)) / float(breakpoint_mcap)) * 100.0
        if index_id == "russell_1000":
            # Non-members near/above breakpoint are R1000 candidates (not mega-caps far above)
            near = near_boundary(dist, max_cand_dist) and dist >= -max_cand_dist
            checks["rank"] = check_result(
                near,
                rank,
                f"breakpoint_mcap={breakpoint_mcap:.0f}",
                rank_method,
            )
        else:
            # R2000: only names inside [band_low, breakpoint] (or near below breakpoint).
            # Mega-caps far above breakpoint are never R2000 candidates.
            in_r2000_band = True
            if band_low is not None and band_high is not None:
                in_r2000_band = band_low <= float(mcap) <= float(breakpoint_mcap) * (1 + max_cand_dist / 100.0)
            elif float(mcap) > float(breakpoint_mcap) * (1 + max_cand_dist / 100.0):
                in_r2000_band = False
            near = near_boundary(dist, max_cand_dist) and dist <= max_cand_dist and in_r2000_band
            checks["rank"] = check_result(
                near,
                rank,
                f"breakpoint_mcap={breakpoint_mcap:.0f}",
                rank_method,
            )
    else:
        checks["rank"] = check_result(None, rank, "breakpoint", "breakpoint unavailable")
        rank_method = "n_a"

    sc = finalize_scorecard(
        index_id, checks, is_member, dist, mi.get("missing") or [], max_cand_dist=max_cand_dist, floor_only=False
    )
    sc["rank_estimate"] = rank
    sc["rank_method"] = rank_method
    # Fallback proxy candidates are suppressed from float-impact + Potential display
    if rank_method == "portfolio_proxy_fallback" and sc.get("status") == "inclusion_candidate":
        sc["status"] = "n_a"
        sc["gating_check"] = "portfolio_proxy_fallback_suppressed"
    return sc


def russell_breakpoint_mcap(
    inputs_by_ticker: dict[str, dict],
    seed: dict,
    rules: dict | None = None,
) -> tuple[float | None, str]:
    """Return (breakpoint_mcap, source). Prefer dated config; portfolio median is last resort."""
    rules = rules or {}
    r1 = (rules.get("indices") or {}).get("russell_1000") or {}
    cfg_bp = r1.get("breakpoint_mcap_usd")
    if cfg_bp is not None:
        try:
            return float(cfg_bp), "config"
        except (TypeError, ValueError):
            pass
    # Last-resort portfolio-local proxy (labeled; candidates suppressed)
    caps = []
    by = seed.get("by_ticker") or {}
    for t, entry in by.items():
        mems = entry.get("memberships") or []
        if "russell_1000" not in mems:
            continue
        mi = inputs_by_ticker.get(t) or {}
        if mi.get("market_cap_usd"):
            caps.append(float(mi["market_cap_usd"]))
    if not caps:
        us = sorted(
            (
                float(mi["market_cap_usd"])
                for mi in inputs_by_ticker.values()
                if mi.get("market") == "US" and mi.get("market_cap_usd")
            ),
            reverse=True,
        )
        if len(us) < 3:
            return None, "n_a"
        return us[max(0, len(us) // 3 - 1)], "portfolio_proxy_fallback"
    caps.sort()
    return caps[len(caps) // 2], "portfolio_proxy_fallback"


def max_candidate_distance(rules: dict) -> float:
    scoring = rules.get("scoring") or {}
    return float(scoring.get("max_candidate_distance_pct") or DEFAULT_MAX_CANDIDATE_DISTANCE_PCT)


def near_boundary(distance_pct: float | None, max_abs: float) -> bool:
    if distance_pct is None:
        return False
    return abs(float(distance_pct)) <= max_abs


def finalize_scorecard(
    index_id: str,
    checks: dict,
    is_member: bool,
    distance_pct: float | None,
    missing: list[str],
    *,
    max_cand_dist: float = DEFAULT_MAX_CANDIDATE_DISTANCE_PCT,
    floor_only: bool = False,
) -> dict:
    """
    Status rules (precision-first):
    - member / deletion_risk for seed members
    - inclusion_candidate only when near boundary (|distance| <= max_cand_dist)
    - floor_only indices (MSCI/Nasdaq min-mcap): never candidate merely for clearing the floor
    """
    gating = None
    known = []
    member_hard_fails = {"exchange", "security_type", "float", "excluded"}
    for name, c in checks.items():
        if c.get("pass") is False:
            if not is_member or name in member_hard_fails:
                gating = gating or name
        if c.get("pass") is not None:
            known.append(c.get("pass"))

    if is_member:
        status = "deletion_risk" if gating else "member"
    else:
        fails = [n for n, c in checks.items() if c.get("pass") is False]
        unknowns = [n for n, c in checks.items() if c.get("pass") is None]
        passes = [n for n, c in checks.items() if c.get("pass") is True]

        if "excluded" in fails:
            status = "ineligible"
            gating = gating or "excluded"
        elif mi_ineligible_from_missing(missing) and not known:
            status = "n_a"
        elif floor_only:
            # Clearing a min-mcap floor is not candidacy; need near-boundary only
            if near_boundary(distance_pct, max_cand_dist) and not fails and passes:
                # For floor indices, distance is usually largely positive (above floor).
                # Treat "near" as within max_cand_dist *above* the floor (0..+max), not far above.
                if distance_pct is not None and 0 <= float(distance_pct) <= max_cand_dist:
                    status = "inclusion_candidate"
                    gating = None
                else:
                    status = "n_a"
                    gating = gating or "above_floor_not_near_cutoff"
            else:
                status = "n_a" if unknowns or not passes else ("ineligible" if fails else "n_a")
        elif near_boundary(distance_pct, max_cand_dist) and not fails and passes:
            status = "inclusion_candidate"
            gating = None
        elif near_boundary(distance_pct, max_cand_dist) and fails and set(fails) <= {"earnings_positive", "float", "liquidity"}:
            # Near boundary but soft gates unknown/fail → still n_a (don't invent)
            if unknowns or any(checks.get(f, {}).get("pass") is None for f in ("float", "liquidity", "earnings_positive")):
                status = "n_a"
                gating = gating or (unknowns[0] if unknowns else fails[0])
            else:
                status = "n_a"
                gating = gating or fails[0]
        elif fails and not near_boundary(distance_pct, max_cand_dist):
            status = "ineligible" if distance_pct is not None and abs(float(distance_pct)) > max_cand_dist * 2 else "n_a"
        elif unknowns and not passes:
            status = "n_a"
            gating = gating or unknowns[0]
        else:
            status = "n_a"

    if is_member and status not in {"member", "deletion_risk"}:
        status = "deletion_risk" if gating else "member"

    return {
        "index": index_id,
        "status": status,
        "checks": checks,
        "gating_check": gating,
        "distance_to_boundary_pct": round(distance_pct, 2) if distance_pct is not None else None,
        "confidence": "rules_only",
    }


def mi_ineligible_from_missing(missing: list[str]) -> bool:
    return "market_cap" in missing


def build_universe_ranks(inputs_by_ticker: dict[str, dict]) -> dict[str, int]:
    """Rank US names by market cap (1 = largest). Portfolio-relative proxy for Russell."""
    rows = []
    for t, mi in inputs_by_ticker.items():
        if mi.get("market") != "US":
            continue
        if mi.get("security_type") in {"cvr", "preferred", "debenture", "rights", "otc_pink", "private"}:
            continue
        mcap = mi.get("market_cap_usd")
        if mcap is None:
            continue
        rows.append((t, mcap))
    rows.sort(key=lambda x: x[1], reverse=True)
    # Scale portfolio ranks into a pseudo full-market rank so breakpoint 1000 is meaningful:
    # map position i of n → approx rank = 1 + i * (3000 / max(n,1))
    n = max(len(rows), 1)
    ranks = {}
    for i, (t, _) in enumerate(rows):
        ranks[t] = int(1 + i * (3000 / n))
    return ranks


def inclusion_probability_band(scorecard: dict, days_out: int | None, rules: dict) -> str:
    if scorecard.get("status") in {"ineligible", "n_a"}:
        return "n_a"
    if scorecard.get("status") == "member":
        return "n_a"
    dist = scorecard.get("distance_to_boundary_pct")
    if dist is None:
        return "n_a"
    checks = scorecard.get("checks") or {}
    known = [c for c in checks.values() if c.get("pass") is not None]
    if not known:
        return "n_a"
    pass_pct = sum(1 for c in known if c.get("pass")) / len(known)
    bands = (rules.get("scoring") or {}).get("inclusion_probability") or {}
    for name in ("high", "medium", "low"):
        b = bands.get(name) or {}
        if abs(dist) <= float(b.get("max_abs_distance_pct") or 999) and pass_pct >= float(
            b.get("min_gates_pass_pct") or 0
        ):
            max_days = b.get("max_days_to_event")
            if days_out is None or max_days is None or days_out <= int(max_days):
                return name
    return "low"


def priority_score(
    scorecards: list[dict],
    mi: dict,
    days_out: int | None,
    rules: dict,
    confirmed_soon: bool,
    *,
    float_impact_shock: float | None = None,
) -> tuple[float, float | None]:
    weights = (rules.get("scoring") or {}).get("weights") or {}
    w_b = float(weights.get("boundary_closeness") or 0.35)
    w_c = float(weights.get("calendar_proximity") or 0.25)
    w_d = float(weights.get("demand_shock") or 0.30)
    w_i = float(weights.get("illiquidity") or 0.10)

    # Best absolute distance among candidate/deletion scorecards
    dists = [
        abs(sc["distance_to_boundary_pct"])
        for sc in scorecards
        if sc.get("distance_to_boundary_pct") is not None
        and sc.get("status") in {"inclusion_candidate", "deletion_risk", "member"}
    ]
    if dists:
        best = min(dists)
        boundary = max(0.0, 1.0 - best / 40.0)
    else:
        boundary = 0.0

    if days_out is None:
        cal = 0.0
    elif days_out < 0:
        cal = 0.1
    else:
        cal = max(0.0, 1.0 - days_out / 180.0)

    # Demand shock: prefer computed float-impact (|net flow| / ADV);
    # fall back to flat assumed_index_weight_bps_add when n_a.
    mcap = mi.get("market_cap_usd")
    adv = mi.get("adv_dollar")
    bps = float((rules.get("scoring") or {}).get("assumed_index_weight_bps_add") or 5.0)
    cap = float((rules.get("scoring") or {}).get("demand_shock_adv_cap") or 50.0)
    shock = None
    if float_impact_shock is not None:
        shock = float(float_impact_shock)
        demand = min(1.0, shock / cap)
    elif mcap and adv and adv > 0:
        assumed_notional = mcap * (bps / 10000.0)
        shock = (assumed_notional / adv) * 100.0  # pct of one-day ADV
        demand = min(1.0, shock / cap)
    else:
        demand = 0.15 if any(sc.get("status") == "inclusion_candidate" for sc in scorecards) else 0.0

    if adv and adv > 0 and mcap:
        # lower ADV / mcap → higher illiquidity score
        turnover = adv / mcap
        illiq = max(0.0, min(1.0, 1.0 - turnover * 50))
    else:
        illiq = 0.4

    score = w_b * boundary + w_c * cal + w_d * demand + w_i * illiq
    if confirmed_soon:
        score = min(1.0, score + 0.15)
    if any(sc.get("status") == "deletion_risk" for sc in scorecards):
        score = min(1.0, score + 0.1)
    return round(score, 4), round(shock, 3) if shock is not None else None


def next_calendar_for_indices(calendar: dict, index_ids: list[str], today: date) -> dict | None:
    best = None
    best_days = None
    for ev in calendar.get("events") or []:
        indices = ev.get("indices") or []
        if index_ids and not any(i in indices for i in index_ids):
            continue
        eff = parse_date(ev.get("effective"))
        d = days_until(eff, today)
        if d is None:
            continue
        if best_days is None or (d >= 0 and (best_days < 0 or d < best_days)) or (best_days is not None and best_days < 0 and d > best_days):
            # prefer soonest future; else least-negative past
            if best is None:
                best, best_days = ev, d
            elif d >= 0 and (best_days < 0 or d < best_days):
                best, best_days = ev, d
            elif best_days is not None and best_days < 0 and d < 0 and d > best_days:
                best, best_days = ev, d
    if not best:
        return None
    return {
        "id": best.get("id"),
        "index_family": best.get("index_family"),
        "indices": best.get("indices"),
        "kind": best.get("kind"),
        "effective": best.get("effective"),
        "label": best.get("label"),
        "days_out": best_days,
    }


def apply_confirmed_to_seed(seed: dict, announcements: list[dict], today: date) -> dict:
    by_ticker = dict(seed.get("by_ticker") or {})
    for ann in announcements:
        if ann.get("confidence") != "provider_confirmed":
            continue
        eff = parse_date(ann.get("effective"))
        if eff is None or eff > today:
            continue
        t = ann.get("ticker")
        idx = ann.get("index")
        action = ann.get("action")
        if not t or not idx:
            continue
        entry = dict(by_ticker.get(t) or {"memberships": [], "source": "provider_confirmed", "as_of": today.isoformat()})
        mem = list(entry.get("memberships") or [])
        if action == "add" and idx not in mem:
            mem.append(idx)
        if action == "delete" and idx in mem:
            mem = [m for m in mem if m != idx]
        entry["memberships"] = sorted(set(mem))
        entry["as_of"] = today.isoformat()
        entry["source"] = "provider_confirmed"
        by_ticker[t] = entry
    seed = dict(seed)
    seed["by_ticker"] = by_ticker
    return seed


def corporate_action_tickers(news_doc: dict) -> set[str]:
    """Tickers that appear to be acquisition targets or going private (deletion risk)."""
    out: set[str] = set()
    target_pat = re.compile(
        r"\b(to\s+be\s+acquired|agrees\s+to\s+be\s+acquired|going\s+private|take[- ]private|"
        r"buyout\s+of|will\s+be\s+acquired|accepts\s+buyout)\b",
        re.I,
    )
    for item in news_doc.get("items") or []:
        title = item.get("title") or ""
        summary = item.get("summary") or ""
        text = f"{title} {summary}"
        if not target_pat.search(text):
            continue
        # Only flag tickers named in the title (primary subject), not co-mentions
        title_up = title.upper()
        for t in item.get("tickers") or ([item.get("ticker")] if item.get("ticker") else []):
            if not t:
                continue
            # Require ticker or company-ish token in title
            bare = str(t).split(".")[0].upper()
            if bare in title_up or str(t).upper() in title_up:
                out.add(t)
    return out


def build_for_ticker(
    ticker: str,
    meta: dict,
    rules: dict,
    calendar: dict,
    seed_entry: dict,
    mi: dict,
    universe_ranks: dict[str, int],
    announcements: list[dict],
    today: date,
    mna_tickers: set[str] | None = None,
    *,
    breakpoint_mcap: float | None = None,
    breakpoint_source: str = "config",
) -> dict:
    memberships = list((seed_entry or {}).get("memberships") or [])
    sec_type = mi.get("security_type")
    ineligible_types = set(rules.get("ineligible_security_types") or [])
    max_cand = max_candidate_distance(rules)
    nasdaq_deny = set((rules.get("indices") or {}).get("nasdaq_100", {}).get("exclude_tickers") or []) | NASDAQ_EXCLUDE_TICKERS

    scorecards: list[dict] = []
    if sec_type and sec_type in ineligible_types:
        scorecards.append(
            {
                "index": "_security",
                "status": "ineligible",
                "checks": {
                    "security_type": check_result(False, sec_type, list(ineligible_types), "excluded security type")
                },
                "gating_check": "security_type",
                "distance_to_boundary_pct": None,
                "confidence": "rules_only",
            }
        )
    else:
        for index_id in applicable_indices(meta, rules):
            spec = (rules.get("indices") or {}).get(index_id) or {}
            is_member = index_id in memberships
            family = spec.get("family")
            if family == "sp_dji":
                if index_id == "djia":
                    # Price-weighted 30; no mcap band scorecard — seed / notices only
                    sc = {
                        "index": index_id,
                        "status": "member" if is_member else "n_a",
                        "checks": {},
                        "gating_check": None if is_member else "membership_seed_only",
                        "distance_to_boundary_pct": None,
                        "confidence": "rules_only",
                    }
                else:
                    sc = scorecard_sp(index_id, spec, mi, is_member, max_cand_dist=max_cand)
            elif family == "russell":
                sc = scorecard_russell(
                    index_id,
                    spec,
                    mi,
                    is_member,
                    universe_ranks,
                    max_cand_dist=max_cand,
                    breakpoint_mcap=breakpoint_mcap,
                    breakpoint_source=breakpoint_source,
                    band_usd=spec.get("band_usd"),
                )
            elif family in {"nasdaq", "msci", "tsx", "ftse", "stoxx", "asx", "nzx", "hsi", "nse", "sgx", "b3", "bmv", "jpx"}:
                key = "min_mcap_usd"
                if "min_mcap_cad" in spec:
                    key = "min_mcap_cad"
                elif "min_mcap_gbp" in spec:
                    key = "min_mcap_gbp"
                elif "min_mcap_eur" in spec:
                    key = "min_mcap_eur"
                excluded = index_id == "nasdaq_100" and ticker.upper() in nasdaq_deny
                sc = scorecard_mcap_min(
                    index_id, spec, mi, is_member, key=key, max_cand_dist=max_cand, excluded=excluded
                )
                if family in {"jpx", "hsi", "nse", "sgx", "b3", "bmv", "asx", "nzx"} and not spec.get(key):
                    if is_member:
                        sc["status"] = "member"
                    else:
                        sc["status"] = "n_a"
                        sc["gating_check"] = sc.get("gating_check") or "membership_seed_only"
            else:
                sc = {
                    "index": index_id,
                    "status": "member" if is_member else "n_a",
                    "checks": {},
                    "gating_check": None if is_member else "unsupported_family",
                    "distance_to_boundary_pct": None,
                    "confidence": "rules_only",
                }
            if is_member and sc.get("status") not in {"deletion_risk"}:
                sc["status"] = "member"
            scorecards.append(sc)

    t_anns = [a for a in announcements if a.get("ticker") == ticker]
    confirmed_events = []
    news_notes = []
    for a in t_anns:
        row_ev = {
            "ticker": ticker,
            "index": a.get("index"),
            "action": a.get("action"),
            "announced": a.get("announced"),
            "effective": a.get("effective"),
            "source_url": a.get("source_url"),
            "source_type": a.get("source_type"),
            "confidence": a.get("confidence"),
            "title": a.get("title"),
            "style_subset": bool(a.get("style_subset")),
            "quality_gated": (
                False
                if a.get("style_subset")
                else bool(a.get("quality_gated") or a.get("confidence") == "provider_confirmed")
            ),
        }
        # Surface provider_confirmed always; news only if quality_gated.
        # Style/subset never upgrades scorecards or confirmed_soon.
        is_style = bool(row_ev.get("style_subset"))
        if (a.get("confidence") == "provider_confirmed" or row_ev.get("quality_gated")) and not is_style:
            confirmed_events.append(row_ev)
        else:
            news_notes.append(row_ev)
        for sc in scorecards:
            if is_style:
                continue
            if sc.get("index") == a.get("index") and (
                a.get("confidence") == "provider_confirmed" or a.get("quality_gated")
            ):
                conf = a.get("confidence") or "news_unconfirmed"
                if conf == "provider_confirmed" or sc.get("confidence") != "provider_confirmed":
                    sc["confidence"] = conf

    index_ids = [sc["index"] for sc in scorecards if sc.get("index") != "_security"]
    next_ev = next_calendar_for_indices(calendar, index_ids, today)
    days_out = next_ev.get("days_out") if next_ev else None

    watch_sc = None
    for sc in scorecards:
        if sc.get("status") in {"inclusion_candidate", "deletion_risk"}:
            watch_sc = sc
            break
    if watch_sc is None and scorecards:
        watch_sc = scorecards[0]
    prob = inclusion_probability_band(watch_sc or {}, days_out, rules) if watch_sc else "n_a"

    confirmed_soon = False
    for ev in confirmed_events:
        if ev.get("style_subset"):
            continue
        eff = parse_date(ev.get("effective"))
        d = days_until(eff, today)
        if d is not None and 0 <= d <= 30:
            confirmed_soon = True

    for ev in confirmed_events:
        if ev.get("action") == "delete":
            for sc in scorecards:
                if sc.get("index") == ev.get("index") and sc.get("status") == "member":
                    sc["status"] = "deletion_risk"

    if mna_tickers and ticker in mna_tickers:
        for sc in scorecards:
            if sc.get("status") == "member":
                sc["status"] = "deletion_risk"
                sc["gating_check"] = sc.get("gating_check") or "corporate_action_news"

    # Priority score recomputed after float_impact attach in build(); fallback here.
    pscore, shock = priority_score(scorecards, mi, days_out, rules, confirmed_soon)

    badge = "n_a"
    for pref in ("deletion_risk", "inclusion_candidate", "member", "ineligible", "n_a"):
        if any(sc.get("status") == pref for sc in scorecards):
            badge = pref
            break

    return {
        "ticker": ticker,
        "company": meta.get("company"),
        "market": meta.get("market"),
        "exchange": meta.get("exchange"),
        "current_memberships": memberships,
        "scorecards": scorecards,
        "badge_status": badge,
        "impact_proxy": {
            "demand_shock_pct_of_adv": shock,
            "priority_score": pscore,
            "demand_shock_source": "assumed_bps_fallback",
        },
        "confirmed_events": confirmed_events,
        "news_notes": news_notes,
        "prediction": {
            "next_calendar_event": next_ev,
            "inclusion_probability_band": prob,
        },
        "inputs_missing": mi.get("missing") or [],
        "security_type": sec_type,
        "_priority_inputs": {
            "days_out": days_out,
            "confirmed_soon": confirmed_soon,
        },
    }


def build(today: date | None = None, *, purge_announcements: bool = True) -> dict:
    today = today or date.today()
    rules = load_json(DATA_DIR / "index_rules.json", {})
    calendar = load_json(DATA_DIR / "index_calendar.json", {})
    seed = load_json(DATA_DIR / "index_memberships_seed.json", {"by_ticker": {}})
    registry = load_json(REGISTRY, {"holdings": {}})
    news = load_json(NEWS_PATH, {})
    fund_cache = load_fundamentals_cache()
    holdings = registry.get("holdings") or {}
    company_names = {t: (h.get("company") or "") for t, h in holdings.items()}

    harvest_news_announcements(
        news, today, seed=seed, company_names=company_names, purge=purge_announcements
    )
    # After purge/live harvest: recover aged headlines from reviews + ticker news archives
    harvest_archive_announcements(
        seed=seed,
        company_names=company_names,
        holdings_tickers=set(holdings),
    )
    n_retag = retag_announcements_style_subset()
    if n_retag:
        print(f"Retagged style_subset on {n_retag} announcement rows")
    announcements = load_announcements()
    seed = apply_confirmed_to_seed(seed, announcements, today)
    save_json(DATA_DIR / "index_memberships_seed.json", seed)
    mna_tickers = corporate_action_tickers(news)

    inputs_by_ticker = {}
    for ticker, meta in holdings.items():
        inputs_by_ticker[ticker] = market_inputs_for_ticker(
            ticker, holdings_meta=meta, fundamentals_cache=fund_cache
        )
    universe_ranks = build_universe_ranks(inputs_by_ticker)
    bp_mcap, bp_source = russell_breakpoint_mcap(inputs_by_ticker, seed, rules)

    by_ticker = {}
    for ticker, meta in sorted(holdings.items()):
        by_ticker[ticker] = build_for_ticker(
            ticker,
            meta,
            rules,
            calendar,
            (seed.get("by_ticker") or {}).get(ticker) or {},
            inputs_by_ticker[ticker],
            universe_ranks,
            announcements,
            today,
            mna_tickers=mna_tickers,
            breakpoint_mcap=bp_mcap,
            breakpoint_source=bp_source,
        )

    # Float-impact forced-flow model (HK reconstitution axioms)
    aum_registry = load_aum_registry()
    float_summary = attach_float_impact(by_ticker, inputs_by_ticker, aum_registry, rules=rules)
    for ticker, row in by_ticker.items():
        fi = row.get("float_impact") or {}
        shock_fi = demand_shock_from_float_impact(fi)
        pri = row.pop("_priority_inputs", None) or {}
        if shock_fi is not None:
            pscore, shock = priority_score(
                row.get("scorecards") or [],
                inputs_by_ticker.get(ticker) or {},
                pri.get("days_out"),
                rules,
                bool(pri.get("confirmed_soon")),
                float_impact_shock=shock_fi,
            )
            row["impact_proxy"] = {
                "demand_shock_pct_of_adv": shock,
                "priority_score": pscore,
                "demand_shock_source": "float_impact",
                "pct_of_float_base": (fi.get("primary") or {}).get("pct_of_float_base"),
            }

    max_cand = max_candidate_distance(rules)
    inclusion_candidates = sorted(
        t
        for t, row in by_ticker.items()
        if row.get("badge_status") == "inclusion_candidate"
        and any(
            sc.get("status") == "inclusion_candidate"
            and near_boundary(sc.get("distance_to_boundary_pct"), max_cand)
            for sc in row.get("scorecards") or []
        )
    )
    deletion_risks = sorted(
        t
        for t, row in by_ticker.items()
        if any(sc.get("status") == "deletion_risk" for sc in row.get("scorecards") or [])
    )
    confirmed_next_30d = []
    for t, row in by_ticker.items():
        for ev in row.get("confirmed_events") or []:
            d = days_until(parse_date(ev.get("effective")), today)
            if d is not None and 0 <= d <= 30:
                confirmed_next_30d.append(t)
                break
    high_priority = sorted(
        by_ticker.keys(),
        key=lambda t: (by_ticker[t].get("impact_proxy") or {}).get("priority_score") or 0,
        reverse=True,
    )
    high_priority_watch = [
        t
        for t in high_priority
        if by_ticker[t].get("badge_status") in {"inclusion_candidate", "deletion_risk"}
        or (
            (by_ticker[t].get("impact_proxy") or {}).get("priority_score") or 0
        ) >= 0.45
        and by_ticker[t].get("badge_status") == "inclusion_candidate"
    ][:40]

    cal_strip = []
    for ev in calendar.get("events") or []:
        eff = parse_date(ev.get("effective"))
        cal_strip.append(
            {
                **{k: ev.get(k) for k in ("id", "index_family", "indices", "kind", "effective", "label")},
                "days_out": days_until(eff, today),
            }
        )
    cal_strip.sort(key=lambda e: (e["days_out"] is None, e["days_out"] if e["days_out"] is not None else 9999))

    quality_events = sum(
        1
        for row in by_ticker.values()
        for ev in row.get("confirmed_events") or []
        if ev.get("quality_gated")
    )
    news_note_count = sum(len(row.get("news_notes") or []) for row in by_ticker.values())

    payload = {
        "generated": now_iso(),
        "rules_as_of": rules.get("as_of"),
        "as_of": today.isoformat(),
        "caption": (
            "The average large-cap S&P 500 index effect has fallen to near zero since 2010; "
            "treat these as research triggers, weighted by demand-shock size, not mechanical trades. "
            "Migrations across the Russell 1000/2000 breakpoint are typically net-negative for the "
            "promoted stock (Horizon Kinetics 2013)."
        ),
        "by_ticker": by_ticker,
        "portfolio_summary": {
            "inclusion_candidates": inclusion_candidates,
            "deletion_risks": deletion_risks,
            "confirmed_next_30d": sorted(set(confirmed_next_30d)),
            "high_priority_watch": high_priority_watch,
            "ticker_count": len(by_ticker),
            "quality_gated_events": quality_events,
            "news_notes": news_note_count,
            "max_candidate_distance_pct": max_cand,
            "top_float_impacts": float_summary.get("top_float_impacts") or [],
            "aum_as_of": float_summary.get("aum_as_of"),
            "aum_stale": float_summary.get("aum_stale"),
        },
        "calendar": cal_strip,
    }
    return payload


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None, help="As-of date YYYY-MM-DD")
    ap.add_argument(
        "--no-purge",
        action="store_true",
        help="Do not purge news_unconfirmed announcements before re-harvest",
    )
    args = ap.parse_args()
    today = date.fromisoformat(args.date) if args.date else date.today()
    payload = build(today=today, purge_announcements=not args.no_purge)
    save_json(OUT_PATH, payload)
    if DOCS_OUT.parent.exists():
        save_json(DOCS_OUT, payload)
    summary = payload["portfolio_summary"]
    print(
        f"Wrote {OUT_PATH} tickers={summary['ticker_count']} "
        f"candidates={len(summary['inclusion_candidates'])} "
        f"deletion_risks={len(summary['deletion_risks'])} "
        f"high_priority={len(summary['high_priority_watch'])} "
        f"quality_events={summary.get('quality_gated_events', 0)}"
    )
    seed_final = load_json(DATA_DIR / "index_memberships_seed.json", {"by_ticker": {}})
    for warn in lint_announcement_conflicts(load_announcements(), seed=seed_final):
        print(f"WARN index conflict: {warn}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
