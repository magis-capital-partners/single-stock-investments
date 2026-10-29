"""Pure royalty filing parsers adapted from the dated 2026-10-23 Magis mirror.

Only extractors are ported. Fetching uses the repo SEC client and normalized
operating store. These parser results do not create valuation fact locks.
"""
from __future__ import annotations
import re
from operating_kpis.model import make_point, month_period
QW = {"first": 1, "second": 2, "third": 3, "fourth": 4}
MON = r"(January|February|March|April|May|June|July|August|September|October|November|December)"
def month_num(name):
    return int(month_period(name + " 2000")[5:])

def norm(t): return re.sub(r"\s+", " ", t.replace("\u200b", " "))

def n(s): return float(s.replace(",", "")) if s is not None else None

def first_num(label, t, after=0, window=120):
    """First number following an exact table label (skips $, |, footnote digits)."""
    m = re.search(re.escape(label) + r"(?:\s*\(\d\))?\s*\|?((?:\s*(?:\$|\||\(\d\)))*)\s*\(?(-?[\d,]+(?:\.\d+)?)\)?", t[after:])
    return n(m.group(2)) if m and len(m.group(0)) < window + len(label) else None

def q_from_text(t):
    m = re.search(r"(first|second|third|fourth)[- ]quarter(?: of| ended)?,? (\d{4})", t, re.I)
    if m: return f"{m.group(2)}Q{QW[m.group(1).lower()]}"
    m = re.search(r"\bQ([1-4]) (\d{4})", t)
    if m: return f"{m.group(2)}Q{m.group(1)}"
    m = re.search(r"(?:quarter|three months) ended " + MON + r" \d{1,2}, (\d{4})", t)
    if m: return f"{m.group(2)}Q{(month_num(m.group(1)) - 1) // 3 + 1}"
    return None

def x_tpl(t, f, url):
    p = q_from_text(t[:3000]); out = []
    if not p: return out
    m = re.search(r"royalty production (?:of|was|averaged) (?:approximately )?([\d.]+) thousand (?:barrels of oil equivalent|Boe)", t, re.I)
    if m: out.append(("oil_gas_royalty_production", n(m.group(1)), "kboe_per_day"))
    m = re.search(r"produced water royalty volumes? (?:of|was|were|averaged) (?:approximately )?([\d.]+) million (?:barrels|bbl)", t, re.I)
    if m: out.append(("produced_water_royalty_volume", n(m.group(1)), "mmbbl_per_day"))
    m = re.search(r"water sales volumes? (?:of|was|were|averaged) (?:approximately )?([\d.]+) (million|thousand) (?:barrels|bbl)", t, re.I)
    if m: out.append(("water_sales_volume", n(m.group(1)) * (1000 if m.group(2) == "million" else 1), "kbbl_per_day"))
    i = t.find("Revenues:")
    for lab, k in [("Water sales", "rev_water_sales"), ("Produced water royalties", "rev_produced_water_royalties"),
                   ("Easements and other surface-related income", "rev_easements_surface"), ("Oil and gas royalties", "rev_oil_gas_royalties")]:
        v = first_num(lab, t, after=max(i, 0))
        if v is not None: out.append((k, v, "usd_k"))
    return [(p,) + o for o in out]

def x_rgld(t, f, url):
    out = []
    if "Preliminary" in t[:1500] or "preliminary" in t[:1500]:
        p = q_from_text(t[:2500])
        m = re.search(r"GEOs\s*\d?\s*\|?\s*([\d,]{5,})", t)
        if p and m: out.append((p, "stream_geos_prelim", n(m.group(1)), "oz"))
        m = re.search(r"Stream Segment Sales\s*\|?\s*\$([\d.]+)M", t)
        if p and m: out.append((p, "stream_sales_prelim", n(m.group(1)), "usd_m"))
        m = re.search(r"Gold \| ([\d,]+) oz", t)
        if p and m: out.append((p, "stream_gold_oz_sold_prelim", n(m.group(1)), "oz"))
    else:
        p = q_from_text(t[:2500])
        m = re.search(r"stream segment sales were approximately ([\d,]{5,}) gold equivalent ounces", t)
        if p and m: out.append((p, "stream_geos_prelim", n(m.group(1)), "oz"))
        ms = list(re.finditer(r"Sales volume of ([\d,]{5,}) GEOs\s*\d?\s*(?:\(compared to ([\d,]{5,}))?", t))[:2]
        m = min(ms, key=lambda x: n(x.group(1))) if ms else None  # Q4 releases also carry the full-year figure
        if p and m:
            yoy = round(n(m.group(1)) / n(m.group(2)) - 1, 4) if m.group(2) else None
            out.append((p, "total_geos_sold", n(m.group(1)), "oz", yoy))
    g = re.search(r"(\d{4}) (?:guidance|outlook)[^.]{0,200}?([\d,]{5,}) (?:to|-|–) ([\d,]{5,}) (?:stream )?GEOs", t, re.I)
    if g: out.append((g.group(1), "geo_guidance_low", n(g.group(2)), "oz")); out.append((g.group(1), "geo_guidance_high", n(g.group(3)), "oz"))
    return out

