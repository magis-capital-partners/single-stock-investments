"""Cache-preserving SEC-only coverage for the frozen announcement universe."""
import hashlib
import json
import time
from datetime import datetime, timezone

from .fundamentals import cik_id


def ensure_sources(cfg, events, output):
    import requests  # deferred: network command only

    cache = cfg.raw_dir / "companyfacts"
    cache.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers["User-Agent"] = cfg.section("edgar")["user_agent"]
    issuers = sorted({int(e["cik"]) for e in events if cik_id(e.get("cik")).isdigit()})
    results, denied = [], False
    for cik in issuers:
        for kind in ("facts", "issuer"):
            name = f"CIK{cik:010d}" + (".issuer" if kind == "issuer" else "") + ".json"
            path = cache / name
            row = {"cik": str(cik), "kind": kind, "file": name}
            if path.exists():
                row["status"] = "cached"
            elif denied:
                row["status"] = "unavailable_after_rate_limit"
            else:
                url = (f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json" if kind == "facts"
                       else f"https://data.sec.gov/submissions/CIK{cik:010d}.json")
                try:
                    response = session.get(url, timeout=30)
                    response.raise_for_status()
                    doc = response.json()
                    if cik_id(doc.get("cik")) != str(cik):
                        raise ValueError("CIK mismatch")
                    if kind == "issuer":
                        doc = {k: doc.get(k) for k in ("cik", "name", "sic", "sicDescription", "tickers", "exchanges")}
                        doc["fetched_at"] = datetime.now(timezone.utc).isoformat()
                    elif not doc.get("facts"):
                        raise ValueError("No companyfacts")
                    tmp = path.with_suffix(".tmp")
                    tmp.write_text(json.dumps(doc), encoding="utf-8")
                    tmp.replace(path)
                    row["status"] = "downloaded"
                    print(f"SEC {cik} {kind}: downloaded", flush=True)
                except (requests.RequestException, ValueError) as exc:
                    row.update(status="unavailable", reason=str(exc)[:180])
                    if isinstance(exc, requests.HTTPError) and exc.response.status_code in {403, 429}:
                        denied = True
                    print(f"SEC {cik} {kind}: unavailable", flush=True)
                time.sleep(max(.25, cfg.section("edgar").get("request_delay_seconds", .25)))
            if path.exists():
                row.update(sha256=hashlib.sha256(path.read_bytes()).hexdigest(), bytes=path.stat().st_size)
            results.append(row)
            output.write_text(json.dumps({"built_at": datetime.now(timezone.utc).isoformat(), "issuers": len(issuers), "results": results}, indent=2), encoding="utf-8")
    return results
