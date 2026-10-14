"""Fast EDGAR date enrichment via full-text search (no full filing download)."""

from __future__ import annotations

from datetime import datetime, timedelta

from .config import Config, load_config
from .db import init_db
from .ingest_splits import edgar_search_reverse_splits
from .utils import RateLimitedSession, pad_cik, parse_date, tqdm, years_ago
from datetime import date


PROXY_FORMS = {
    "PRE 14A",
    "DEF 14A",
    "DEFA14A",
    "PRE14A",
    "DEF14A",
    "PREC14A",
    "DEFC14A",
    "PRE 14C",
    "DEF 14C",
    "PRE 14C/A",
    "DEF 14C/A",
}


def _role_for_form(form: str) -> str:
    f = (form or "").upper().replace(" ", "")
    if f in {x.replace(" ", "") for x in PROXY_FORMS}:
        return "proxy"
    if f.startswith("8-K") or f.startswith("6-K"):
        return "announce"
    return "other"


def enrich_from_search(cfg: Config | None = None) -> dict[str, int]:
    cfg = cfg or load_config()
    conn = init_db(cfg.db_path)
    edgar_cfg = cfg.section("edgar")
    http = RateLimitedSession(
        edgar_cfg.get("user_agent", "ReverseSplitResearch research@localhost"),
        float(edgar_cfg.get("request_delay_seconds", 0.12)),
    )
    start = years_ago(int(cfg.section("universe").get("years_back", 5)))
    end = date.today()
    print(f"EDGAR search enrich {start} .. {end}")
    hits = edgar_search_reverse_splits(cfg, http, start, end)
    print(f"hits={len(hits)}")

    # Index hits by CIK
    by_cik: dict[str, list] = {}
    for h in hits:
        cik = pad_cik(h.get("cik"))
        if not cik:
            continue
        by_cik.setdefault(cik, []).append(h)

    lookback = int(edgar_cfg.get("lookback_days", 365))
    lookahead = int(edgar_cfg.get("lookahead_days", 30))
    events = conn.execute(
        "SELECT id, cik, ex_date FROM reverse_splits WHERE cik IS NOT NULL"
    ).fetchall()

    updated = 0
    filings = 0
    for ev in tqdm(events, desc="map search hits"):
        cik = pad_cik(ev["cik"])
        if not cik or cik not in by_cik:
            continue
        ex = datetime.strptime(ev["ex_date"][:10], "%Y-%m-%d").date()
        proxy_dates = []
        announce_dates = []
        for h in by_cik[cik]:
            filed = parse_date(h.get("filed_at"))
            if not filed:
                continue
            fd = datetime.strptime(filed, "%Y-%m-%d").date()
            if fd < ex - timedelta(days=lookback) or fd > ex + timedelta(days=lookahead):
                continue
            role = _role_for_form(h.get("form") or "")
            if role == "other":
                continue
            acc = h.get("accession") or ""
            url = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type={h.get('form')}&dateb=&owner=include&count=40"
            conn.execute(
                """
                INSERT INTO filings (event_id, accession, form, filed_at, url, role, excerpt)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(event_id, accession, role) DO NOTHING
                """,
                (ev["id"], acc, h.get("form"), filed, url, role, "from_edgar_search"),
            )
            filings += 1
            if role == "proxy":
                proxy_dates.append(filed)
            elif role == "announce":
                announce_dates.append(filed)
        if proxy_dates or announce_dates:
            conn.execute(
                """
                UPDATE reverse_splits SET
                    first_proxy_date = COALESCE(first_proxy_date, ?),
                    announce_date = COALESCE(announce_date, ?),
                    status = 'enriched_search',
                    confidence = MAX(confidence, 0.55),
                    updated_at = datetime('now')
                WHERE id=?
                """,
                (
                    min(proxy_dates) if proxy_dates else None,
                    min(announce_dates) if announce_dates else None,
                    ev["id"],
                ),
            )
            updated += 1
        if updated % 50 == 0:
            conn.commit()
    conn.commit()
    conn.close()
    return {"events_updated": updated, "filings": filings, "hits": len(hits)}


if __name__ == "__main__":
    print(enrich_from_search())
