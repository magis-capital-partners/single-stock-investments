"""One-off local preview of Peters time-average growth on Michael's sleeve.

Reads no Gateway. Prices are Yahoo adjusted closes. The book is the D1 sleeve
snapshot taken 2026-10-07 (58 positions, NAV equals gross market value).
"""

from __future__ import annotations

import json
import math
import statistics
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).with_name("michael-time-average-2026-10-07.html")
NAV = 10090779.689878102
AS_OF = "2026-10-07"
WINDOW = 252

# ticker, market_value_usd
POSITIONS = [
    ("GTX", 4291596.279997643),
    ("JPM", 2544383.9799966887),
    ("HEI-A", 760592.7999999969),
    ("CSU", 623295.4909907987),
    ("QDEL", 377100.00000000023),
    ("MCO", 282579.00000000186),
    ("TBBK", 193759.99999999997),
    ("POST", 183300.0),
    ("SHC", 182500.0),
    ("MCHB", 109122.88000000098),
    ("MEHCQ.ESC", 65440.944534603004),
    ("COLD", 57298.560000000994),
    ("FTRE", 51949.99999999999),
    ("ASPN", -35220.0),
    ("3905.T", 34948.0818),
    ("TOI", 34535.657129399995),
    ("GPGI", 31726.070000002004),
    ("CORBF", 30955.05000000001),
    ("FIHO12", 26184.434927880044),
    ("WEST", -24750.0),
    ("BRBR", 24369.610000000004),
    ("BUR", 18685.179999996),
    ("LMN", 13992.844229999999),
    ("EQPT", -9450.0),
    ("GS", 9060.619999998999),
    ("FNMAP", 8862.0),
    ("CSU.DB", 8434.6635285),
    ("FLXN.CVR", 7440.0),
    ("INV", 5095.799999999999),
    ("FMCCK", 4980.0),
    ("WATR", 4637.690000000001),
    ("FMCCL", 4575.0),
    ("FNMAO", 4546.75),
    ("HL", 3848.2000000000003),
    ("JL80", 3788.99),
    ("FLUX", -2602.509999998),
    ("GDRZF", 2545.0),
    ("EFOR", -1798.5),
    ("ECHO", 1600.1599999999999),
    ("AXTQ", -1574.4),
    ("MRTX.CVR", 1540.0),
    ("XTIA", -1375.0300000000002),
    ("SKHQ", -1183.52),
    ("B", 1027.91),
    ("COHQ", -783.56),
    ("CHTR", -769.17),
    ("ECHX", -633.96),
    ("MACK", 168.11286257999998),
    ("NAN", 100.679999999),
    ("ABMD.CVR", 61.2),
    ("GKTX.PS1", 2.769960002252003),
    ("GKTX.PS2", 2.769960002252003),
    ("GKTX.PS3", 2.769960002252003),
    ("PRVL.CVR", 1.0600000000000005),
    ("CSU.WTS", 0.03),
    ("AKUS.CNT", 0.0),
    ("BFFI.ESC", 0.0),
    ("LENS.MRG", 0.0),
]

STRUCTURAL_OMIT = {
    "MEHCQ.ESC": "escrow stub",
    "CSU.DB": "debenture",
    "FLXN.CVR": "contingent value right",
    "MRTX.CVR": "contingent value right",
    "ABMD.CVR": "contingent value right",
    "PRVL.CVR": "contingent value right",
    "GKTX.PS1": "preferred stub",
    "GKTX.PS2": "preferred stub",
    "GKTX.PS3": "preferred stub",
    "CSU.WTS": "warrant",
    "AKUS.CNT": "zero-value contingent",
    "BFFI.ESC": "escrow stub",
    "LENS.MRG": "merger stub",
    "JL80": "not a common-stock listing",
}

