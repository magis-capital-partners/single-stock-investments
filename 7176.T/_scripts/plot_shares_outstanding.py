#!/usr/bin/env python3
"""Plot split-adjusted issued shares outstanding for 7176.T (issuer filings)."""
from __future__ import annotations

import json
import math
from datetime import date
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.dates as mdates

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "research"

# Issued shares outstanding (as filed) from 発行者情報 progression tables
# Sources: mid/issuer information PDFs in 01_Official/Issuer_Information/
RAW = [
    ("2015-10-01", 1_470_000, "10:1 split effective (147k pre-split)"),
    ("2017-10-01", 2_148_000, "10:1 split effective"),
    ("2019-10-01", 2_100_000, "10:1 split effective"),
    ("2021-08-24", 850_000, "Treasury cancellation"),
    ("2022-08-30", 520_000, "Treasury cancellation"),
    ("2023-04-01", 5_200_000, "10:1 split effective"),
    ("2023-08-22", 3_130_000, "Treasury cancellation"),
    ("2024-09-10", 2_188_000, "Treasury cancellation"),
    ("2025-08-29", 1_356_000, "Treasury cancellation"),
    ("2025-11-01", 27_120_000, "20:1 split effective"),
]

# Forward split factors to express each observation in Nov-2025 share units
SPLITS = [
    (date(2015, 10, 1), 10),
    (date(2017, 10, 1), 10),
    (date(2019, 10, 1), 10),
    (date(2023, 4, 1), 10),
    (date(2025, 11, 1), 20),
]


def forward_mult(observation: date) -> int:
    m = 1
    for eff, ratio in SPLITS:
        if observation < eff:
            m *= ratio
    return m


def parse_ymd(s: str) -> date:
    y, m, d = map(int, s.split("-"))
    return date(y, m, d)


def cagr(start: float, end: float, years: float) -> float:
    if start <= 0 or end <= 0 or years <= 0:
        return float("nan")
    return (end / start) ** (1 / years) - 1


def main() -> None:
    dates = []
    reported = []
    adjusted = []
    notes = []
    for ds, sh, note in RAW:
        d = parse_ymd(ds)
        mult = forward_mult(d)
        dates.append(d)
        reported.append(sh)
        adjusted.append(sh * mult)
        notes.append(note)

    # CAGR windows (split-adjusted basis, Nov-2025 units)
    end_d = parse_ymd("2025-11-01")
    end_sh = adjusted[-1]
    windows = [
        ("2015-10-01", "2015 listing era"),
        ("2022-08-30", "pre-2023 split"),
        ("2023-04-01", "post-2023 split"),
        ("2023-08-22", "post Aug-2023 cancel"),
        ("2024-09-10", "post Sep-2024 cancel"),
    ]
    cagr_rows = []
    for start_s, label in windows:
        start_d = parse_ymd(start_s)
        idx = next(i for i, dd in enumerate(dates) if dd == start_d)
        start_sh = adjusted[idx]
        yrs = (end_d - start_d).days / 365.25
        rate = cagr(start_sh, end_sh, yrs)
        cagr_rows.append(
            {
                "label": label,
                "start_date": start_s,
                "end_date": "2025-11-01",
                "start_shares_adj": start_sh,
                "end_shares_adj": end_sh,
                "years": round(yrs, 2),
                "cagr_reduction_pct": round(rate * 100, 2),
            }
        )

    # Full series (log scale — early points include stacked split factors pre-buybacks)
    fig, axes = plt.subplots(2, 1, figsize=(10, 8), gridspec_kw={"height_ratios": [1, 1.2]})

    ax0 = axes[0]
    ax0.semilogy(dates, adjusted, "o-", color="#7f8c8d", linewidth=1.5, markersize=6)
    ax0.set_ylabel("Shares outstanding (log scale)", fontsize=10)
    ax0.set_title("7176.T — Full history (split-adjusted to Nov-2025 units)", fontsize=11)
    ax0.grid(True, which="both", alpha=0.3)
    ax0.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))

    # Focus: 2021+ (buyback era; comparable economics)
    focus_idx = [i for i, d in enumerate(dates) if d >= date(2021, 1, 1)]
    fd = [dates[i] for i in focus_idx]
    fa = [adjusted[i] for i in focus_idx]
    ax1 = axes[1]
    ax1.plot(fd, [x / 1e6 for x in fa], "o-", color="#1a5276", linewidth=2, markersize=7)
    ax1.set_ylabel("Issued shares outstanding (millions)", fontsize=11)
    ax1.set_xlabel("Date", fontsize=11)
    ax1.set_title(
        "Focus: treasury cancellations era (split-adjusted, Nov-2025 units)",
        fontsize=11,
    )
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax1.xaxis.set_major_locator(mdates.YearLocator(1))
    ax1.grid(True, alpha=0.3)
    cagr_22 = cagr_rows[1]["cagr_reduction_pct"]
    ax1.annotate(
        f"27.12M shares (Nov 2025)\n"
        f"CAGR share reduction\n2022-08 → 2025-11: {cagr_22:.1f}%/yr",
        xy=(fd[-1], fa[-1] / 1e6),
        xytext=(-140, 25),
        textcoords="offset points",
        fontsize=9,
        arrowprops=dict(arrowstyle="->", color="gray"),
    )
    fig.autofmt_xdate()
    fig.tight_layout()
    png = OUT_DIR / "shares_outstanding_split_adjusted.png"
    fig.savefig(png, dpi=150)
    plt.close(fig)

    summary = {
        "ticker": "7176.T",
        "basis": "All points converted to Nov-2025 split share units (forward split factors only).",
        "splits_applied": [
            {"effective": str(e), "ratio": f"1:{r}"} for e, r in SPLITS
        ],
        "series": [
            {
                "date": str(d),
                "reported_shares": r,
                "split_adjusted_shares": a,
                "note": n,
            }
            for d, r, a, n in zip(dates, reported, adjusted, notes)
        ],
        "cagr_reduction_split_adjusted": cagr_rows,
        "interpretation": (
            "Negative CAGR = average annual rate of decline in issued share count "
            "(treasury cancellations dominate; splits increase reported count before adjustment)."
        ),
    }
    json_path = OUT_DIR / "shares_outstanding_split_adjusted.json"
    json_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"Wrote {png}")
    print(f"Wrote {json_path}")
    for row in cagr_rows:
        print(
            f"  {row['start_date']} -> {row['end_date']} ({row['years']}y): "
            f"{row['cagr_reduction_pct']:.2f}%/yr"
        )


if __name__ == "__main__":
    main()
