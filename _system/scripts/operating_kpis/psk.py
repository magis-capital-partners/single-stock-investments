"""PrairieSky pure IR-release parser, ported from the 2026-10-23 mirror."""
from __future__ import annotations
import html as _h
import json
import re
from operating_kpis.model import LayoutError, make_point
from operating_kpis.http_util import http_get
API = "https://www.prairiesky.com/wp-json/wp/v2/posts?per_page=100&search=quarter%20results&_fields=date,link,title,content"
QW = {"first": 1, "second": 2, "third": 3, "fourth": 4}

def first_after(label, t, start=0):
    m = re.search(re.escape(label) + r"(?:[\s|]*\(\s*(?:\|\s*)?\d\s*\))?[\s|]*\(?(-?[\d,]+(?:\.\d+)?)", t[start:])
    return float(m.group(1).replace(",", "")) if m else None

def parse_psk_posts(posts, *, fetched_at: str, backfill=False):
    def row(ticker, kpi, period, value, unit, *, source_url, doc="", **extra):
        point = make_point(ticker=ticker, kpi=kpi, period=period, value=value,
                           unit=unit, source_url=source_url, doc=doc, fetched_at=fetched_at)
        point["claim_type"] = "fact"
        point["source_as_of"] = p["date"][:10]
        point.update(extra)
        return point
    out = []
    import datetime as dt
    cutoff = (dt.date.fromisoformat(fetched_at[:10]) - dt.timedelta(days=(900 if backfill else 200))).isoformat()
    for p in posts:
        if p["date"][:10] < cutoff:
            continue
        title = _h.unescape(p["title"]["rendered"])
        m = re.search(r"(First|Second|Third|Fourth) Quarter(?: and Year-End)?(?: Results for)? (\d{4})|(\d{4}) Annual and (Fourth) Quarter|Fourth Quarter and Year-End Results for (\d{4})|Fourth Quarter And Year-End Results For (\d{4})", title, re.I)
        if not m or "Conference Call" in title:
            continue
        if m.group(1): per = f"{m.group(2)}Q{QW[m.group(1).lower()]}"
        elif m.group(3): per = f"{m.group(3)}Q4"
        else: per = f"{m.group(5) or m.group(6)}Q4"
        if any(r["period"] == per for r in out):
            continue
        t = _h.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " | ", p["content"]["rendered"])))
        i = t.find("Royalty production volumes")
        if i < 0:
            out.append(row("PSK.TO", "layout_warning", per, None, "", source_url=p["link"], note="'Royalty production volumes' table not found")); continue
        vals = {"oil_royalty_production": ("Crude oil (bbls/d)", "bbl_per_day"), "ngl_royalty_production": ("NGL (bbls/d)", "bbl_per_day"),
                "gas_royalty_production": ("Natural gas (MMcf/d)", "mmcf_per_day"), "total_royalty_production": ("Royalty Production (BOE/d)", "boe_per_day")}
        for k, (lab, unit) in vals.items():
            v = first_after(lab, t, i)
            if v is not None:
                out.append(row("PSK.TO", k, per, v, unit, source_url=p["link"], doc=title))
        rv = first_after("Royalty production revenue", t)
        if rv is not None:
            out.append(row("PSK.TO", "royalty_production_revenue", per, rv, "cad_m", source_url=p["link"], doc=title))
        h = re.search(r"Total royalty production reached (?:a record )?([\d,]+) BOE per day", t)
        if h:
            hv = float(h.group(1).replace(",", ""))
            tv = next((r["value"] for r in out if r["period"] == per and r["kpi"] == "total_royalty_production"), None)
            if tv and abs(tv - hv) > 1:
                raise LayoutError(f"PSK: table total {tv} != headline {hv} for {per} (column misread?)")
    if not any(r["kpi"] == "total_royalty_production" for r in out):
        raise LayoutError("PSK: no royalty production parsed from prairiesky.com releases")
    return out

def fetch_psk(fetched_at: str):
    status, raw, error = http_get(API, timeout=30)
    if status != 200:
        return [], [{"ticker": "PSK.TO", "status": "blocked", "source_url": API, "note": error}]
    points = [p for p in parse_psk_posts(json.loads(raw), fetched_at=fetched_at) if p.get("value") is not None]
    return points, [{"ticker": "PSK.TO", "status": "ok", "source_url": API}]