YAHOO = {
    "HEI-A": ["HEI-A"],
    "CSU": ["CSU.TO"],
    "3905.T": ["3905.T"],
    "TOI": ["TOI.V", "TOI.TO", "TOI"],
    "FIHO12": ["FIHO12.MX"],
    "LMN": ["LMN.V", "LMN.TO"],
    "BUR": ["BUR"],
    "CORBF": ["CORBF"],
    "GDRZF": ["GDRZF"],
}

FX_FOR_SUFFIX = {
    ".TO": "CAD=X",
    ".V": "CAD=X",
    ".T": "JPY=X",
    ".MX": "MXN=X",
}


def fetch_json(url: str) -> dict:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "magis-research/time-average-preview (local example)"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def yahoo_adj(symbol: str) -> list[tuple[str, float]]:
    url = (
        "https://query1.finance.yahoo.com/v8/finance/chart/"
        + urllib.parse.quote(symbol, safe="")
        + "?"
        + urllib.parse.urlencode(
            {
                "range": "2y",
                "interval": "1d",
                "events": "div,splits",
            }
        )
    )
    payload = fetch_json(url)
    result = payload["chart"]["result"][0]
    stamps = result.get("timestamp") or []
    quote = ((result.get("indicators") or {}).get("quote") or [{}])[0]
    closes = quote.get("close") or []
    adjusted = (((result.get("indicators") or {}).get("adjclose") or [{}])[0]).get("adjclose") or []
    rows = []
    for index, stamp in enumerate(stamps):
        raw = closes[index] if index < len(closes) else None
        adj = adjusted[index] if index < len(adjusted) else None
        price = adj if isinstance(adj, (int, float)) else raw
        if not isinstance(price, (int, float)) or not math.isfinite(price) or price <= 0:
            continue
        day = datetime.fromtimestamp(stamp, tz=timezone.utc).strftime("%Y-%m-%d")
        rows.append((day, float(price)))
    # Yahoo can repeat a stamp. Keep the last print of each day.
    by_day: dict[str, float] = {}
    for day, price in rows:
        by_day[day] = price
    return sorted(by_day.items())


def load_series(candidates: list[str]) -> tuple[str, list[tuple[str, float]]]:
    last_error = "no candidate"
    for symbol in candidates:
        rows = None
        for attempt in range(3):
            try:
                rows = yahoo_adj(symbol)
                break
            except Exception as error:  # network or empty chart
                last_error = f"{symbol}: {error}"
                time.sleep(0.4 * (attempt + 1))
        if rows is None:
            continue
        if len(rows) >= 260:
            return symbol, rows
        last_error = f"{symbol}: {len(rows)} sessions"
        time.sleep(0.15)
    raise RuntimeError(last_error)


def fx_divisor(yahoo_symbol: str) -> str | None:
    for suffix, fx in FX_FOR_SUFFIX.items():
        if yahoo_symbol.endswith(suffix):
            return fx
    return None


def to_usd(rows: list[tuple[str, float]], fx: dict[str, float] | None) -> dict[str, float]:
    out = {}
    for day, price in rows:
        if fx is None:
            out[day] = price
            continue
        rate = fx.get(day)
        if rate and rate > 0:
            out[day] = price / rate
    return out


def simple_returns(prices: dict[str, float], calendar: list[str]) -> dict[str, float]:
    out = {}
    previous = None
    prev_day = None
    for day in calendar:
        price = prices.get(day)
        if price is None:
            continue
        if previous is not None and prev_day is not None:
            out[day] = price / previous - 1.0
        previous = price
        prev_day = day
    return out


def fred_bill() -> tuple[float, str]:
    url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS3MO"
    request = urllib.request.Request(url, headers={"User-Agent": "magis-research/time-average-preview"})
    with urllib.request.urlopen(request, timeout=30) as response:
        text = response.read().decode("utf-8")
    last_date = None
    last_yield = None
    for line in text.splitlines()[1:]:
        date, value = line.split(",")
        if value in ("", "."):
            continue
        last_date = date
        last_yield = float(value) / 100.0
    if last_yield is None or last_date is None:
        raise RuntimeError("DGS3MO empty")
    return math.log(1.0 + last_yield), last_date


