"""One-off: build value_up_fund.csv from Yahoo Finance JP fund history API."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd
import requests

FUND_CODE = "9D311082"
OUT = Path(__file__).resolve().parents[1] / "research" / "model" / "data" / "touki_nav" / "value_up_fund.csv"
HISTORY_URL = f"https://finance.yahoo.co.jp/quote/{FUND_CODE}/history"
BFF = f"https://finance.yahoo.co.jp/bff-pc/v1/main/fund/price/history/{FUND_CODE}"


def _parse_preloaded_jwt(html: str) -> str:
    prefix = "window.__PRELOADED_STATE__ = "
    start = html.find(prefix) + len(prefix)
    depth = 0
    end = start
    for i, ch in enumerate(html[start:], start=start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    state = json.loads(html[start:end])
    return state["pageInfo"]["jwtToken"]


def _parse_jp_date(s: str) -> pd.Timestamp:
    m = re.match(r"(\d{4})年(\d{1,2})月(\d{1,2})日", s.strip())
    if not m:
        raise ValueError(f"unparseable date: {s!r}")
    y, mo, _d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    return pd.Timestamp(y, mo, 1) + pd.offsets.MonthEnd(0)


def _num(s: str) -> float:
    return float(str(s).replace(",", "").replace("+", ""))


def fetch_monthly_histories() -> list[dict]:
    sess = requests.Session()
    sess.headers.update({"User-Agent": "Mozilla/5.0 (MarvinResearch/7176.T)"})
    html = sess.get(HISTORY_URL, timeout=60).text
    jwt = _parse_preloaded_jwt(html)
    headers = {
        "Referer": HISTORY_URL,
        "jwt-token": jwt,
        "Accept": "application/json",
    }
    params = {
        "fromDate": "20150101",
        "toDate": pd.Timestamp.today().strftime("%Y%m%d"),
        "timeFrame": "monthly",
        "page": 1,
        "size": 500,
        "displayedMaxPage": 5,
    }
    r = sess.get(BFF, params=params, headers=headers, timeout=60)
    r.raise_for_status()
    data = r.json()
    return data["histories"]


def main() -> None:
    rows = []
    for h in fetch_monthly_histories():
        rows.append(
            {
                "as_of": _parse_jp_date(h["date"]).strftime("%Y-%m-%d"),
                "nav_jpy": _num(h["price"]),
                "aum_jpym": _num(h["netAssetsBalance"]),
            }
        )
    df = pd.DataFrame(rows).sort_values("as_of").drop_duplicates("as_of", keep="last")
    df["nav_jpy"] = df["nav_jpy"].astype(float)
    df["month_ret"] = df["nav_jpy"].pct_change()
    df["source"] = f"yahoo_finance_jp:{FUND_CODE}"
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT, index=False)
    print(f"wrote {OUT} rows={len(df)} range={df['as_of'].iloc[0]}..{df['as_of'].iloc[-1]}")


if __name__ == "__main__":
    main()
