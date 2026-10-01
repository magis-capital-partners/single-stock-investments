"""Build the study report (HTML) straight from the result files -- no hand-copied numbers."""
from __future__ import annotations

import html
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import fear_vec  # noqa: E402
import gzip  # noqa: E402
from common import BARS, INDEX_SIGNALS, RESULTS as RES, STOCK_SIGNALS, manifest  # noqa: E402

with gzip.open(RES / "index_results.json.gz", "rt", encoding="utf-8") as _fh:
    R = json.load(_fh)
C = json.loads((RES / "cross_section.json").read_text())
S = json.loads((RES / "per_stock_summary.json").read_text())
E = json.loads((RES / "events_summary.json").read_text())
A = json.loads((RES / "auc.json").read_text())
ACC = pd.read_parquet(RES / "bucket_acc.parquet")
ACC["mean"] = ACC["sum"] / ACC["n"]
ACC["hit"] = ACC["npos"] / ACC["n"]
PT = pd.read_csv(RES / "per_stock_table.csv")
MAN = manifest()
esc = html.escape


def pct(x, d=1, sign=True):
    if x is None or (isinstance(x, float) and not math.isfinite(x)):
        return "–"
    s = f"{100 * x:+.{d}f}%" if sign else f"{100 * x:.{d}f}%"
    return s.replace("-", "−")


def num(x, d=3, sign=True):
    if x is None or (isinstance(x, float) and not math.isfinite(x)):
        return "–"
    s = f"{x:+.{d}f}" if sign else f"{x:.{d}f}"
    return s.replace("-", "−")


def tstat(t):
    if t is None or not math.isfinite(t):
        return "–"
    return f"t {t:+.1f}".replace("-", "−")


# ---------------------------------------------------------------------------- SVG kit
class Fig:
    """Tiny SVG builder: every mark can carry a tooltip (data-tip) and stays theme-tokened."""

    def __init__(self, w, h):
        self.w, self.h = w, h
        self.parts: list[str] = []

    def add(self, s):
        self.parts.append(s)

    def svg(self, label):
        return (f'<svg viewBox="0 0 {self.w} {self.h}" role="img" aria-label="{esc(label)}" class="chart" '
                f'preserveAspectRatio="xMidYMid meet">{"".join(self.parts)}</svg>')


def rounded_bar(x0, y0, x1, y1, r=4, horizontal=False, positive=True):
    """Rectangle with 4px rounded data-end, square at the baseline."""
    if horizontal:
        left, right = min(x0, x1), max(x0, x1)
        top, bot = y0, y1
        w = right - left
        r = min(r, w / 2, (bot - top) / 2)
        if w <= 0.5:
            return f"M{left:.1f},{top:.1f}h0.5v{bot - top:.1f}h-0.5z"
        if positive:  # data end at right
            return (f"M{left:.1f},{top:.1f}H{right - r:.1f}Q{right:.1f},{top:.1f} {right:.1f},{top + r:.1f}"
                    f"V{bot - r:.1f}Q{right:.1f},{bot:.1f} {right - r:.1f},{bot:.1f}H{left:.1f}Z")
        return (f"M{right:.1f},{top:.1f}H{left + r:.1f}Q{left:.1f},{top:.1f} {left:.1f},{top + r:.1f}"
                f"V{bot - r:.1f}Q{left:.1f},{bot:.1f} {left + r:.1f},{bot:.1f}H{right:.1f}Z")
    top, bot = min(y0, y1), max(y0, y1)
    left, right = x0, x1
    hgt = bot - top
    r = min(r, (right - left) / 2, hgt / 2)
    if hgt <= 0.5:
        return f"M{left:.1f},{top:.1f}h{right - left:.1f}v0.5h{-(right - left):.1f}z"
    if positive:  # data end at top
        return (f"M{left:.1f},{bot:.1f}V{top + r:.1f}Q{left:.1f},{top:.1f} {left + r:.1f},{top:.1f}"
                f"H{right - r:.1f}Q{right:.1f},{top:.1f} {right:.1f},{top + r:.1f}V{bot:.1f}Z")
    return (f"M{left:.1f},{top:.1f}V{bot - r:.1f}Q{left:.1f},{bot:.1f} {left + r:.1f},{bot:.1f}"
            f"H{right - r:.1f}Q{right:.1f},{bot:.1f} {right:.1f},{bot - r:.1f}V{top:.1f}Z")


def nice_ticks(lo, hi, n=5):
    span = hi - lo
    if span <= 0:
        return [lo]
    raw = span / n
    mag = 10 ** math.floor(math.log10(raw))
    step = min((s * mag for s in (1, 2, 2.5, 5, 10) if s * mag >= raw), default=mag * 10)
    start = math.floor(lo / step) * step
    ticks = []
    v = start
    while v <= hi + step * 0.001:
        if v >= lo - step * 0.001:
            ticks.append(round(v, 10))
        v += step
    return ticks


def hbar_chart(rows, *, ref=None, ref_label="", fmt=lambda v: pct(v, 1), width=760, label="", group_key=None, groups=None):
    """Horizontal bars with optional whiskers (lo, hi) and a dashed-free reference rule."""
    row_h, top, bottom, left, right = 30, 18, 34, 250, 60
    h = top + bottom + row_h * len(rows)
    vals = [r["v"] for r in rows] + [r.get("lo", r["v"]) for r in rows] + [r.get("hi", r["v"]) for r in rows] + ([ref] if ref is not None else []) + [0]
    vmin, vmax = min(vals), max(vals)
    pad = (vmax - vmin) * 0.06
    vmin -= pad
    vmax += pad
    f = Fig(width, h)
    pw = width - left - right
    X = lambda v: left + (v - vmin) / (vmax - vmin) * pw  # noqa: E731
    for t in nice_ticks(vmin, vmax, 6):
        x = X(t)
        f.add(f'<line class="grid" x1="{x:.1f}" x2="{x:.1f}" y1="{top - 6}" y2="{h - bottom + 4}"/>')
        f.add(f'<text class="tick" x="{x:.1f}" y="{h - bottom + 20}" text-anchor="middle">{esc(fmt(t))}</text>')
    x0 = X(0)
    f.add(f'<line class="axis" x1="{x0:.1f}" x2="{x0:.1f}" y1="{top - 6}" y2="{h - bottom + 4}"/>')
    for i, r in enumerate(rows):
        yc = top + i * row_h + row_h / 2
        cls = r.get("cls", "m1")
        y0, y1 = yc - 8, yc + 8
        path = rounded_bar(x0, y0, X(r["v"]), y1, horizontal=True, positive=r["v"] >= 0)
        tip = esc(r.get("tip", ""))
        f.add(f'<g class="hit" tabindex="0" data-tip="{tip}"><rect class="hitbox" x="{left}" y="{yc - row_h / 2:.1f}" width="{pw}" height="{row_h}"/>'
              f'<path class="{cls}" d="{path}"/>')
        if "lo" in r and r["lo"] is not None:
            f.add(f'<line class="whisker" x1="{X(r["lo"]):.1f}" x2="{X(r["hi"]):.1f}" y1="{yc:.1f}" y2="{yc:.1f}"/>'
                  f'<line class="whisker" x1="{X(r["lo"]):.1f}" x2="{X(r["lo"]):.1f}" y1="{yc - 5:.1f}" y2="{yc + 5:.1f}"/>'
                  f'<line class="whisker" x1="{X(r["hi"]):.1f}" x2="{X(r["hi"]):.1f}" y1="{yc - 5:.1f}" y2="{yc + 5:.1f}"/>')
        f.add("</g>")
        f.add(f'<text class="rowlabel" x="{left - 10}" y="{yc + 4:.1f}" text-anchor="end">{esc(r["label"])}</text>')
        vx = max(X(r["v"]), X(r.get("hi", r["v"]) or r["v"])) + 6
        f.add(f'<text class="val" x="{vx:.1f}" y="{yc + 4:.1f}">{esc(fmt(r["v"]))}</text>')
    if ref is not None:
        xr = X(ref)
        f.add(f'<line class="ref" x1="{xr:.1f}" x2="{xr:.1f}" y1="{top - 10}" y2="{h - bottom + 4}"/>'
              f'<text class="reflabel" x="{xr + 4:.1f}" y="{top - 2}">{esc(ref_label)}</text>')
    return f.svg(label)


def column_chart(cats, vals, *, width=330, height=210, fmt=lambda v: pct(v, 1), label="", diverging=True, tips=None, ylab=None, cls_fixed=None, extra_ref=None):
    top, bottom, left, right = 16, 38, 46, 8
    f = Fig(width, height)
    vmin, vmax = min(0, min(vals)), max(0, max(vals))
    pad = (vmax - vmin) * 0.08 or 0.01
    vmin -= pad if vmin < 0 else 0
    vmax += pad
    ph = height - top - bottom
    pw = width - left - right
    Y = lambda v: top + (vmax - v) / (vmax - vmin) * ph  # noqa: E731
    for t in nice_ticks(vmin, vmax, 4):
        y = Y(t)
        f.add(f'<line class="grid" x1="{left}" x2="{width - right}" y1="{y:.1f}" y2="{y:.1f}"/>'
              f'<text class="tick" x="{left - 6}" y="{y + 3.5:.1f}" text-anchor="end">{esc(fmt(t))}</text>')
    y0 = Y(0)
    f.add(f'<line class="axis" x1="{left}" x2="{width - right}" y1="{y0:.1f}" y2="{y0:.1f}"/>')
    if extra_ref is not None:
        yr = Y(extra_ref[0])
        f.add(f'<line class="ref" x1="{left}" x2="{width - right}" y1="{yr:.1f}" y2="{yr:.1f}"/>'
              f'<text class="reflabel" x="{width - right}" y="{yr - 4:.1f}" text-anchor="end">{esc(extra_ref[1])}</text>')
    band = pw / len(cats)
    bw = min(24, band * 0.62)
    for i, (c, v) in enumerate(zip(cats, vals)):
        xc = left + band * i + band / 2
        cls = cls_fixed or ("m1" if (v >= 0 or not diverging) else "mneg")
        path = rounded_bar(xc - bw / 2, Y(v), xc + bw / 2, y0, positive=v >= 0)
        tip = esc(tips[i] if tips else f"{c}: {fmt(v)}")
        f.add(f'<g class="hit" tabindex="0" data-tip="{tip}"><rect class="hitbox" x="{xc - band / 2:.1f}" y="{top}" width="{band:.1f}" height="{ph}"/>'
              f'<path class="{cls}" d="{path}"/></g>')
        f.add(f'<text class="tick" x="{xc:.1f}" y="{height - bottom + 15}" text-anchor="middle">{esc(str(c))}</text>')
    if ylab:
        f.add(f'<text class="axlabel" x="{left + pw / 2:.1f}" y="{height - 4}" text-anchor="middle">{esc(ylab)}</text>')
    return f.svg(label)


