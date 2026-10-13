"""Classify reverse_splits exchange_class using SEC exchange map."""

from __future__ import annotations

import json

from .config import Config, load_config
from .db import init_db
from .ingest_splits import classify_exchange
from .utils import RateLimitedSession, normalize_ticker, pad_cik


def main(cfg: Config | None = None) -> None:
    cfg = cfg or load_config()
    http = RateLimitedSession(cfg.section("edgar")["user_agent"], 0.2)
    cache = cfg.raw_dir / "sec_company_tickers_exchange.json"
    try:
        raw = http.get("https://www.sec.gov/files/company_tickers_exchange.json").json()
        cache.write_text(json.dumps(raw), encoding="utf-8")
    except Exception as e:
        print("exchange map fetch failed", e)
        raw = json.loads(cache.read_text(encoding="utf-8")) if cache.exists() else None

    conn = init_db(cfg.db_path)
    updated = 0
    if raw and "data" in raw:
        fields = raw["fields"]
        by_ticker = {}
        for row in raw["data"]:
            rec = dict(zip(fields, row))
            t = normalize_ticker(rec.get("ticker"))
            if t:
                by_ticker[t] = rec
        rows = conn.execute("SELECT id, ticker, cik, exchange_class FROM reverse_splits").fetchall()
        for r in rows:
            rec = by_ticker.get(r["ticker"])
            if not rec:
                continue
            exch = rec.get("exchange")
            klass = classify_exchange(str(exch) if exch else None)
            if not exch or str(exch).upper() in {"", "NONE", "OTC", "OTCM", "PINK"}:
                if klass == "unknown":
                    klass = "otc"
            conn.execute(
                "UPDATE reverse_splits SET exchange=?, exchange_class=?, cik=COALESCE(cik, ?) WHERE id=?",
                (exch, klass if klass != "unknown" else r["exchange_class"], pad_cik(rec.get("cik")), r["id"]),
            )
            updated += 1
        conn.commit()
    print("updated", updated)
    rows = conn.execute("SELECT exchange_class, COUNT(*) c FROM reverse_splits GROUP BY 1").fetchall()
    print({r["exchange_class"]: r["c"] for r in rows})
    rows = conn.execute("SELECT cohort, COUNT(*) c FROM reverse_splits GROUP BY 1").fetchall()
    print({r["cohort"]: r["c"] for r in rows})
    conn.close()


if __name__ == "__main__":
    main()
