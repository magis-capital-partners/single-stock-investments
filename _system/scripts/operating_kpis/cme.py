"""CME monthly market-statistics press release.

The release states asset-class ADV and the year-over-year change in prose.
cmegroup.com answers this environment with HTTP 403, so the live fetcher
records a block and the parser is locked to a fixture.
"""
from __future__ import annotations

import re

from operating_kpis.http_util import http_get
from operating_kpis.model import LayoutError, make_point, month_period

# Tried in order. The slug changes every month; the listing page is the
# discovery path when it is not blocked.
CANDIDATE_URLS = (
    "https://cmegroupinc.gcs-web.com/news-releases",
    "https://www.cmegroup.com/media-room/press-releases.html",
)

_PATTERNS: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    (
        "total_adv",
        "contracts_per_day",
        re.compile(
            r"with\s+([\d.]+)\s+million contracts,\s+up\s+([\d.]+)\s*%",
            re.I,
        ),
    ),
    (
        "interest_rate_adv",
        "contracts_per_day",
        re.compile(
            r"Interest Rate ADV increased\s+([\d.]+)\s*%\s+to\s+([\d.]+)\s+million",
            re.I,
        ),
    ),
    (
        "equity_index_adv",
        "contracts_per_day",
        re.compile(
            r"Equity Index ADV increased\s+([\d.]+)\s*%\s+to\s+([\d.]+)\s+million",
            re.I,
        ),
    ),
    (
        "energy_adv",
        "contracts_per_day",
        re.compile(
            r"Energy ADV increased\s+([\d.]+)\s*%\s+to\s+([\d.]+)\s+million",
            re.I,
        ),
    ),
    (
        "agricultural_adv",
        "contracts_per_day",
        re.compile(
            r"Agricultural ADV increased\s+([\d.]+)\s*%\s+to\s+([\d.]+)\s+million",
            re.I,
        ),
    ),
    (
        "fx_adv",
        "contracts_per_day",
        re.compile(
            r"Foreign Exchange ADV increased\s+([\d.]+)\s*%\s+to\s+([\d.]+)\s+million",
            re.I,
        ),
    ),
    (
        "metals_adv",
        "contracts_per_day",
        re.compile(r"Metals ADV of\s+([\d.]+)\s+million", re.I),
    ),
)


def parse_cme_release(
    text: str,
    *,
    source_url: str,
    doc: str,
    fetched_at: str,
) -> list[dict]:
    period = None
    for match in re.finditer(
        r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(20\d{2})\b",
        text,
    ):
        period = month_period(f"{match.group(1)} {match.group(2)}")
        if period:
            break
    if not period:
        raise LayoutError("CME release has no month and year")
    points = []
    for kpi, unit, pattern in _PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        groups = match.groups()
        if kpi == "total_adv":
            level, yoy_pct = float(groups[0]), float(groups[1])
        elif kpi == "metals_adv":
            level, yoy_pct = float(groups[0]), None
        else:
            yoy_pct, level = float(groups[0]), float(groups[1])
        point = make_point(
            ticker="CME",
            kpi=kpi,
            period=period,
            value=round(level * 1_000_000, 2),
            unit=unit,
            source_url=source_url,
            doc=doc,
            fetched_at=fetched_at,
            yoy_basis="ratio",
        )
        if yoy_pct is not None:
            point["yoy"] = round(yoy_pct / 100.0, 6)
        points.append(point)
    if not any(point["kpi"] == "total_adv" for point in points):
        raise LayoutError("CME release has no total ADV sentence")
    return points


def _fetch_legacy_cme(fetched_at: str) -> tuple[list[dict], list[dict]]:
    notes = []
    for url in CANDIDATE_URLS:
        status, body, err = http_get(url, timeout=20)
        if status != 200:
            notes.append({
                "ticker": "CME",
                "status": "blocked",
                "source_url": url,
                "http_status": status,
                "note": err or "CME volume page was not readable",
            })
            continue
        text = body.decode("utf-8", errors="replace")
        try:
            points = parse_cme_release(text, source_url=url, doc=url, fetched_at=fetched_at)
        except LayoutError as exc:
            notes.append({
                "ticker": "CME",
                "status": "blocked",
                "source_url": url,
                "http_status": status,
                "note": str(exc),
            })
            continue
        return points, [{"ticker": "CME", "status": "ok", "source_url": url}]
    return [], notes