def mean(values: list[float]) -> float:
    return sum(values) / len(values)


def pstdev(values: list[float]) -> float:
    return statistics.stdev(values) if len(values) > 1 else float("nan")


def esc(value: object) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def pct(value: float | None, digits: int = 1) -> str:
    if value is None or not math.isfinite(value):
        return "—"
    return f"{value * 100:.{digits}f}%"


def main() -> None:
    rf, rf_date = fred_bill()
    rf_daily = math.exp(rf / 252.0) - 1.0
    print(f"rf {rf:.4%} as of {rf_date}")

    spy_symbol, spy_rows = load_series(["SPY"])
    calendar = [day for day, _ in spy_rows][-WINDOW - 1 :]
    print(f"calendar {calendar[0]} to {calendar[-1]} via {spy_symbol}")

    fx_cache: dict[str, dict[str, float]] = {}
    for fx_symbol in ("CAD=X", "JPY=X", "MXN=X"):
        _, rows = load_series([fx_symbol])
        fx_cache[fx_symbol] = {day: price for day, price in rows}
        print(f"fx {fx_symbol} {len(rows)}")
        time.sleep(0.15)

    included = []
    omitted = []
    for ticker, market_value in POSITIONS:
        if ticker in STRUCTURAL_OMIT:
            omitted.append((ticker, market_value, STRUCTURAL_OMIT[ticker]))
            continue
        if abs(market_value) < 500:
            omitted.append((ticker, market_value, "market value under $500"))
            continue
        candidates = YAHOO.get(ticker, [ticker])
        try:
            yahoo_symbol, rows = load_series(candidates)
        except Exception as error:
            omitted.append((ticker, market_value, f"no 2-year price history ({error})"))
            continue
        fx_symbol = fx_divisor(yahoo_symbol)
        usd = to_usd(rows, fx_cache.get(fx_symbol) if fx_symbol else None)
        returns = simple_returns(usd, calendar)
        covered = [day for day in calendar[1:] if day in returns]
        if len(covered) < 200:
            omitted.append((ticker, market_value, f"{yahoo_symbol}: only {len(covered)} sessions on the SPY calendar"))
            continue
        included.append(
            {
                "ticker": ticker,
                "yahoo": yahoo_symbol,
                "fx": fx_symbol,
                "market_value": market_value,
                "weight": market_value / NAV,
                "returns": returns,
            }
        )
        print(f"ok {ticker} via {yahoo_symbol} days {len(covered)} w {market_value / NAV:.3%}")
        time.sleep(0.12)

    common = [day for day in calendar[1:]]
    common = [day for day in common if all(day in row["returns"] for row in included)]
    print(f"included {len(included)} common days {len(common)}")

    def series_for(weights: list[tuple[float, dict[str, float]]], days: list[str]) -> list[float]:
        total_w = sum(weight for weight, _ in weights)
        out = []
        for day in days:
            risky = sum(weight * rets[day] for weight, rets in weights)
            out.append(risky + (1.0 - total_w) * rf_daily)
        return out

    book_weights = [(row["weight"], row["returns"]) for row in included]
    book_days = common
    book_simple = series_for(book_weights, book_days)
    logs = [math.log1p(value) for value in book_simple if value > -0.999]
    g_emp = mean(logs) * 252.0
    mu_emp = mean(book_simple) * 252.0
    l_now = sum(row["weight"] for row in included)
    residual_w = 1.0 - sum(row["weight"] for row in POSITIONS and included)  # placeholder
    stock_weight = sum(market_value for _, market_value in POSITIONS) / NAV
    included_weight = l_now
    omitted_weight = sum(market_value for _, market_value, _ in omitted) / NAV

    # Fully invested mix: scale included weights to sum to 1, no cash.
    if abs(l_now) < 1e-8:
        raise SystemExit("net weight is zero")
    full_weights = [(row["weight"] / l_now, row["returns"]) for row in included]
    full_simple = []
    for day in book_days:
        full_simple.append(sum(weight * rets[day] for weight, rets in full_weights))
    full_logs = [math.log1p(value) for value in full_simple if value > -0.999]
    g_full = mean(full_logs) * 252.0
    sigma = pstdev(full_logs) * math.sqrt(252.0)
    mu = g_full + 0.5 * sigma * sigma
    mu_excess = mu - rf
    ito_at_now = 0.5 * (l_now ** 2) * sigma * sigma
    l_opt = mu_excess / (sigma * sigma) if sigma else float("nan")
    # equation 19, positive branch
    disc = mu_excess ** 2 + 2.0 * rf * sigma * sigma
    l_c = (mu_excess + math.sqrt(disc)) / (sigma * sigma) if sigma and disc >= 0 else float("nan")
    g_model = rf + l_now * mu_excess - 0.5 * (l_now ** 2) * sigma * sigma
    growth_at_opt_denom = g_full  # unlevered mix growth; t_c uses the running book's growth
    # characteristic time of the book at l_now (equation 18)
    g_now = rf + l_now * mu_excess - 0.5 * (l_now ** 2) * sigma * sigma
    if abs(g_now) < 1e-8:
        t_c = float("inf")
    else:
        t_c = (l_now ** 2 * sigma ** 2) / (g_now ** 2)
    se = sigma / math.sqrt(len(full_logs))
    l_opt_low = (mu_excess - se) / (sigma * sigma)
    l_opt_high = (mu_excess + se) / (sigma * sigma)
    reasons = []
    if len(full_logs) < 252:
        reasons.append(f"the common window is {len(full_logs)} sessions, short of a full year")
    if not math.isfinite(t_c):
        reasons.append("growth at today's scale is about zero, so the characteristic time is unbounded")
    elif t_c > 3.0:
        reasons.append(f"the characteristic time is {t_c:.1f} years, longer than the window can identify")
    if reasons:
        status = "unidentified"
        status_why = "; ".join(reasons) + ", so the scale is withheld"
    elif l_opt_high < l_now:
        status = "past the peak"
        status_why = "even the high end of the drift band sits below today's scale"
    elif l_opt_low > l_now:
        status = "room"
        status_why = "even the low end of the drift band sits above today's scale"
    else:
        status = "unidentified"
        status_why = "the drift band straddles today's scale"

    per_name = []
    for row in included:
        w = row["weight"]
        days = [day for day in calendar[1:] if day in row["returns"]][-WINDOW:]
        simple = [row["returns"][day] for day in days]
        name_logs = [math.log1p(w * value + (1.0 - w) * rf_daily) for value in simple if (w * value + (1.0 - w) * rf_daily) > -0.999]
        asset_logs = [math.log1p(value) for value in simple if value > -0.999]
        g_name = mean(name_logs) * 252.0
        sig_name = pstdev(asset_logs) * math.sqrt(252.0)
        g_asset = mean(asset_logs) * 252.0
        mu_name = g_asset + 0.5 * sig_name * sig_name
        excess = mu_name - rf
        drag = 0.5 * (w ** 2) * sig_name * sig_name
        per_name.append(
            {
                **{k: row[k] for k in ("ticker", "yahoo", "market_value", "weight")},
                "drag": drag,
                "growth": g_name,
                "sigma": sig_name,
                "l_opt": excess / (sig_name * sig_name) if sig_name else float("nan"),
            }
        )
    per_name.sort(key=lambda row: abs(row["market_value"]), reverse=True)

    def status_class(label: str) -> str:
        return {"past the peak": "bad", "room": "ok", "unidentified": "wait"}.get(label, "wait")

    rows_html = []
    for row in per_name:
        side = "short" if row["market_value"] < 0 else "long"
        rows_html.append(
            "<tr>"
            f"<td>{esc(row['ticker'])}</td>"
            f"<td class='dim'>{side}</td>"
            f"<td class='num'>{row['weight'] * 100:.1f}%</td>"
            f"<td class='num'>{pct(row['drag'])}</td>"
            f"<td class='num'>{pct(row['growth'])}</td>"
            f"<td class='num dim'>{pct(row['sigma'], 0)}</td>"
            "</tr>"
        )
    omit_html = []
    for ticker, market_value, reason in sorted(omitted, key=lambda item: abs(item[1]), reverse=True):
        omit_html.append(
            "<tr>"
            f"<td>{esc(ticker)}</td>"
            f"<td class='num'>{market_value / NAV * 100:.2f}%</td>"
            f"<td class='dim'>{esc(reason)}</td>"
            "</tr>"
        )

    scale_cell = "withheld"
    if status != "unidentified":
        scale_cell = f"{l_opt:.2f}×"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Michael · time-average growth preview</title>