def x_fnv(t, f, url):
    out = []
    m = re.search(r"Financial Highlights\s*[–-]\s*Q([1-4]) (\d{4})", t)
    if not m: return out
    p = f"{m.group(2)}Q{m.group(1)}"
    seg = t[m.end(): m.end() + 800]
    a = re.search(r"([\d,]+) GEOs\s*\d?\s*sold,?\s*([+-]?\d+)%", seg)
    if a: out.append((p, "geos_sold", n(a.group(1)), "oz", int(a.group(2)) / 100))
    b = re.search(r"([\d,]+) Net GEOs\s*\d?\s*sold,?\s*([+-]?\d+)%", seg)
    if b: out.append((p, "net_geos_sold", n(b.group(1)), "oz", int(b.group(2)) / 100))
    g = re.search(r"Guidance(.{0,3000})", t)
    if g:
        h = re.search(r"([\d,]{6,})\s*(?:to|-|–)\s*([\d,]{6,})\s*GEOs", g.group(1))
        y = re.search(r"(20\d\d) (?:guidance|GEO)", g.group(1)) or re.search(r"(20\d\d)", g.group(1))
        if h and y:
            out.append((y.group(1), "geo_guidance_low", n(h.group(1)), "oz")); out.append((y.group(1), "geo_guidance_high", n(h.group(2)), "oz"))
    return out

def x_wpm(t, f, url):
    out = []
    m = re.search(r"gold equivalent production\s*\d?\s*\(“?\"?GEOs\"?”?\) of ([\d,]+) ounces in the (first|second|third|fourth) quarter of (\d{4})(?:, an? (\d+)% (increase|decrease))?", t)
    if m:
        yoy = (int(m.group(4)) / 100 * (1 if m.group(5) == "increase" else -1)) if m.group(4) else None
        out.append((f"{m.group(3)}Q{QW[m.group(2)]}", "attributable_geo_production", n(m.group(1)), "oz", yoy))
    g = re.search(r"production in (\d{4}) is forecast to be.{0,300}?approximately ([\d,]+) to ([\d,]+) GEOs", t)
    if g: out.append((g.group(1), "geo_guidance_low", n(g.group(2)), "oz")); out.append((g.group(1), "geo_guidance_high", n(g.group(3)), "oz"))
    return out


SPECS = {
    "TPL": (1811074, ("8-K",), "2.02", x_tpl),
    "RGLD": (85535, ("8-K",), "2.02", x_rgld),
    "FNV": (1456346, ("6-K",), None, x_fnv),
    "WPM": (1323404, ("6-K",), None, x_wpm),
}


def parse_filing(ticker: str, text: str, *, filing: dict, source_url: str, fetched_at: str) -> list[dict]:
    """No network. One exhibit, one accession, one URL per observation."""
    out = []
    for observation in SPECS[ticker][3](norm(text), filing, source_url):
        period, kpi, value, unit = observation[:4]
        point = make_point(ticker=ticker, kpi=kpi, period=period, value=value, unit=unit,
                           source_url=source_url, doc=filing.get("primaryDocument") or source_url,
                           accession=filing.get("accessionNumber"), fetched_at=fetched_at)
        point["source_as_of"] = filing.get("filingDate")
        point["claim_type"] = "fact"
        if len(observation) > 4 and "guidance" not in kpi:
            point["yoy"] = observation[4]
            point["yoy_origin"] = "issuer_reported"
        out.append(point)
    return out


def fetch_filing_kpis(ticker: str, fetched_at: str) -> tuple[list[dict], list[dict]]:
    from operating_kpis.disclosures import recent_exhibits
    from operating_kpis.model import LayoutError

    cik, forms, item, _ = SPECS[ticker]
    seen = {}
    sources = []
    try:
        for filing, text, url in recent_exhibits(cik, forms=forms, item=item):
            points = parse_filing(ticker, text, filing=filing, source_url=url, fetched_at=fetched_at)
            if not points and q_from_text(norm(text)[:3000]) and re.search(r"GEOs|gold equivalent|Royalty production|Water sales", text, re.I):
                raise LayoutError(f"{ticker} results exhibit no longer matches its operating KPI parser: {url}")
            for point in points:
                seen.setdefault((point["kpi"], point["period"]), point)
            if points:
                sources.append({"ticker": ticker, "status": "ok", "source_url": url,
                                "as_of": filing.get("filingDate")})
    except (OSError, TimeoutError) as exc:
        sources.append({"ticker": ticker, "status": "blocked", "note": str(exc)})
    if not seen and not sources:
        # Old/non-results disclosures are routine; a parser layout change is
        # surfaced when a known results exhibit no longer produces its KPIs.
        sources.append({"ticker": ticker, "status": "blocked", "note": "No parseable recent operating disclosure; prior history retained."})
    return list(seen.values()), sources