# PR Newswire is issuer-authored primary release text. The parser is pure.
import datetime as dt
import html as _h
from urllib.parse import urljoin

def month_num(name):
    return int(month_period(name + " 2000")[5:])

MON = r"(January|February|March|April|May|June|July|August|September|October|November|December)"
CLASSES = [("Interest Rate", "adv_interest_rate"), ("Equity Index", "adv_equity_index"), ("Energy", "adv_energy"),
           ("Agricultural", "adv_agricultural"), ("Foreign Exchange", "adv_fx"), ("Metals", "adv_metals"),
           ("Cryptocurrency", "adv_crypto"), ("International", "adv_international")]

def parse_prnewswire_release(h: str, *, source_url: str, fetched_at: str):
    u = source_url
    def row(ticker, kpi, period, value, unit, *, source_url, doc="", yoy=None, **extra):
        if unit == "contracts_k":
            value, unit = value * 1000, "contracts_per_day"
        point = make_point(ticker=ticker, kpi=kpi, period=period, value=value,
                           unit=unit, source_url=source_url, doc=doc, fetched_at=fetched_at)
        point["yoy"] = yoy
        point["claim_type"] = "fact"
        point["source_as_of"] = pub.group(1)
        point.update(extra)
        return point
    pub = re.search(r"<meta name='date' content=\"(\d{4}-\d\d-\d\d)", h) or re.search(r'"datePublished":\s*"(\d{4}-\d\d-\d\d)', h)
    b = re.search(r'(?s)<section class="release-body.*?</section>', h)
    t = _h.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", b.group(0) if b else "")))
    if not t or not pub:
        raise LayoutError(f"CME/PRN: release body or date missing {u}")
    pd = dt.date.fromisoformat(pub.group(1))
    mh = re.search(MON + r" (\d{4}) (?:monthly highlights|(?:monthly )?(?:ADV )?(?:highlights )?across asset classes)", t)
    if mh:
        mon, yr = month_num(mh.group(1)), int(mh.group(2))
    else:
        if pd.day > 12:
            return []  # not a month-start volume report
        prev = pd.replace(day=1) - dt.timedelta(days=1); mon, yr = prev.month, prev.year
    mname = dt.date(yr, mon, 1).strftime("%B")
    period = f"{yr}-{mon:02d}"
    tr = max(t.find("today reported"), 0)
    intro = t[tr: (mh.start() if mh and mh.start() > tr else tr + 1200)]
    if mname not in intro and not mh:
        return []
    out = []
    tot = None
    tm = re.search(r"-(\d{1,2})-(\d)-million-contracts|-(\d{1,2})-million-contracts", u)
    if tm and re.search(r"(adv|volume)[^/]*-of-|record-of-", u) and not re.search(r"annual|quarterly|q[1-4]|international", u):
        v = float(f"{tm.group(1)}.{tm.group(2)}") if tm.group(1) else float(tm.group(3))
        y = re.search(r"(up|down)-(\d+)-year-over-year", u)
        tot = (v, ((1 if y.group(1) == "up" else -1) * int(y.group(2)) / 100) if y else None)
    for m in ([] if tot else  re.finditer(r"([\d.]+) million contracts", intro)):
        pre, post = intro[max(0, m.start() - 160): m.start()], intro[m.end(): m.end() + 90]
        if (mname in pre[-160:] or mname in post[:25]) and not re.search(r"Q[1-4]|quarter|annual|full-year|during the year|interest rate|equity index|metals|energy|international", pre[-45:] + post[:20], re.I):
            yoy = None
            y = re.search(r"(up|down|increase of|decrease of|increased|decreased) (\d+)%", post[:60])
            if y:
                yoy = (-1 if y.group(1).startswith(("down", "decrease")) else 1) * int(y.group(2)) / 100
            tot = (float(m.group(1)), yoy); break
    if tot:
        out.append(row("CME", "adv_total", period, tot[0] * 1000, "contracts_k", yoy=tot[1],
                       source_url=u, doc="PRN " + u.rsplit("-", 1)[-1].split(".")[0], note="yoy as reported"))
    sect = t[mh.end(): mh.end() + 6000] if mh else t[tr: tr + 6000]
    q = re.search(r"Q[1-4] \d{4} quarterly highlights|quarterly highlights", sect)
    if q: sect = sect[: q.start()]
    if not mh and re.search(r"quarter|Q[1-4] \d{4}", t[tr: tr + 600]):
        sect = ""  # month vs quarter breakdown ambiguous without a '<Month> <Year> ... highlights' header
    for label, kpi in CLASSES:
        m = re.search(rf"{label}\s+ADV (?:(increased|decreased|rose|fell|declined|grew) (\d+)% (?:to|year-over-year to) |(?:of|was|reached|hit)(?: a record| an? all-time record)? )([\d.,]+)( million| thousand)? contracts", sect)
        if m:
            v = float(m.group(3).replace(",", ""))
            if m.group(4) == " million" and "," in m.group(3):  # e.g. release typo '866,000 million contracts'
                v = v / 1000
            else:
                v = v * 1000 if m.group(4) == " million" else (v if m.group(4) == " thousand" else v / 1000)
            yoy = None
            if m.group(2):
                yoy = (1 if m.group(1) in ("increased", "rose", "grew") else -1) * int(m.group(2)) / 100
            out.append(row("CME", kpi, period, round(v, 1), "contracts_k", yoy=yoy, source_url=u,
                           doc="PRN " + u.rsplit("-", 1)[-1].split(".")[0], note="yoy as reported"))
    return out