<style>
  :root {{
    --bg: #0a0e17; --card: #151d2e; --line: #1e2d46; --text: #e8ecf4;
    --muted: #8896ae; --dim: #566580; --amber: #f59e0b; --green: #10b981; --red: #ef4444; --cyan: #06b6d4;
  }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; background: var(--bg); color: var(--text); font: 15px/1.45 "Segoe UI", sans-serif; }}
  main {{ max-width: 980px; margin: 0 auto; padding: 28px 20px 64px; }}
  .kicker {{ color: var(--cyan); font: 600 11px/1 ui-monospace, monospace; letter-spacing: .08em; text-transform: uppercase; }}
  h1 {{ font-size: 28px; margin: 8px 0 4px; }}
  .sub {{ color: var(--muted); margin: 0 0 18px; }}
  .banner {{ border: 1px solid rgba(245,158,11,.45); background: rgba(245,158,11,.08); border-radius: 10px; padding: 12px 14px; color: #f6d48a; margin-bottom: 16px; }}
  .grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin: 14px 0 18px; }}
  .card {{ background: var(--card); border: 1px solid var(--line); border-radius: 10px; padding: 12px 14px; }}
  .card span {{ display: block; color: var(--dim); font: 600 10px/1 ui-monospace, monospace; letter-spacing: .06em; text-transform: uppercase; margin-bottom: 6px; }}
  .card strong {{ font: 650 22px/1.1 ui-monospace, monospace; }}
  .wait strong {{ color: var(--amber); }}
  .bad strong {{ color: var(--red); }}
  .ok strong {{ color: var(--green); }}
  section {{ background: var(--card); border: 1px solid var(--line); border-radius: 12px; padding: 16px 16px 8px; margin-top: 14px; }}
  h2 {{ font-size: 16px; margin: 0 0 6px; }}
  p {{ color: var(--muted); margin: 0 0 12px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  th {{ text-align: left; color: var(--dim); font-size: 10px; letter-spacing: .05em; text-transform: uppercase; padding: 8px 6px; border-bottom: 1px solid var(--line); }}
  td {{ padding: 7px 6px; border-bottom: 1px solid #162033; }}
  .num {{ text-align: right; font-family: ui-monospace, monospace; }}
  th.num {{ text-align: right; }}
  .dim {{ color: var(--muted); }}
  @media (max-width: 800px) {{ .grid {{ grid-template-columns: 1fr 1fr; }} }}
</style>
</head>
<body>
<main>
  <div class="kicker">Proposed · Michael sleeve only · not a valuation</div>
  <h1>Time-average growth of the current mix</h1>
  <p class="sub">Sleeve dated {AS_OF}. NAV ${NAV:,.0f}. This is a daily-rebalanced hypothetical of today's stock weights. It is not broker net-liquidation value, and it is not a target weight.</p>
  <div class="banner">Local preview. Research only. An optimal scale above 1× is an upper bound: the formula charges borrowing at the Treasury bill and charges nothing to trade. Drift from one year of prices is noisy, so the scale is withheld unless the whole error band agrees.</div>
  <div class="grid">
    <div class="card"><span>Itô drag at today's scale</span><strong>{pct(ito_at_now)}</strong></div>
    <div class="card"><span>Empirical growth</span><strong>{pct(g_emp)}</strong></div>
    <div class="card"><span>Average of many paths</span><strong>{pct(mu_emp)}</strong></div>
    <div class="card {status_class(status)}"><span>Scale vs the peak</span><strong>{esc(status)}</strong></div>
  </div>
  <section>
    <h2>The book</h2>
    <p>{esc(status_why[:1].upper() + status_why[1:])}. Net stock weight of names in the mix is {l_now * 100:.1f}% of NAV. Omitted names are {omitted_weight * 100:.1f}% of NAV. Common window {book_days[0]} to {book_days[-1]} ({len(book_days)} sessions). 3-month bill {pct(math.exp(rf) - 1, 2)} as of {rf_date}, continuously compounded in the formula. Model growth at today's scale {pct(g_model)}. {"Peak scale, the critical scale, and the characteristic time stay off this panel until the window is a full year and the drift band agrees." if status == "unidentified" else f"Peak scale {esc(scale_cell)}. Critical scale where growth is zero {l_c:.2f}×. Characteristic time {t_c:.1f} years."}</p>
  </section>
  <section>
    <h2>Names in the mix</h2>
    <p>Each row is that name alone, at its current fraction of NAV, with the rest of wealth in the Treasury bill. Drag is the gap between the average of many paths and the growth of one reinvested path.</p>
    <table>
      <thead><tr><th>Name</th><th>Side</th><th class="num">Weight</th><th class="num">Itô drag</th><th class="num">Growth</th><th class="num">Volatility</th></tr></thead>
      <tbody>
        {''.join(rows_html)}
      </tbody>
    </table>
  </section>
  <section>
    <h2>Left out</h2>
    <p>Rights, warrants, escrows, and names without two years of dollar prices. Their market value still sits in NAV, so the mix is not the whole sleeve.</p>
    <table>
      <thead><tr><th>Name</th><th class="num">Weight</th><th>Reason</th></tr></thead>
      <tbody>
        {''.join(omit_html)}
      </tbody>
    </table>
  </section>
</main>
</body>
</html>
"""
    OUT.write_text(html, encoding="utf-8")
    summary = {
        "as_of": AS_OF,
        "nav": NAV,
        "included": len(included),
        "omitted": len(omitted),
        "l_now": l_now,
        "omitted_weight": omitted_weight,
        "included_weight": included_weight,
        "stock_weight_all_rows": stock_weight,
        "ito_drag": ito_at_now,
        "g_emp": g_emp,
        "mu_emp": mu_emp,
        "g_model": g_model,
        "sigma": sigma,
        "mu_excess": mu_excess,
        "l_opt": l_opt,
        "l_opt_low": l_opt_low,
        "l_opt_high": l_opt_high,
        "l_c": l_c,
        "t_c": t_c,
        "status": status,
        "status_why": status_why,
        "rf": math.exp(rf) - 1,
        "rf_date": rf_date,
        "common_days": len(book_days),
        "common_start": book_days[0],
        "common_end": book_days[-1],
        "names": [
            {"ticker": row["ticker"], "weight": row["weight"], "drag": row["drag"], "growth": row["growth"], "sigma": row["sigma"]}
            for row in per_name
        ],
        "omitted": [{"ticker": t, "weight": mv / NAV, "reason": reason} for t, mv, reason in omitted],
    }
    Path(__file__).with_name("michael-time-average-2026-10-07.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(json.dumps({k: summary[k] for k in ("status", "ito_drag", "g_emp", "mu_emp", "l_opt", "l_c", "t_c", "l_now", "included", "common_days")}, indent=2))
    print(OUT)


if __name__ == "__main__":
    main()
