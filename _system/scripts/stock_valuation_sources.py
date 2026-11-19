"""Replayable public vendor annual observations and dated spot FX, research only."""
from __future__ import annotations
from datetime import datetime, timezone, timedelta
import gzip
import json
from pathlib import Path
import threading
import time
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen
from stock_valuation_models import number

TYPES = {"annualDilutedEPS": ("diluted_eps", "income"), "annualBasicEPS": ("basic_eps", "income"),
         "annualTotalRevenue": ("revenue", "income"), "annualDilutedAverageShares": ("diluted_shares", "income"),
         "annualOperatingCashFlow": ("ocf", "cashflow"), "annualCapitalExpenditure": ("capex", "cashflow")}
_LOCK = threading.Lock()
_NEXT = 0.0


def get_json(url):
    global _NEXT
    for attempt in range(3):
        try:
            with _LOCK:
                time.sleep(max(0, _NEXT-time.monotonic()))
                _NEXT = time.monotonic()+.8
            with urlopen(Request(url, headers={"User-Agent": "Mozilla/5.0 stock-research", "Accept-Encoding": "gzip"}), timeout=35) as response:
                body = response.read()
                if response.headers.get("Content-Encoding") == "gzip":
                    body = gzip.decompress(body)
            return json.loads(body)
        except (OSError, ValueError):
            if attempt == 2:
                raise
            time.sleep(2 ** (attempt+1))


def fetch_history(symbol, cache: Path):
    target = cache / (quote(symbol, safe="") + ".json")
    if target.is_file():
        return json.loads(target.read_text(encoding="utf-8"))
    url = "https://query1.finance.yahoo.com/ws/fundamentals-timeseries/v1/finance/timeseries/" + quote(symbol, safe="") + "?" + urlencode({
        "symbol": symbol, "type": ",".join(TYPES), "period1": int(datetime(2022, 1, 1, tzinfo=timezone.utc).timestamp()), "period2": int(time.time())})
    data = get_json(url)
    saved = {"symbol": symbol, "source_url": url, "retrieved_at": datetime.now(timezone.utc).isoformat(), "data": data}
    cache.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(saved, separators=(",", ":")), encoding="utf-8")
    return saved


def vendor_history(saved, as_of):
    rows = saved.get("data", {}).get("timeseries", {}).get("result") or []
    series, currencies = [], set()
    for row in rows:
        if row.get("meta", {}).get("symbol") != [saved["symbol"]]:
            raise ValueError("Vendor financial listing mismatch")
        for key, (identity, statement) in TYPES.items():
            if key not in row:
                continue
            observations = [p for p in row[key] if p.get("periodType") == "12M" and p.get("asOfDate", "9999") <= as_of and number(p.get("reportedValue", {}).get("raw"))]
            money_currencies = {p.get("currencyCode") for p in observations}
            if len(money_currencies) != 1 or not all(isinstance(c, str) and len(c) == 3 for c in money_currencies):
                continue
            currency = next(iter(money_currencies)); currencies.add(currency)
            unit = "shares" if identity == "diluted_shares" else currency+"/shares" if identity.endswith("eps") else currency
            points = [{"period": p["asOfDate"], "value": p["reportedValue"]["raw"], "period_type": "12M",
                       "basis": "Vendor annual 12-month observation; reporting/share basis needs review", "vendor_input": True,
                       "source": {"url": saved["source_url"], "ref": saved["source_url"], "retrieved_at": saved["retrieved_at"], "locator": key+"; "+p["asOfDate"]}}
                      for p in observations]
            series.append({"id": identity, "unit": unit, "statement": statement, "annual": sorted(points, key=lambda p: p["period"]), "quarterly": []})
    if len(currencies) != 1:
        return {"currency": None, "series": []}
    currency = next(iter(currencies))
    by_id = {s["id"]: s for s in series}
    capex = {p["period"]: p for p in by_id.get("capex", {}).get("annual", [])}
    fcf = [{**p, "value": p["value"]-abs(capex[p["period"]]["value"]), "source_refs": [p["source"], capex[p["period"]]["source"]],
            "calculation_inputs": [{"label": "Operating cash flow", "value": p["value"], "unit": currency, "period": p["period"], "source": p["source"]},
                                   {"label": "Capital expenditure (absolute amount deducted)", "value": capex[p["period"]]["value"], "unit": currency, "period": p["period"], "source": capex[p["period"]]["source"]}],
            "basis": "Vendor annual operating cash flow less capital expenditure; not normalized owner cash"}
           for p in by_id.get("ocf", {}).get("annual", []) if p["period"] in capex]
    series.append({"id": "free_cash_flow", "unit": currency, "statement": "cashflow", "annual": fcf, "quarterly": []})
    return {"currency": currency, "series": series}


def fetch_fx(source, target, as_of, cache: Path):
    symbol = source+target+"=X"
    path = cache / (symbol+".json")
    if path.is_file():
        saved = json.loads(path.read_text(encoding="utf-8"))
    else:
        url = "https://query1.finance.yahoo.com/v8/finance/chart/"+quote(symbol, safe="")+"?range=1mo&interval=1d"
        saved = {"source_url": url, "retrieved_at": datetime.now(timezone.utc).isoformat(), "data": get_json(url)}
        cache.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(saved, separators=(",", ":")), encoding="utf-8")
    data = saved["data"]["chart"]["result"][0]
    if data["meta"].get("symbol") != symbol or data["meta"].get("currency") != target:
        raise ValueError("FX pair identity mismatch")
    cutoff = min(as_of, (datetime.now(timezone.utc).date()-timedelta(days=1)).isoformat())
    points = [(datetime.fromtimestamp(ts, timezone.utc).date().isoformat(), value)
              for ts, value in zip(data.get("timestamp", []), data["indicators"]["quote"][0]["close"])
              if number(value) and value > 0 and datetime.fromtimestamp(ts, timezone.utc).date().isoformat() <= cutoff]
    when, value = max(points)
    if (datetime.fromisoformat(as_of)-datetime.fromisoformat(when)).days > 7:
        raise ValueError("Dated FX observation is too old")
    return {"from_currency": source, "to_currency": target, "rate": value, "as_of": when, "source_url": saved["source_url"], "retrieved_at": saved["retrieved_at"]}