def parse_rpc(text: str, *, source_url: str, filing: dict, fetched_at: str) -> list[dict]:
    period = re.search(r"(first|second|third|fourth)[- ]quarter (20\d{2})", text, re.I)
    rpc = re.search(r"(?:average )?rate per contract[^$]{0,80}\$\s?([\d.]+)", text, re.I)
    if not period or not rpc:
        return []
    quarter = ["first", "second", "third", "fourth"].index(period.group(1).lower()) + 1
    point = make_point(ticker="CME", kpi="rpc_total", period=f"{period.group(2)}Q{quarter}",
                       value=float(rpc.group(1).rstrip(".")), unit="usd_per_contract",
                       source_url=source_url, doc=filing.get("primaryDocument") or source_url,
                       accession=filing.get("accessionNumber"), fetched_at=fetched_at)
    point["source_as_of"] = filing.get("filingDate")
    point["claim_type"] = "fact"
    return [point]


def fetch_cme(fetched_at: str) -> tuple[list[dict], list[dict]]:
    from operating_kpis.disclosures import recent_exhibits
    points, sources = {}, []
    listing = "https://www.prnewswire.com/news/cme-group/?page=1&pagesize=100"
    status, raw, error = http_get(listing, timeout=30)
    if status == 200:
        links = re.findall(r'href="(/news-releases/cme-group[^\"]*?(?:adv|volume|average-daily)[^\"]*?-\d{9}\.html)"', raw.decode("utf-8", "replace"))
        links = [url for url in dict.fromkeys(links) if not re.search(
            r"international|daily-volume-record|open-interest|single-day|corn|dairy|energy-complex|metals-complex|crypto|sofr|fx-futures|brokertec", url)]
        if not links:
            raise LayoutError("CME issuer release listing has no discoverable monthly volume links")
        for link in links[:8]:
            url = urljoin(listing, link)
            code, body, err = http_get(url, timeout=30)
            if code != 200:
                sources.append({"ticker": "CME", "status": "blocked", "source_url": url, "note": err})
                continue
            rows = parse_prnewswire_release(body.decode("utf-8", "replace"), source_url=url, fetched_at=fetched_at)
            if rows and not any(row["kpi"] == "adv_total" for row in rows):
                raise LayoutError("CME monthly release parsed asset classes but no total ADV")
            for point in rows:
                points.setdefault((point["kpi"], point["period"]), point)
            if rows:
                sources.append({"ticker": "CME", "status": "ok", "source_url": url})
    else:
        sources.append({"ticker": "CME", "status": "blocked", "source_url": listing, "note": error})
    try:
        for filing, text, url in recent_exhibits(1156375, item="2.02", limit=3):
            rows = parse_rpc(text, source_url=url, filing=filing, fetched_at=fetched_at)
            for point in rows:
                points.setdefault((point["kpi"], point["period"]), point)
            if rows:
                sources.append({"ticker": "CME", "status": "ok", "source_url": url})
    except (OSError, TimeoutError) as exc:
        sources.append({"ticker": "CME", "status": "blocked", "source_url": "https://data.sec.gov/submissions/CIK0001156375.json", "note": str(exc)})
    return list(points.values()), sources