def grouped_columns(cats, series, *, width=760, height=260, fmt=lambda v: pct(v, 1), label=""):
    """series: list of (name, cls, values, los, his, tips)."""
    top, bottom, left, right = 16, 46, 52, 8
    f = Fig(width, height)
    allv = [0.0]
    for _, _, vs, lo, hi, _ in series:
        allv += [v for v in vs if v is not None] + [x for x in (lo or []) if x is not None] + [x for x in (hi or []) if x is not None]
    vmin, vmax = min(allv), max(allv)
    pad = (vmax - vmin) * 0.08
    vmin -= pad
    vmax += pad
    ph = height - top - bottom
    pw = width - left - right
    Y = lambda v: top + (vmax - v) / (vmax - vmin) * ph  # noqa: E731
    for t in nice_ticks(vmin, vmax, 5):
        y = Y(t)
        f.add(f'<line class="grid" x1="{left}" x2="{width - right}" y1="{y:.1f}" y2="{y:.1f}"/>'
              f'<text class="tick" x="{left - 6}" y="{y + 3.5:.1f}" text-anchor="end">{esc(fmt(t))}</text>')
    y0 = Y(0)
    f.add(f'<line class="axis" x1="{left}" x2="{width - right}" y1="{y0:.1f}" y2="{y0:.1f}"/>')
    band = pw / len(cats)
    k = len(series)
    bw = min(22, band * 0.7 / k)
    gap = 2
    for i, c in enumerate(cats):
        xc = left + band * i + band / 2
        start = xc - (k * bw + (k - 1) * gap) / 2
        for j, (name, cls, vs, lo, hi, tips) in enumerate(series):
            v = vs[i]
            if v is None:
                continue
            x0 = start + j * (bw + gap)
            path = rounded_bar(x0, Y(v), x0 + bw, y0, positive=v >= 0)
            tip = esc(tips[i] if tips else f"{name} · {c}: {fmt(v)}")
            f.add(f'<g class="hit" tabindex="0" data-tip="{tip}"><rect class="hitbox" x="{x0 - 1:.1f}" y="{top}" width="{bw + 2:.1f}" height="{ph}"/>'
                  f'<path class="{cls}" d="{path}"/>')
            if lo and lo[i] is not None:
                xm = x0 + bw / 2
                f.add(f'<line class="whisker" x1="{xm:.1f}" x2="{xm:.1f}" y1="{Y(lo[i]):.1f}" y2="{Y(hi[i]):.1f}"/>')
            f.add("</g>")
        words = str(c).split(" ")
        if len(c) > 16 and len(words) > 1:
            cut = max(1, len(words) // 2)
            l1, l2 = " ".join(words[:cut]), " ".join(words[cut:])
            f.add(f'<text class="tick" x="{xc:.1f}" y="{height - bottom + 15}" text-anchor="middle">{esc(l1)}'
                  f'<tspan x="{xc:.1f}" dy="13">{esc(l2)}</tspan></text>')
        else:
            f.add(f'<text class="tick" x="{xc:.1f}" y="{height - bottom + 15}" text-anchor="middle">{esc(c)}</text>')
    return f.svg(label)


def legend(items):
    return '<div class="legend">' + "".join(
        f'<span class="key"><svg width="14" height="10" aria-hidden="true"><rect class="{cls}" x="0" y="0" width="14" height="10" rx="2"/></svg>{esc(name)}</span>'
        for name, cls in items) + "</div>"


def table_html(headers, rows, cls="data"):
    head = "".join(f"<th>{esc(h)}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f'<div class="tablewrap"><table class="{cls}"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def figure(title, sub, svg_html, table, note="", legend_html=""):
    return f"""<figure class="fig">
  <figcaption><strong>{esc(title)}</strong><span>{sub}</span></figcaption>
  {legend_html}
  <div class="plot">{svg_html}</div>
  <details class="tableview"><summary>Show the numbers</summary>{table}</details>
  {f'<p class="fignote">{note}</p>' if note else ''}
</figure>"""


# ---------------------------------------------------------------------------- data helpers
SPY = R["ladder"]["SPY"]
SPYC = SPY["conditions"]
UNC63 = SPYC["published_normal"]["h63"]["uncond_mean"]
GSPC = R["ladder"]["^GSPC"]
MAC = R["macro"]["SPY"]


def acc_table(dim, era="ALL"):
    a = ACC[(ACC["dim"] == dim) & (ACC["era"] == era)]
    p = a.pivot_table(index="bucket", columns="outcome", values=["mean", "hit", "n"])
    return p


def cond_row(key, label, cls="m1"):
    v = SPYC[key]["h63"]
    se = v["diff_vs_uncond"] / v["diff_t_nw"] if v["diff_t_nw"] not in (0, None) and math.isfinite(v["diff_t_nw"]) else None
    m = v["all_days_mean"]
    lo, hi = (m - 1.96 * abs(se), m + 1.96 * abs(se)) if se is not None and m is not None else (None, None)
    days = SPYC[key]["days"]
    tip = (f"{label}: {pct(m, 2)} average 63-session return over {days:,} days "
           f"({pct(v['diff_vs_uncond'], 2)} vs all days, {tstat(v['diff_t_nw'])}); hit rate {pct(v['all_days_hit'], 0, False)}")
    return {"label": label, "v": m, "lo": lo, "hi": hi, "cls": cls, "tip": tip, "days": days, "diff": v["diff_vs_uncond"],
            "t": v["diff_t_nw"], "hit": v["all_days_hit"], "entries": SPYC[key]["entries"]}


# ---------------------------------------------------------------------------- figures
def fig_spy_conditions():
    ladder = [("published_normal", "Ladder: normal"), ("published_observe", "Ladder: observe"),
              ("published_stress", "Ladder: stress"), ("published_exhaustion_candidate", "Ladder: exhaustion candidate"),
              ("raw_confirmed", "Raw confirmed (never published)"),
              ("meaningful_exh_ge65", "“Meaningful” exhaustion ≥ 65"), ("meaningful_exh_lt45", "Stressed drawdown, exhaustion < 45"),
              ("panic_ge90", "Panic score ≥ 90")]
    simple = [("baseline_dd_le_10", "Simple rule: SPY ≥ 10% off high"), ("baseline_rsi_lt_30", "Simple rule: RSI(14) < 30"),
              ("baseline_ret5_le_-5", "Simple rule: 5-day drop ≥ 5%"), ("baseline_vix_ge_30", "Simple rule: VIX ≥ 30")]
    rows = [cond_row(k, l, "m1") for k, l in ladder] + [cond_row(k, l, "mgray") for k, l in simple]
    svg = hbar_chart(rows, ref=UNC63, ref_label=f"all days {pct(UNC63, 1)}", fmt=lambda v: pct(v, 0), label="SPY 63-session forward return by condition")
    tab = table_html(["Condition", "Days", "Entries", "Avg 63-session return", "vs all days", "HAC t", "Hit rate"],
                     [[esc(r["label"]), f"{r['days']:,}", f"{r['entries']:,}", pct(r["v"], 2), pct(r["diff"], 2), tstat(r["t"]), pct(r["hit"], 0, False)] for r in rows])
    return figure("SPY, 63 sessions after each condition (1993–2026)",
                  "Average return from the next session's close. Whiskers: 95% Newey-West interval. The published ladder never reached “confirmed exhaustion”.",
                  svg, tab, legend_html=legend([("Dashboard ladder / scores", "m1"), ("Simple rules for comparison", "mgray")]))


def fig_spy_deciles():
    out = []
    tabs = []
    for score, title in (("panic", "Panic decile → 63-session return"), ("exhaustion", "Exhaustion decile → 63-session return")):
        d = SPY["deciles"][score]["h63"]["deciles"]
        vals = [x["mean"] for x in d]
        cats = [str(x["decile"]) for x in d]
        tips = [f"Decile {x['decile']} ({x['score_lo']:.0f}–{x['score_hi']:.0f}): {pct(x['mean'], 2)}, hit {pct(x['hit'], 0, False)}" for x in d]
        ic = SPY["deciles"][score]["h63"]
        out.append(f'<div class="mini"><div class="minititle">{esc(title)}<small>IC {num(ic["ic"])} · {tstat(ic["slope_t_nw"])}</small></div>'
                   + column_chart(cats, vals, tips=tips, label=title, extra_ref=(UNC63, "all days"), ylab="decile (1 = calmest)") + "</div>")
        tabs.append([title] + [pct(v, 2) for v in vals])
    fv = SPY["deciles"]["panic"]["fwd_vol21_by_decile"]
    out.append(f'<div class="mini"><div class="minititle">Panic decile → next-month volatility<small>IC {num(SPY["deciles"]["panic"]["fwd_vol21_ic"])}</small></div>'
               + column_chart([str(i) for i in range(1, 11)], fv, fmt=lambda v: pct(v, 0, False), diverging=False, cls_fixed="m1",
                              tips=[f"Decile {i + 1}: {pct(v, 1, False)} annualized volatility over the next 21 sessions" for i, v in enumerate(fv)],
                              label="panic decile vs forward volatility", ylab="decile (1 = calmest)") + "</div>")
    tabs.append(["Panic decile → next-month volatility"] + [pct(v, 1, False) for v in fv])
    tab = table_html(["Series"] + [f"D{i}" for i in range(1, 11)], tabs)
    return figure("SPY: the score predicts volatility, not returns",
                  "Deciles of each daily score, 1993–2026. A useful return signal would slope steadily; panic is flat until the top decile, exhaustion slopes the wrong way.",
                  f'<div class="minis">{"".join(out)}</div>', tab)


def fig_timeline():
    bars = fear_vec.production_rows(pd.read_parquet(BARS / MAN["SPY"]["file"]))
    sig = pd.read_parquet(INDEX_SIGNALS / "SPY.parquet")
    df = bars.merge(sig[["date", "state", "raw_state"]], on="date", how="inner")
    df["d"] = pd.to_datetime(df["date"])
    wk = df.set_index("d").resample("W-FRI").agg({"close": "last", "state": "max", "date": "last"}).dropna()
    width, height, top, bottom, left, right = 960, 300, 14, 30, 48, 12
    f = Fig(width, height)
    t0, t1 = df["d"].iloc[0], df["d"].iloc[-1]
    X = lambda d: left + (d - t0).days / (t1 - t0).days * (width - left - right)  # noqa: E731
    lo, hi = math.log(20), math.log(800)
    Y = lambda v: top + (hi - math.log(v)) / (hi - lo) * (height - top - bottom)  # noqa: E731
    for v in (25, 50, 100, 200, 400, 800):
        y = Y(v)
        f.add(f'<line class="grid" x1="{left}" x2="{width - right}" y1="{y:.1f}" y2="{y:.1f}"/><text class="tick" x="{left - 6}" y="{y + 3.5:.1f}" text-anchor="end">${v}</text>')
    for yr in range(1994, 2027, 4):
        x = X(pd.Timestamp(f"{yr}-01-01"))
        f.add(f'<text class="tick" x="{x:.1f}" y="{height - 10}" text-anchor="middle">{yr}</text>')
    # shaded runs of published state >= stress
    st = df["state"].to_numpy()
    runs, start = [], None
    for i, s in enumerate(st):
        if s >= 2 and start is None:
            start = i
        if (s < 2 or i == len(st) - 1) and start is not None:
            runs.append((start, i))
            start = None
    for a, b in runs:
        xa, xb = X(df["d"].iloc[a]), X(df["d"].iloc[b])
        f.add(f'<rect class="band" x="{xa:.1f}" y="{top}" width="{max(1.5, xb - xa):.1f}" height="{height - top - bottom}"/>')
    pts = " ".join(f"{X(d):.1f},{Y(c):.1f}" for d, c in zip(wk.index, wk["close"]))
    f.add(f'<polyline class="line1" points="{pts}"/>')
    ent = df[(df["state"] >= 3) & (df["state"].shift(1) < 3)]
    for _, r in ent.iterrows():
        f.add(f'<g class="hit" tabindex="0" data-tip="Exhaustion candidate published {r["date"]} at ${r["close"]:.0f}"><circle class="dot2" cx="{X(r["d"]):.1f}" cy="{Y(r["close"]):.1f}" r="5"/></g>')
    raw = df[df["raw_state"] == 4]
    for _, r in raw.iterrows():
        f.add(f'<g class="hit" tabindex="0" data-tip="Raw confirmed exhaustion {r["date"]} (suppressed by the 2-session dwell)"><circle class="dot3" cx="{X(r["d"]):.1f}" cy="{Y(r["close"]):.1f}" r="4.5"/></g>')
    f.add(f'<line class="xhair" id="tl-x" x1="0" x2="0" y1="{top}" y2="{height - bottom}" visibility="hidden"/>')
    f.add(f'<rect class="tl-catch" x="{left}" y="{top}" width="{width - left - right}" height="{height - top - bottom}"/>')
    data = {"x": [round(X(d), 1) for d in wk.index], "d": list(wk["date"]), "c": [round(float(c), 2) for c in wk["close"]],
            "s": [int(s) for s in wk["state"]]}
    script = f"<script>window.__TL={json.dumps(data, separators=(',', ':'))};</script>"
    tab = table_html(["Event", "Dates"], [
        ["Exhaustion candidate published (6)", esc(", ".join(ent["date"]))],
        ["Raw confirmed exhaustion, never published (15)", esc(", ".join(raw["date"]))],
        ["Weeks with ladder at stress or above", f"{int((wk['state'] >= 2).sum())} of {len(wk)}"],
    ])
    return figure("SPY 1993–2026 with the replayed ladder",
                  "Log price. Shaded: published “stress” or above. Orange: the six published exhaustion candidates. Green: raw confirmed-exhaustion days the 2-session dwell suppressed.",
                  f'<div class="tl" id="timeline">{f.svg("SPY price with ladder states")}</div>{script}', tab,
                  legend_html=legend([("SPY (log scale)", "m1"), ("Ladder ≥ stress", "mband"), ("Exhaustion candidate", "m2"), ("Raw confirmed (suppressed)", "m3")]))


def fig_stock_buckets():
    p = acc_table("panic")
    buckets = [b for b in p.index if p.loc[b, ("n", "x63")] >= 1000]
    cats = [f"{10 * b}–{10 * b + 10}" for b in buckets]
    x63 = [p.loc[b, ("mean", "x63")] for b in buckets]
    hit = [p.loc[b, ("hit", "x63")] for b in buckets]
    n = [int(p.loc[b, ("n", "x63")]) for b in buckets]
    mae = [p.loc[b, ("hit", "mae63_lt_15")] for b in buckets]
    vol = [p.loc[b, ("mean", "vol21")] for b in buckets]
    base = ACC[(ACC["dim"] == "all") & (ACC["era"] == "ALL") & (ACC["outcome"] == "x63")]["mean"].iloc[0]
    base_mae = ACC[(ACC["dim"] == "all") & (ACC["era"] == "ALL") & (ACC["outcome"] == "mae63_lt_15")]["hit"].iloc[0]
    tips = [f"Panic {c}: {pct(v, 2)} vs SPY over 63 sessions; beat SPY {pct(h, 0, False)} of the time; {k:,} stock-days" for c, v, h, k in zip(cats, x63, hit, n)]
    a = column_chart(cats, x63, width=470, height=230, tips=tips, fmt=lambda v: pct(v, 1), label="panic bucket vs 63-session excess return",
                     extra_ref=(base, "all days"), ylab="panic score at the close")
    tips2 = [f"Panic {c}: {pct(m, 0, False)} fell another 15%+ within 63 sessions" for c, m in zip(cats, mae)]
    b = column_chart(cats, mae, width=470, height=230, tips=tips2, fmt=lambda v: pct(v, 0, False), diverging=False, cls_fixed="m1",
                     label="panic bucket vs further 15% drop", extra_ref=(base_mae, "all days"), ylab="panic score at the close")
    tab = table_html(["Panic", "Stock-days", "63-session excess (log)", "Beat SPY", "Fell 15%+ more", "Next-month vol"],
                     [[c, f"{k:,}", pct(v, 2), pct(h, 1, False), pct(m, 1, False), pct(vv, 0, False)] for c, k, v, h, m, vv in zip(cats, n, x63, hit, mae, vol)])
    return figure("All stocks: what followed each level of the panic score",
                  "4.9 million stock-days, 1962–2026, after a 3-year warm-up per stock. Excess = log return minus SPY's (local index abroad), from the next close.",
                  f'<div class="minis two"><div class="mini"><div class="minititle">63-session return vs SPY</div>{a}</div>'
                  f'<div class="mini"><div class="minititle">Share that fell another 15%+ within 63 sessions</div>{b}</div></div>', tab)


def fig_events():
    names = [("stress_building", "Stress building"), ("panic_or_worse", "Panic"), ("phase_falling_knife", "“Falling knife”"),
             ("candidate_or_worse", "Capitulation candidate"), ("emerging_or_confirmed", "Exhaustion emerging/confirmed")]
    regimes = [("spy_normal", "SPY calm", "m1"), ("spy_stress_building", "SPY stress building", "m2"), ("spy_panic_or_worse", "SPY in panic", "m3")]
    series = []
    rows = []
    for rk, rl, cls in regimes:
        vs, lo, hi, tips = [], [], [], []
        for k, label in names:
            blk = E["by_market"].get(k, {}).get(rk)
            if not blk:
                vs.append(None); lo.append(None); hi.append(None); tips.append("")
                continue
            m = blk["x_nc_63"]
            vs.append(m["mean"]); lo.append(m["ci95"][0]); hi.append(m["ci95"][1])
            tips.append(f"{label} while {rl.lower()}: {pct(m['mean'], 2)} vs SPY over 63 sessions (95% CI {pct(m['ci95'][0], 1)} to {pct(m['ci95'][1], 1)}), {blk['events']:,} entries in {blk['months']} months")
            rows.append([esc(label), esc(rl), f"{blk['events']:,}", f"{blk['months']}", pct(m["mean"], 2), f"{pct(m['ci95'][0], 1)} to {pct(m['ci95'][1], 1)}",
                         pct(m["hit"], 0, False), pct(blk["r_nc_63"]["mean"], 1), pct(blk["p_mae63_lt_-15"], 0, False)])
        series.append((rl, cls, vs, lo, hi, tips))
    svg = grouped_columns([l for _, l in names], series, width=860, height=280, label="state entry by market regime")
    tab = table_html(["Stock state entered", "Market (SPY fear model)", "Entries", "Months", "63-session excess", "95% CI (month clusters)", "Beat SPY", "Total return", "Fell 15%+ more"], rows)
    return figure("A stock panicking alone is not a stock panicking with the market",
                  "63-session log return vs SPY after a stock enters each state, split by the SPY fear state that day. Whiskers: 95% interval, resampling calendar months.",
                  svg, tab, legend_html=legend([(l, c) for _, l, c in regimes]))


def fig_cross_section_eras():
    eras = ["1975-1989", "1990-1999", "2000-2009", "2010-2019", "2020-2026"]
    p = [C["ic|panic|x21"]["by_era"][e]["mean"] for e in eras]
    r = [-C["ic|ret5|x21"]["by_era"][e]["mean"] for e in eras]
    pt_ = [C["ic|panic|x21"]["by_era"][e]["t"] for e in eras]
    rt_ = [C["ic|ret5|x21"]["by_era"][e]["t"] for e in eras]
    series = [("Panic score", "m1", p, None, None, [f"Panic, {e}: IC {num(v)} ({tstat(t)})" for e, v, t in zip(eras, p, pt_)]),
              ("Last 5 days' loss (simple reversal)", "mgray", r, None, None, [f"5-day reversal, {e}: IC {num(v)} ({tstat(-t)})" for e, v, t in zip(eras, r, rt_)])]
    svg = grouped_columns([e.replace("-", "–") for e in eras], series, width=760, height=250, fmt=lambda v: num(v, 2), label="cross-sectional IC by era")
    tab = table_html(["Era", "Panic IC (21-session)", "t", "5-day reversal IC", "t"],
                     [[e, num(a), tstat(at), num(b), tstat(-bt)] for e, a, at, b, bt in zip(eras, p, pt_, r, rt_)])
    return figure("Ranking stocks by panic: a fading short-term reversal",
                  "Average daily rank correlation between each US stock's panic score and its next-21-session return vs SPY, ranked against all other stocks that day.",
                  svg, tab, legend_html=legend([("Panic score", "m1"), ("Last 5 days' loss (simple reversal)", "mgray")]))


def fig_per_stock_hist():
    ps = pd.read_parquet(RES / "per_stock.parquet")
    ps = ps[ps["usable_rows"] >= 756]
    zz = (ps["panic_x63_ic"] / ps["panic_x63_null_sd"]).to_numpy(float)
    zz = zz[np.isfinite(zz)]
    edges = np.arange(-4, 4.01, 0.5)
    counts, _ = np.histogram(np.clip(zz, -3.99, 3.99), bins=edges)
    width, height, top, bottom, left, right = 760, 250, 16, 40, 48, 10
    f = Fig(width, height)
    ymax = max(counts.max(), len(zz) * 0.5 * 0.4) * 1.1
    pw, ph = width - left - right, height - top - bottom
    X = lambda v: left + (v + 4) / 8 * pw  # noqa: E731
    Y = lambda c: top + (ymax - c) / ymax * ph  # noqa: E731
    for t in nice_ticks(0, ymax, 4):
        f.add(f'<line class="grid" x1="{left}" x2="{width - right}" y1="{Y(t):.1f}" y2="{Y(t):.1f}"/><text class="tick" x="{left - 6}" y="{Y(t) + 3.5:.1f}" text-anchor="end">{int(t)}</text>')
    f.add(f'<line class="axis" x1="{left}" x2="{width - right}" y1="{Y(0):.1f}" y2="{Y(0):.1f}"/>')
    for i, c in enumerate(counts):
        x0, x1 = X(edges[i]) + 1, X(edges[i + 1]) - 1
        lo_e, hi_e = edges[i], edges[i + 1]
        f.add(f'<g class="hit" tabindex="0" data-tip="{int(c)} stocks with z between {lo_e:+.1f} and {hi_e:+.1f}"><rect class="hitbox" x="{x0:.1f}" y="{top}" width="{x1 - x0:.1f}" height="{ph}"/>'
              f'<path class="m1" d="{rounded_bar(x0, Y(c), x1, Y(0))}"/></g>')
    xs = np.linspace(-4, 4, 161)
    dens = len(zz) * 0.5 * np.exp(-xs ** 2 / 2) / math.sqrt(2 * math.pi)
    pts = " ".join(f"{X(x):.1f},{Y(d):.1f}" for x, d in zip(xs, dens))
    f.add(f'<polyline class="line-ref" points="{pts}"/>')
    for t in range(-4, 5):
        f.add(f'<text class="tick" x="{X(t):.1f}" y="{height - bottom + 16}" text-anchor="middle">{t:+d}</text>'.replace("+0", "0"))
    f.add(f'<text class="axlabel" x="{left + pw / 2:.1f}" y="{height - 4}" text-anchor="middle">z-score of each stock’s panic → 63-session excess-return correlation vs its own shuffled-in-time null</text>')
    s63 = S["x63"]
    tab = table_html(["Measure", "Value"], [
        ["Stocks tested (≥ 3 usable years after warm-up)", f"{S['stocks']:,}"],
        ["Median correlation (IC)", num(s63["median_ic"])],
        ["Share of stocks with positive IC", pct(s63["share_positive"], 0, False)],
        ["Share significant at 5% (pure chance would give 5%)", pct(s63["share_p_lt_05"], 1, False)],
        ["Stocks that survive a 10% false-discovery screen", f"{s63['fdr10_count']} ({s63['fdr10_pos']} positive, {s63['fdr10_neg']} negative)"],
        ["Typical variance explained (median IC²)", pct(s63["r2_implied_median"], 2, False)],
        ["Between-stock spread of the true effect (τ)", num(s63["between_stock_sd_tau"], 3, False)],
        ["Typical noise in one stock's IC (null SD)", num(s63["mean_null_sd"], 3, False)],
    ])
    return figure("Stock by stock: one small common effect, not a per-stock edge",
                  "Each stock's panic-to-future-return correlation, divided by the spread you'd get by chance from that stock's own history. Gray curve: what pure noise would look like.",
                  f.svg("per-stock z-score histogram"), tab, legend_html=legend([("Stocks", "m1"), ("Expected if the score carried no information", "mgray")]))


# ---------------------------------------------------------------------------- tables
def index_table():
    rows = []
    order = ["SPY", "^GSPC", "QQQ", "^NDX", "IWM", "^RUT", "DIA", "EFA", "EEM", "EWJ", "HYG", "LQD", "TLT",
             "XLB", "XLC", "XLE", "XLF", "XLI", "XLK", "XLP", "XLRE", "XLU", "XLV", "XLY"]
    for sym in order:
        res = R["ladder"][sym]
        c = res["conditions"]
        st = c["published_ge_stress"]["h63"]
        rows.append([esc(sym.replace("^GSPC", "S&P 500 index").replace("^NDX", "Nasdaq-100 index").replace("^RUT", "Russell 2000 index")),
                     res["first"][:4], pct(st["uncond_mean"], 1), f"{c['published_ge_stress']['entries']}",
                     f"{pct(st['diff_vs_uncond'], 1)} ({tstat(st['diff_t_nw'])})",
                     num(res["deciles"]["panic"]["h63"]["ic"]), num(res["deciles"]["exhaustion"]["h63"]["ic"]),
                     num(res["deciles"]["panic"]["fwd_vol21_ic"], 2)])
    return table_html(["Index / ETF", "From", "Avg 63-session return", "Stress entries", "63-session edge when ≥ stress", "Panic IC", "Exhaustion IC", "Panic → vol IC"], rows)


def timing_table():
    labels = {"published_ge_stress": "Published ladder ≥ stress", "published_exhaustion_candidate": "Published exhaustion candidate",
              "raw_ge_candidate": "Raw ≥ exhaustion candidate", "raw_confirmed": "Raw confirmed exhaustion",
              "meaningful_exh_ge65": "“Meaningful” exhaustion ≥ 65", "panic_ge80": "Panic ≥ 80",
              "baseline_rsi_lt_30": "Simple rule: RSI(14) < 30", "baseline_dd_le_20": "Simple rule: ≥ 20% off high"}
    rows = []
    for k, l in labels.items():
        v = SPY["timing"][k]
        rows.append([esc(l), f"{v['signal_entries']}", pct(v["recall_at_k"], 0, False), "–" if v["precision_at_k"] is None else pct(v["precision_at_k"], 0, False)])
    return table_html(["Signal (SPY, 1993–2026)", "Times it fired", f"Bottoms caught (of {SPY['episodes']})", "Firings that were near a bottom"], rows)


def state_table():
    rows = []
    labels = [("stress_building", "Stress building"), ("panic_or_worse", "Panic or worse"), ("phase_falling_knife", "“Falling knife” phase"),
              ("phase_stabilizing", "“Stabilizing” phase"), ("candidate_or_worse", "Capitulation candidate or worse"),
              ("emerging_or_confirmed", "Exhaustion emerging or confirmed"), ("confirmed_exhaustion", "Confirmed exhaustion")]
    base = E["baseline"]
    for k, l in labels:
        v = E["events"][k]
        m = v["x_nc_63"]
        rows.append([esc(l), f"{v['events']:,}", f"{v['stocks']}", pct(m["mean"], 2), f"{pct(m['ci95'][0], 1)} to {pct(m['ci95'][1], 1)}",
                     pct(m["hit"], 0, False), pct(v["p_mae63_lt_-15"], 0, False), pct(v["fwd_vol21"], 0, False)])
    rows.append(["<em>Every stock-day (baseline)</em>", f"{base['x63']['n']:,}", "", pct(base["x63"]["mean"], 2), "", pct(base["x63"]["hit"], 0, False),
                 pct(base["mae63_lt_15"]["hit"], 0, False), pct(base["vol21"]["mean"], 0, False)])
    return table_html(["State entered", "Entries", "Stocks", "63-session excess", "95% CI", "Beat SPY", "Fell 15%+ more", "Next-month vol"], rows)


def per_stock_rows():
    ps = pd.read_parquet(RES / "per_stock.parquet")
    keep = PT.merge(ps[["symbol", "usable_rows"]].rename(columns={"usable_rows": "ur"}), on="symbol", how="left")
    out = []
    for r in keep.itertuples(index=False):
        if not (isinstance(r.panic_x63_ic, float) and math.isfinite(r.panic_x63_ic)):
            continue
        years = r.usable_rows / 252.0
        if years < 5:
            verdict, vcls = "Too short to judge", "v-na"
        elif r.panic_x63_fdr10 and r.panic_x63_ic > 0:
            verdict, vcls = "Fear preceded outperformance", "v-pos"
        elif r.panic_x63_fdr10 and r.panic_x63_ic < 0:
            verdict, vcls = "Fear preceded underperformance", "v-neg"
        else:
            verdict, vcls = "No reliable link", "v-none"
        d70 = (r.x63_panic70 - r.x63_all) if (isinstance(r.x63_panic70, float) and math.isfinite(r.x63_panic70)) else float("nan")
        out.append({"t": r.ticker, "f": str(r.first)[:4], "y": round(years, 1), "pd": int(r.days_panic), "ic21": r.panic_x21_ic, "ic63": r.panic_x63_ic,
                    "sh": r.panic_x63_ic_shrunk, "p": r.panic_x63_p, "d70": d70, "h70": r.hit_x63_panic70, "v": verdict, "vc": vcls})
    return out


def per_stock_table_html(rows):
    def cell(v, kind):
        if v is None or (isinstance(v, float) and not math.isfinite(v)):
            return '<td data-v="">–</td>'
        if kind == "ic":
            return f'<td data-v="{v:.4f}">{num(v)}</td>'
        if kind == "p":
            return f'<td data-v="{v:.4f}">{v:.3f}</td>'
        if kind == "pct":
            return f'<td data-v="{v:.5f}">{pct(v, 1)}</td>'
        if kind == "pct0":
            return f'<td data-v="{v:.5f}">{pct(v, 0, False)}</td>'
        return f'<td data-v="{v}">{v}</td>'
    body = []
    for r in sorted(rows, key=lambda r: r["t"]):
        body.append(f'<tr><th scope="row" data-v="{esc(r["t"])}">{esc(r["t"])}</th><td data-v="{r["f"]}">{r["f"]}</td><td data-v="{r["y"]}">{r["y"]}</td>'
                    f'<td data-v="{r["pd"]}">{r["pd"]:,}</td>{cell(r["ic21"], "ic")}{cell(r["ic63"], "ic")}{cell(r["sh"], "ic")}{cell(r["p"], "p")}'
                    f'{cell(r["d70"], "pct")}{cell(r["h70"], "pct0")}<td data-v="{esc(r["v"])}"><span class="verdict {r["vc"]}">{esc(r["v"])}</span></td></tr>')
    heads = [("Ticker", "s"), ("Data from", "n"), ("Usable years", "n"), ("Days in panic", "n"), ("IC 21d", "n"), ("IC 63d", "n"),
             ("IC 63d, shrunk", "n"), ("p-value", "n"), ("63d excess when panic ≥ 70, vs normal", "n"), ("Beat SPY when panic ≥ 70", "n"), ("Verdict", "s")]
    th = "".join(f'<th scope="col"><button type="button" data-col="{i}" data-kind="{k}">{esc(h)}</button></th>' for i, (h, k) in enumerate(heads))
    return f'<div class="tablewrap tall"><table class="data sortable" id="stocks"><thead><tr>{th}</tr></thead><tbody>{"".join(body)}</tbody></table></div>'


# ---------------------------------------------------------------------------- page
def build() -> str:
    s63 = S["x63"]
    ps_rows = per_stock_rows()
    n_judged = sum(1 for r in ps_rows if r["vc"] != "v-na")
    n_pos = sum(1 for r in ps_rows if r["vc"] == "v-pos")
    n_neg = sum(1 for r in ps_rows if r["vc"] == "v-neg")
    stress = cond_row("published_ge_stress", "")
    gst = GSPC["conditions"]["published_ge_stress"]["h63"]
    ic21 = C["ic|panic|x21"]
    ic63 = C["ic|panic|x63"]
    fmb21 = C["fmb|panic|x21|panic"]
    sp21 = C["spread|panic|x21"]
    sp252 = C["spread|panic|x252"]
    exh21 = C["ic|exhaustion|x21"]
    era26 = C["ic|panic|x21"]["by_era"]["2020-2026"]
    base = E["baseline"]
    ev = E["events"]
    rv20_auc = A["rv20"]["auc_vol21_gt_median"]
    stab_days = acc_table("phase").loc[3, ("n", "x63")] / acc_table("all").loc[0, ("n", "x63")]
    n_stockdays = int(base["x63"]["n"])
    mac_stab = MAC["conditions"]["phase_stabilizing"]["share"]
    n_replayed = len(list(STOCK_SIGNALS.glob("*.parquet")))
    n_young = n_replayed - 1 - S["stocks"]  # minus DNP (wrong security)
    pb = acc_table("panic")
    pbk = [b for b in pb.index if pb.loc[b, ("n", "x63")] >= 1000]
    vol_lo, vol_hi = pb.loc[pbk[0], ("mean", "vol21")], pb.loc[pbk[-1], ("mean", "vol21")]
    dd_lo, dd_hi = pb.loc[pbk[0], ("hit", "mae63_lt_15")], pb.loc[pbk[-1], ("hit", "mae63_lt_15")]
    syms = list(R["ladder"])
    n_exh_neg = sum(R["ladder"][k]["deciles"]["exhaustion"]["h63"]["ic"] < 0 for k in syms)
    n_vol_pos = sum(R["ladder"][k]["deciles"]["panic"]["fwd_vol21_ic"] > 0 for k in syms)

    score_rows = [
        ["Index ladder (risk page): “stress” rung", "Selloff in progress", f"SPY averaged {pct(stress['v'], 1)} over the next 63 sessions vs {pct(UNC63, 1)} on all days ({tstat(stress['t'])}); 1962–2026 S&P edge only {pct(gst['diff_vs_uncond'], 1)} ({tstat(gst['diff_t_nw'])})",
         '<span class="verdict v-weak">Weak, era-dependent</span>'],
        ["Index ladder: exhaustion rungs", "The selling is exhausting; a bottom is forming", f"Confirmed exhaustion never published for SPY in 33 years; candidate published 6 times, none at a major low. Higher exhaustion was followed by lower returns (IC {num(SPY['deciles']['exhaustion']['h63']['ic'])})",
         '<span class="verdict v-bad">No edge</span>'],
        ["Per-stock panic score (0–100), as a return signal", "Fear in this stock", f"Daily rank IC {num(ic21['mean'])} at 21 sessions, {num(ic63['mean'])} at 63; reverses to {pct(sp252['mean'], 1)} at one year; {num(era26['mean'])} since 2020. AUC for beating SPY: {A['panic']['auc_x63_pos']:.3f}",
         '<span class="verdict v-weak">Faint, fading</span>'],
        ["Per-stock panic score, as a risk signal", "Danger / volatility", f"Next-month volatility rises from {pct(vol_lo, 0, False)} to {pct(vol_hi, 0, False)} across the panic range, but the stock's own 20-day volatility predicts it far better (AUC {rv20_auc:.2f} vs {A['panic']['auc_vol21_gt_median']:.2f})",
         '<span class="verdict v-ok">Works, but redundant</span>'],
        ["Stock states: stress building → confirmed exhaustion", "Escalating capitulation, then stabilization", f"Each rung adds risk (fell 15%+ more: {pct(ev['stress_building']['p_mae63_lt_-15'], 0, False)} → {pct(ev['confirmed_exhaustion']['p_mae63_lt_-15'], 0, False)}), but 63-session returns stay within about half a point of baseline at every rung",
         '<span class="verdict v-weak">Risk yes, timing no</span>'],
        ["Setup phase: “falling knife” vs “stabilizing”", "Wait vs. better entry", f"“Falling knife” days beat SPY by {pct(ev['phase_falling_knife']['x_nc_63']['mean'], 2)} over 63 sessions; “stabilizing” by {pct(ev['phase_stabilizing']['x_nc_63']['mean'], 2)}. “Stabilizing” labels {pct(stab_days, 0, False)} of all stock-days",
         '<span class="verdict v-bad">Misleading labels</span>'],
    ]
    scorecard = table_html(["Signal", "What the dashboard implies", "What history shows", "Verdict"], score_rows, cls="data scorecard")

    plan = PLAN_HTML.format(
        n_stocks=len(PT), n_stockdays=f"{n_stockdays / 1e6:.1f} million",
    )

    page = f"""<title>Fear Signal Accuracy Study</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Instrument+Sans:wght@400;500;600;700&family=Source+Serif+4:opsz,wght@8..60,400;8..60,600&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>{CSS}</style>
<main class="page">
<header class="masthead">
  <p class="eyebrow">Single-stock investments · Technical signals research · Data through 30 Sep 2026</p>
  <h1>Do the fear scores predict returns?</h1>
  <p class="dek">A point-in-time replay of the dashboard’s two technical signals across all available history: the index capitulation ladder on the risk page, and the 0–100 fear scores shown for every stock. The headline number in the “Fear / tape” column is the panic score.</p>
  <dl class="facts">
    <div><dt>Stocks</dt><dd>{n_replayed:,} replayed · {S['stocks']} with 3+ usable years</dd></div>
    <div><dt>Stock-days scored</dt><dd>{n_stockdays / 1e6:.1f} million, 1962–2026</dd></div>
    <div><dt>Index history</dt><dd>SPY 1993–2026 · S&amp;P 500 1962–2026 · 22 ETFs</dd></div>
    <div><dt>Replay check</dt><dd>560 random snapshots matched production exactly</dd></div>
  </dl>
</header>

<section class="answer">
  <h2>The short answer</h2>
  <p><strong>The scores measure fear accurately, but fear is a poor timing signal.</strong> When the panic score is high, the next month really is more volatile and deeper drops really are more likely. What the score does not do is tell you when to buy. Higher fear has been followed by slightly better returns on average, but the effect is tiny: the most-feared tenth of stocks beat the least-feared tenth by {pct(sp21['mean'], 1, False)} over the next month, and the score explains roughly {pct(s63['r2_implied_median'], 1, False)} of what happens next. It has also faded to nothing since 2020, and it reverses at one year.</p>
  <p><strong>The “exhaustion” half of both models has no edge.</strong> On the index, higher exhaustion readings were followed by <em>lower</em> returns, and the ladder’s top rung never fired for SPY in 33 years. On single stocks, “stabilizing” is the label on {pct(stab_days, 0, False)} of all days, and “falling knife” days did better afterwards than “stabilizing” days.</p>
  <p><strong>Context matters more than the score.</strong> A stock that panics while the market is calm has kept underperforming. A stock that panics in a market-wide selloff has rebounded with the market. The dashboard does not distinguish the two.</p>
  {scorecard}
</section>

<section id="index">
  <h2>Index capitulation ladder</h2>
  <p>The risk page’s ladder runs the intraday forced-flow model on daily bars for SPY, QQQ, IWM, the sector SPDRs and macro ETFs. It was replayed every session with the production code, including the two-session hysteresis and the drawdown gate. The replay matched all 31 rows the dashboard has published since 10 August.</p>
  {fig_timeline()}
  <p>The ladder spent {pct(SPYC['published_ge_stress']['share'], 1, False)} of sessions at “stress” or above. The upper rungs are the problem. On daily bars, the exhaustion confirmations (an up day, a close in the upper half) flip from one session to the next, so the required two-session dwell almost never holds. SPY’s raw model said “confirmed exhaustion” on 15 days, including 26 Dec 2018 and 13 Oct 2022, each the session after a major low. It also said it on 7 Jul 2008 and 2 Mar 2020, with much further to fall. None of the 15 was ever published.</p>
  {fig_spy_conditions()}
  <p>The one rung that carries information is <strong>stress</strong>: SPY’s next 63 sessions averaged {pct(stress['v'], 1)} against {pct(UNC63, 1)} on all days. Compared only with days at the same drawdown that didn’t fire, it still added {pct(SPY['drawdown_matched']['published_ge_stress']['weighted_diff'], 1)}. It is no better than simple rules, though: a 5% five-day drop or a VIX close above 30 did as well or better. Over the full S&amp;P 500 history from 1962 its edge shrinks to {pct(gst['diff_vs_uncond'], 1)} ({tstat(gst['diff_t_nw'])}). Buying stress worked unusually well after 1993.</p>
  {fig_spy_deciles()}
  <h3>Does it find bottoms?</h3>
  <p>Across the {SPY['episodes']} SPY corrections of 10% or more since 1993, a signal “caught” a bottom if it fired within ten sessions of the low. Precision is the share of all firings that landed that close to a bottom.</p>
  {timing_table()}
  <p class="aside">RSI(14) under 30 caught more bottoms than any rung of the ladder. Every signal fires mostly at times that are not bottoms, which is expected. Lows are rare, so precision near 15% is about what a well-timed fear gauge can achieve.</p>
  <h3>Every index and ETF</h3>
  <p>Exhaustion’s correlation with the next 63 sessions is negative for {n_exh_neg} of the {len(syms)} series. Panic predicts next-month volatility for {"all of them" if n_vol_pos == len(syms) else f"{n_vol_pos} of them"}. The return edge of “stress” varies widely and is not significant for most. These series share the same market episodes, so they are not independent confirmations.</p>
  {index_table()}
  <p class="aside">The holdings page’s separate “market fear” read applies the per-stock model to SPY, and it disagrees with the ladder. It says “stress building” today while the ladder has read “normal” every day since August. Its “stress building” state covers {pct(MAC['conditions']['stress_building']['share'], 0, False)} of all SPY sessions and carries no return information ({pct(MAC['conditions']['stress_building']['h63']['diff_vs_uncond'], 1)} vs all days). Its only “confirmed exhaustion” readings, on 10 and 23 Jan 2008, were followed by {pct(MAC['conditions']['confirmed_exhaustion']['h252']['all_days_mean'], 0)} over the next year.</p>
</section>

<section id="stocks">
  <h2>Per-stock fear scores</h2>
  <p>Every dashboard stock with price history was replayed every session from its first trade, using today’s production model: up to 64 years for the oldest names. Scores are only used once a stock has the full three-year percentile window the model expects. Outcomes are log returns from the next session’s close, minus SPY’s (or the local index’s abroad), so a market-wide rebound doesn’t count as stock-specific skill.</p>
  {fig_stock_buckets()}
  <p>The pattern is a slope in risk, not in return. Moving from calm to extreme readings, the chance of another 15% drop goes from {pct(dd_lo, 0, False)} to {pct(dd_hi, 0, False)} and next-month volatility from {pct(vol_lo, 0, False)} to {pct(vol_hi, 0, False)}. Returns relative to SPY move by about a percentage point across the whole range, and only at the very top.</p>
  {state_table()}
  {fig_events()}
  <p>Split by what the market was doing, the result changes. Stock-specific panics, with the market calm, were followed by flat-to-negative relative returns. That is consistent with the well-documented drift after company-specific bad news. Panics during market-wide selloffs were followed by positive relative returns, and much larger absolute ones, as high-beta names bounced with the market. Part of that is beta rather than skill.</p>
  {fig_cross_section_eras()}
  <p>Ranked against each other on the same day, higher-panic stocks beat lower-panic stocks by {pct(sp21['mean'], 2)} over 21 sessions (top vs bottom decile, {tstat(sp21['t'])}). About half of that is plain short-term reversal: controlling for the last 5 and 20 days’ return, momentum, volatility and drawdown cuts the panic coefficient from {num(C['fmb_alone|panic|x21']['mean'])} to {num(fmb21['mean'])} ({tstat(fmb21['t'])}). Over a full year the ranking reverses: the top decile trailed the bottom by {pct(abs(sp252['mean']), 1, False)}, the momentum effect. The exhaustion score is negative here too (IC {num(exh21['mean'])}), because it mostly records whether the stock just had an up day. All figures are before trading costs, which would absorb most of a 21-session spread this size.</p>
  {fig_per_stock_hist()}
</section>

<section id="each-stock">
  <h2>Each stock</h2>
  <p>Per-stock results for the panic score against the stock’s own 63-session return vs SPY. The p-value compares each stock with a null built by shifting its own signal in time. “Shrunk” pulls each estimate toward the group average in proportion to its noise, and is the better guide to any one stock. Of the {n_judged} stocks with five or more usable years, {n_pos} show a link that survives a 10% false-discovery screen with fear preceding outperformance, and {n_neg} the reverse. That is consistent with one weak shared effect and no stock where the score is a dependable timing tool.</p>
  <div class="tools"><label for="q">Find a ticker</label><input id="q" type="search" placeholder="e.g. FICO" autocomplete="off"><span id="qcount" class="muted"></span></div>
  {per_stock_table_html(ps_rows)}
  <p class="aside">Not shown: {n_young} younger listings without three usable years after the warm-up; SPY itself; DNP.WA, whose Yahoo symbol resolves to the wrong security (see below); and AVB, EA, EQR, LBRDK and TOI, whose histories Yahoo no longer serves.</p>
</section>

<section id="issues">
  <h2>Problems found along the way</h2>
  <ol class="issues">
    <li><strong>“Stabilizing after stress” has no stress gate.</strong> The stock setup calls any day with exhaustion ≥ 40 “stabilizing”, including calm up-days at all-time highs. The index ladder already fixed this with its exhaustion-meaningful gate; the stock model never got it.</li>
    <li><strong>The ladder’s top rungs can’t fire on daily bars.</strong> The two-session dwell was set for minute bars. On daily bars it has suppressed every confirmed-exhaustion reading for SPY since 1993.</li>
    <li><strong>Two market-fear reads disagree.</strong> The risk page ladder says “normal”; the holdings page’s SPY read says “stress building” (pressure 79). They are different models with different thresholds, and nothing on the page says so.</li>
    <li><strong>DNP.WA shows technicals for the wrong company.</strong> The Yahoo symbol resolves to <code>DNP</code>, the DNP Select Income Fund on NYSE, not Dino Polska in Warsaw (<code>DNP.WA</code>).</li>
    <li><strong>Delisted names vanish.</strong> Yahoo returns a single bar for AVB, EA, EQR, LBRDK and TOI. Their dashboard rows are preserved snapshots. The same mechanism quietly removes failures from any history-based study.</li>
    <li><strong>Inherited histories and corrupt adjustments.</strong> Some tickers carry a predecessor company’s history (WULF before 2021 is IKONICS). 28 histories contain one-day moves above 3×, several of them reverse-split artifacts (XTIA’s adjusted price reaches 2×10<sup>13</sup>). This study drops the year either side of such moves.</li>
    <li><strong>The cached SPY benchmark is a bot-check page.</strong> <code>_system/reference/market-data/benchmarks/spy_us.csv</code> contains Stooq’s JavaScript challenge HTML, not prices.</li>
  </ol>
</section>

{plan}

<section id="method">
  <h2>Method and caveats</h2>
  <ul class="method">
    <li><strong>Replay.</strong> Index ladder: production <code>flow_stress.calculate_flow_snapshot</code>, <code>apply_state_hysteresis</code> and <code>build_capitulation_daily</code> gates, run once per session on a 100-bar window. That window was checked identical to the production 2-year call on 120 samples. Stock model: a vectorized replay of <code>build_technical_signals.calculate_snapshot</code>, matched against the production function on 560 random (stock, date) snapshots. Every state, phase and confirmation was identical; the only differences were 0.1–1.0 percentile points in four tie-heavy 1990s penny-stock histories.</li>
    <li><strong>Data.</strong> Yahoo chart v8 daily bars with the production dividend adjustment. Before SPY existed (Jan 1993) the stock benchmark is the S&amp;P 500 price index, so relative-strength inputs match production exactly from mid-1996.</li>
    <li><strong>Outcomes.</strong> Entry at the next session’s close, because the dashboard updates overnight. Next-open and same-close entries were also computed and change nothing material. Stock averages use log returns to keep a few multi-baggers and bad prints from dominating.</li>
    <li><strong>Inference.</strong> Newey-West errors with lags equal to the horizon for overlapping windows; bootstrap by calendar month for events, because a crash month produces hundreds of simultaneous signals that are really one observation; circular-shift nulls and Benjamini-Hochberg for per-stock tests.</li>
    <li><strong>Survivorship.</strong> The universe is today’s dashboard, so companies that failed are missing. That flatters “buy the fear” results. The positive stock-level effects here are upper bounds, and the index results, which have no survivorship problem, are the cleaner test.</li>
    <li><strong>Selection.</strong> Many names were added to the dashboard after a large move. Pre-2000 data for small and foreign listings is thinner and noisier. Excess returns are measured against SPY, not beta-adjusted.</li>
  </ul>
</section>
<footer class="foot">Replay and analysis code (<code>fear_vec.py</code>, <code>index_replay.py</code>, <code>stock_stage1–4.py</code>, <code>report.py</code>) is kept with the study files and can be committed to the repository’s research folder. No ThetaData or IB Gateway access was used; all prices came from the public Yahoo endpoint the dashboard already uses.</footer>
</main>
<div id="tip" role="tooltip" hidden></div>
<script>{JS}</script>
"""
    return page


PLAN_HTML = """<section id="plan">
  <h2>The study plan</h2>
  <p>Phases 1 to 4 were run for this report. Phases 5 to 7 are what it would take to make the conclusions decision-grade and keep them current.</p>
  <ol class="phases">
    <li><h3>Pre-register the questions</h3>
      <p>Write down what each label claims before looking at outcomes. Fix three primary endpoints:</p>
      <ul>
        <li>SPY’s 63-session return after the ladder reaches “stress”, against all days and against days at the same drawdown.</li>
        <li>The daily cross-sectional rank correlation of panic with 21- and 63-session excess returns.</li>
        <li>Each stock’s panic-to-63-session correlation against its own time-shifted null.</li>
      </ul>
      <p>Everything else is exploratory and gets a false-discovery correction.</p>
      <p class="status done">Done for this pass</p></li>
    <li><h3>Assemble the longest clean history</h3>
      <p>Full daily OHLCV for every dashboard stock and the 23 ladder ETFs, from the same source and adjustment as production. Screen for:</p>
      <ul>
        <li>Wrong-security mappings.</li>
        <li>Delisted symbols.</li>
        <li>Inherited histories.</li>
        <li>Impossible one-day moves.</li>
      </ul>
      <p class="status done">Done · {n_stocks} stocks with 3+ usable years, {n_stockdays} stock-days</p></li>
    <li><h3>Replay the signals point-in-time</h3>
      <p>Recompute every score as the nightly job would have published it that evening, using only data up to that close. Prove the replay against the production code, not against itself.</p>
      <p class="status done">Done · exact match on 560 random snapshots</p></li>
    <li><h3>Score accuracy and precision</h3>
      <p>Accuracy asks whether the signal points the right way: rank correlation, hit rate against the base rate, AUC, and decile slopes. Precision has three senses:</p>
      <ul>
        <li>How often a firing is followed by the outcome it implies.</li>
        <li>How tight those outcomes are.</li>
        <li>How close to the actual low it fires.</li>
      </ul>
      <p>Run each test across horizons of 1 to 252 sessions, both as risk (further drawdown, volatility) and as return. Compare against simple rules and standard factors.</p>
      <p class="status done">Done · this report</p></li>
    <li><h3>Remove survivorship and beta</h3>
      <p>Replicate the stock results on a point-in-time universe that includes delisted companies. That requires a vendor with dead-company history (CRSP, Norgate or Sharadar); Yahoo drops them. Measure excess returns against a beta-matched benchmark, and net out realistic trading costs.</p>
      <p class="status todo">Next · needs a licensed data source</p></li>
    <li><h3>Track every published signal forward</h3>
      <p>Log each nightly score and ladder state as it is published, and grade it when its 21-, 63- and 252-session outcomes mature. This is the only true out-of-sample test. It also catches drift between the live job and this replay, such as missed runs, data revisions or code changes. Show the running record on the dashboard beside the signal.</p>
      <p class="status todo">Next · small nightly job, no new data needed</p></li>
    <li><h3>Recalibrate, with a holdout</h3>
      <p>Only after phases 5–6:</p>
      <ul>
        <li>Gate “stabilizing” on real stress.</li>
        <li>Shorten or drop the daily-bar dwell for the exhaustion rungs.</li>
        <li>Show market context next to each stock’s panic.</li>
        <li>Re-test any change walk-forward on a held-out period before it reaches the page.</li>
      </ul>
      <p class="status todo">Later · decision rules below</p></li>
  </ol>
  <h3>Decision rules</h3>
  <ul class="rules">
    <li>If a label’s historical outcomes don’t differ from the baseline at the pre-registered horizon, relabel it as description (“high volatility”, “sharp decline”) rather than advice (“falling knife”, “stabilizing”).</li>
    <li>Keep panic and pressure as risk gauges: they reliably precede higher volatility. Show the stock’s own realized volatility next to them, since it predicts risk better.</li>
    <li>Treat the index “stress” rung as a regime flag, not a buy signal, until the 1962–1992 weakness is explained.</li>
    <li>Retire or rebuild the exhaustion rungs. Ten years of forward tracking with no edge is enough to remove them from the page.</li>
  </ul>
</section>"""

CSS = r"""
/* Layout: one reading column (~68ch); figures and tables break out to the wide measure */
:root {
  --bg: #f5f6f8; --surface: #ffffff; --ink: #14171c; --ink-2: #49505b; --muted: #747b87; --rule: #dde1e8;
  --accent: #2a78d6; --c1: #2a78d6; --c2: #eb6834; --c3: #1baf7a; --neg: #e34948; --gray: #a7acb5; --band: rgba(42,120,214,.10);
  --grid: #e7e9ee; --axis: #c3c7cf;
  --good: #0ca30c; --warn: #fab219; --serious: #ec835a; --crit: #d03b3b;
  --chip-ok: rgba(12,163,12,.12); --chip-weak: rgba(250,178,25,.18); --chip-bad: rgba(208,59,59,.12); --chip-na: rgba(116,123,135,.12);
  --display: "Instrument Sans", system-ui, -apple-system, "Segoe UI", sans-serif;
  --body: "Source Serif 4", Georgia, "Times New Roman", serif;
  --data: "IBM Plex Mono", ui-monospace, Consolas, monospace;
  --measure: 70ch; --wide: 1000px;
}
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {
  --bg: #0f1114; --surface: #171a1f; --ink: #edf0f4; --ink-2: #b8bfca; --muted: #8b929e; --rule: #2a2f37;
  --accent: #3987e5; --c1: #3987e5; --c2: #d95926; --c3: #199e70; --neg: #e66767; --gray: #6c727c; --band: rgba(57,135,229,.16);
  --grid: #23272e; --axis: #3a4049;
  --chip-ok: rgba(12,163,12,.20); --chip-weak: rgba(250,178,25,.18); --chip-bad: rgba(230,103,103,.18); --chip-na: rgba(139,146,158,.16);
  color-scheme: dark; } }
:root[data-theme="dark"] {
  --bg: #0f1114; --surface: #171a1f; --ink: #edf0f4; --ink-2: #b8bfca; --muted: #8b929e; --rule: #2a2f37;
  --accent: #3987e5; --c1: #3987e5; --c2: #d95926; --c3: #199e70; --neg: #e66767; --gray: #6c727c; --band: rgba(57,135,229,.16);
  --grid: #23272e; --axis: #3a4049;
  --chip-ok: rgba(12,163,12,.20); --chip-weak: rgba(250,178,25,.18); --chip-bad: rgba(230,103,103,.18); --chip-na: rgba(139,146,158,.16);
  color-scheme: dark; }
html { -webkit-text-size-adjust: 100%; }
body { background: var(--bg); color: var(--ink); font-family: var(--body); font-size: 17px; line-height: 1.6; }
.page { max-width: var(--wide); margin: 0 auto; padding-inline: 20px; padding-block: 40px 64px; }
.page > header, .page > section, .page > footer { display: grid; gap: 14px; }
section { margin-top: 56px; }
section > p, section > h2, section > h3, section > ul, section > ol, .masthead > p, .masthead > h1, .tools { max-width: var(--measure); }
h1, h2, h3 { font-family: var(--display); text-wrap: balance; margin: 0; color: var(--ink); }
h1 { font-size: clamp(30px, 5vw, 46px); line-height: 1.08; font-weight: 700; letter-spacing: -0.015em; }
h2 { font-size: 26px; line-height: 1.2; font-weight: 650; padding-top: 18px; border-top: 1px solid var(--rule); }
h3 { font-size: 18px; font-weight: 600; margin-top: 10px; }
p { margin: 0; }
.eyebrow { font-family: var(--display); font-size: 12.5px; letter-spacing: .06em; text-transform: uppercase; color: var(--muted); }
.dek { font-size: 19.5px; color: var(--ink-2); line-height: 1.5; }
.facts { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px 24px; margin: 8px 0 0; padding: 16px 0 0; border-top: 1px solid var(--rule); }
.facts div { min-width: 0; }
.facts dt { font-family: var(--display); font-size: 12px; letter-spacing: .05em; text-transform: uppercase; color: var(--muted); }
.facts dd { margin: 2px 0 0; font-family: var(--display); font-size: 15px; font-weight: 500; }
.answer p strong { font-family: var(--display); font-weight: 600; }
.aside { font-size: 15px; color: var(--ink-2); }
code { font-family: var(--data); font-size: .84em; background: var(--chip-na); padding: 1px 5px; border-radius: 4px; overflow-wrap: anywhere; }
.muted { color: var(--muted); }
/* tables */
.tablewrap { overflow-x: auto; max-width: 100%; border: 1px solid var(--rule); border-radius: 8px; background: var(--surface); }
.tablewrap.tall { max-height: 560px; overflow-y: auto; }
table.data { border-collapse: collapse; width: 100%; font-family: var(--display); font-size: 13.5px; font-variant-numeric: tabular-nums; }
table.data th, table.data td { padding: 8px 12px; text-align: left; border-bottom: 1px solid var(--grid); vertical-align: top; }
table.data thead th { position: sticky; top: 0; background: var(--surface); color: var(--muted); font-weight: 600; font-size: 12px; letter-spacing: .03em; text-transform: uppercase; z-index: 1; }
table.data tbody tr:last-child td, table.data tbody tr:last-child th { border-bottom: 0; }
table.data tbody th { font-weight: 600; }
table.scorecard td:first-child { font-weight: 600; min-width: 190px; }
table.scorecard td:nth-child(3) { min-width: 300px; }
.sortable thead button { all: unset; cursor: pointer; display: inline-flex; gap: 4px; align-items: center; }
.sortable thead button:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; border-radius: 3px; }
.sortable thead button[aria-sort="ascending"]::after { content: "↑"; }
.sortable thead button[aria-sort="descending"]::after { content: "↓"; }
.verdict { display: inline-block; padding: 2px 9px; border-radius: 999px; font-family: var(--display); font-size: 12.5px; font-weight: 600; white-space: nowrap; }
.verdict::before { margin-right: 5px; }
.v-ok { background: var(--chip-ok); } .v-ok::before { content: "●"; color: var(--good); }
.v-weak { background: var(--chip-weak); } .v-weak::before { content: "◐"; color: var(--warn); }
.v-bad { background: var(--chip-bad); } .v-bad::before { content: "✕"; color: var(--crit); }
.v-pos { background: var(--chip-ok); } .v-pos::before { content: "▲"; color: var(--good); }
.v-neg { background: var(--chip-bad); } .v-neg::before { content: "▼"; color: var(--crit); }
.v-none, .v-na { background: var(--chip-na); } .v-none::before { content: "○"; color: var(--muted); } .v-na::before { content: "–"; color: var(--muted); }
/* figures */
.fig { margin: 8px 0 0; padding: 18px 18px 14px; background: var(--surface); border: 1px solid var(--rule); border-radius: 10px; display: grid; gap: 10px; min-width: 0; }
.fig figcaption { display: grid; gap: 3px; font-family: var(--display); }
.fig figcaption strong { font-size: 16px; font-weight: 600; }
.fig figcaption span { font-size: 13.5px; color: var(--ink-2); line-height: 1.45; }
.plot { min-width: 0; }
svg.chart { width: 100%; height: auto; display: block; font-family: var(--display); overflow: visible; }
.minis { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 14px 22px; }
.minis.two { grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); }
.mini { min-width: 0; display: grid; gap: 4px; }
.minititle { font-family: var(--display); font-size: 13.5px; font-weight: 600; display: flex; justify-content: space-between; gap: 8px; flex-wrap: wrap; }
.minititle small { font-weight: 500; color: var(--muted); font-size: 12px; }
.chart .grid { stroke: var(--grid); stroke-width: 1; }
.chart .axis { stroke: var(--axis); stroke-width: 1; }
.chart .tick { fill: var(--muted); font-size: 11px; font-variant-numeric: tabular-nums; }
.chart .axlabel { fill: var(--muted); font-size: 11px; }
.chart .rowlabel { fill: var(--ink-2); font-size: 12.5px; }
.chart .val { fill: var(--ink); font-size: 12px; font-weight: 600; font-variant-numeric: tabular-nums; }
.chart .ref { stroke: var(--ink-2); stroke-width: 1.25; }
.chart .reflabel { fill: var(--ink-2); font-size: 11px; font-weight: 600; }
.chart .whisker { stroke: var(--ink-2); stroke-width: 1.25; }
.chart .m1 { fill: var(--c1); } .chart .m2 { fill: var(--c2); } .chart .m3 { fill: var(--c3); }
.chart .mneg { fill: var(--neg); } .chart .mgray { fill: var(--gray); }
.chart .hitbox { fill: transparent; }
.chart .hit { outline: none; }
.chart .hit:hover path, .chart .hit:focus-visible path { opacity: .78; }
.chart .hit:focus-visible .hitbox { stroke: var(--accent); stroke-width: 1.5; }
.chart .line1 { fill: none; stroke: var(--c1); stroke-width: 1.6; stroke-linejoin: round; stroke-linecap: round; }
.chart .line-ref { fill: none; stroke: var(--gray); stroke-width: 2; stroke-linejoin: round; }
.chart .band { fill: var(--band); }
.chart .dot2 { fill: var(--c2); stroke: var(--surface); stroke-width: 2; }
.chart .dot3 { fill: var(--c3); stroke: var(--surface); stroke-width: 2; }
.chart .xhair { stroke: var(--ink-2); stroke-width: 1; }
.chart .tl-catch { fill: transparent; }
.legend { display: flex; flex-wrap: wrap; gap: 6px 16px; font-family: var(--display); font-size: 12.5px; color: var(--ink-2); }
.legend .key { display: inline-flex; align-items: center; gap: 6px; }
.legend rect.m1 { fill: var(--c1); } .legend rect.m2 { fill: var(--c2); } .legend rect.m3 { fill: var(--c3); }
.legend rect.mgray { fill: var(--gray); } .legend rect.mband { fill: var(--band); stroke: var(--c1); stroke-width: .5; }
.tableview summary { cursor: pointer; font-family: var(--display); font-size: 13px; color: var(--accent); font-weight: 600; width: fit-content; }
.tableview summary:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; border-radius: 3px; }
.tableview[open] summary { margin-bottom: 8px; }
.fignote { font-size: 13px; color: var(--muted); font-family: var(--display); }
#tip { position: fixed; z-index: 10; pointer-events: none; max-width: 300px; padding: 8px 10px; border-radius: 8px; background: var(--ink); color: var(--bg); font-family: var(--display); font-size: 12.5px; line-height: 1.4; box-shadow: 0 4px 18px rgba(0,0,0,.18); }
/* lists */
ol.issues, ul.method, ul.rules { display: grid; gap: 10px; padding-left: 22px; margin: 0; }
ol.phases { list-style: none; counter-reset: ph; padding: 0; margin: 0; display: grid; gap: 14px; max-width: var(--measure); }
ol.phases > li { counter-increment: ph; position: relative; padding: 14px 16px 14px 54px; background: var(--surface); border: 1px solid var(--rule); border-radius: 10px; display: grid; gap: 6px; }
ol.phases > li::before { content: counter(ph); position: absolute; left: 16px; top: 13px; width: 26px; height: 26px; border-radius: 50%; display: grid; place-items: center; font-family: var(--display); font-weight: 700; font-size: 13px; background: var(--chip-na); color: var(--ink); }
ol.phases h3 { margin: 0; font-size: 16.5px; }
ol.phases p { font-size: 15.5px; }
ol.phases ul { display: grid; gap: 4px; padding-left: 20px; margin: 0; font-size: 15.5px; }
.status { font-family: var(--display); font-size: 12.5px; font-weight: 600; }
.status.done { color: var(--good); } .status.todo { color: var(--muted); }
.status.done::before { content: "✓ "; } .status.todo::before { content: "○ "; }
.tools { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; font-family: var(--display); font-size: 14px; }
.tools input { font: inherit; padding: 7px 10px; border: 1px solid var(--rule); border-radius: 8px; background: var(--surface); color: var(--ink); min-width: 0; width: 200px; }
.tools input:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }
.foot { margin-top: 48px; padding-top: 16px; border-top: 1px solid var(--rule); font-family: var(--display); font-size: 13px; color: var(--muted); }
@media (max-width: 560px) { body { font-size: 16px; } .page { padding-inline: 16px; } .fig { padding: 14px 12px 12px; } h2 { font-size: 22px; } }
@media (prefers-reduced-motion: reduce) { * { transition: none !important; } }
"""

JS = r"""
(function () {
  var tip = document.getElementById('tip');
  function show(text, x, y) {
    tip.textContent = text; tip.hidden = false;
    var w = tip.offsetWidth, h = tip.offsetHeight;
    var left = Math.min(window.innerWidth - w - 8, x + 14), top = y - h - 12;
    if (top < 8) top = y + 16;
    tip.style.left = Math.max(8, left) + 'px'; tip.style.top = top + 'px';
  }
  function hide() { tip.hidden = true; }
  document.querySelectorAll('[data-tip]').forEach(function (el) {
    el.addEventListener('pointermove', function (e) { show(el.getAttribute('data-tip'), e.clientX, e.clientY); });
    el.addEventListener('pointerleave', hide);
    el.addEventListener('focus', function () { var r = el.getBoundingClientRect(); show(el.getAttribute('data-tip'), r.left + r.width / 2, r.top); });
    el.addEventListener('blur', hide);
  });
  // timeline crosshair
  var tl = window.__TL, wrap = document.getElementById('timeline');
  if (tl && wrap) {
    var svg = wrap.querySelector('svg'), xh = svg.querySelector('#tl-x'), catchEl = svg.querySelector('.tl-catch');
    var names = ['normal', 'observe', 'stress', 'exhaustion candidate', 'confirmed exhaustion'];
    catchEl.addEventListener('pointermove', function (e) {
      var pt = svg.createSVGPoint(); pt.x = e.clientX; pt.y = e.clientY;
      var p = pt.matrixTransform(svg.getScreenCTM().inverse());
      var lo = 0, hi = tl.x.length - 1;
      while (hi - lo > 1) { var mid = (lo + hi) >> 1; if (tl.x[mid] < p.x) lo = mid; else hi = mid; }
      var i = Math.abs(tl.x[lo] - p.x) < Math.abs(tl.x[hi] - p.x) ? lo : hi;
      xh.setAttribute('x1', tl.x[i]); xh.setAttribute('x2', tl.x[i]); xh.setAttribute('visibility', 'visible');
      show('$' + tl.c[i].toFixed(2) + '  ·  week of ' + tl.d[i] + '  ·  ladder: ' + names[tl.s[i]], e.clientX, e.clientY);
    });
    catchEl.addEventListener('pointerleave', function () { xh.setAttribute('visibility', 'hidden'); hide(); });
  }
  // per-stock table: sort + filter
  var table = document.getElementById('stocks');
  if (table) {
    var tbody = table.tBodies[0], rows = Array.prototype.slice.call(tbody.rows), q = document.getElementById('q'), qc = document.getElementById('qcount');
    function count() { var n = rows.filter(function (r) { return !r.hidden; }).length; qc.textContent = n + ' of ' + rows.length + ' stocks'; }
    q.addEventListener('input', function () {
      var v = q.value.trim().toUpperCase();
      rows.forEach(function (r) { r.hidden = v && r.cells[0].textContent.toUpperCase().indexOf(v) === -1; });
      count();
    });
    table.querySelectorAll('thead button').forEach(function (b) {
      b.addEventListener('click', function () {
        var col = +b.dataset.col, kind = b.dataset.kind, dir = b.getAttribute('aria-sort') === 'ascending' ? -1 : 1;
        table.querySelectorAll('thead button').forEach(function (o) { o.removeAttribute('aria-sort'); });
        b.setAttribute('aria-sort', dir === 1 ? 'ascending' : 'descending');
        rows.sort(function (a, c) {
          var x = a.cells[col].dataset.v, y = c.cells[col].dataset.v;
          if (kind === 'n') { x = x === '' ? Infinity * dir : +x; y = y === '' ? Infinity * dir : +y; return (x - y) * dir; }
          return x.localeCompare(y) * dir;
        });
        rows.forEach(function (r) { tbody.appendChild(r); });
      });
    });
    count();
  }
})();
"""

if __name__ == "__main__":
    out = RES / "report.html"
    out.write_text(build(), encoding="utf-8")
    print("wrote", out, f"{out.stat().st_size / 1024:.0f} KB")
