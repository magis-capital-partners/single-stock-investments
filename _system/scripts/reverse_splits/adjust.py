"""Nominal vs split-adjusted prices.

Yahoo's daily Close is sometimes already continuous across a reverse split and
sometimes still raw. A short's borrow, price floor, and share count live in
nominal (printed) dollars. Returns in this repo are computed from those
nominal prices, with the share count multiplied by the ratio only if a hold
is allowed to cross the ex-date.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PriceFrame:
    dates: list[str]
    open: list[float]
    high: list[float]
    low: list[float]
    close: list[float]
    volume: list[float]

    def __len__(self) -> int:
        return len(self.dates)


@dataclass(frozen=True)
class SplitPrint:
    ex_date: str
    ratio: float
    status: str  # raw | continuous | ambiguous | missing
    post_index: int | None
    observed: float | None


@dataclass
class NominalSeries:
    frame: PriceFrame
    splits: list[SplitPrint] = field(default_factory=list)
    ambiguous: set[int] = field(default_factory=set)


def classify_split(
    dates: list[str],
    closes: list[float],
    ex_date: str,
    ratio: float | None,
    window: int = 3,
) -> SplitPrint:
    """Classify the print in a +/- `window` session band around the ex-date.

    `ratio` is new/old (0.1 for a 1-for-10). A raw series jumps by about
    1/ratio. A continuous series does not.
    """
    if ratio is None or ratio <= 0 or ratio >= 1:
        return SplitPrint(ex_date, float(ratio or 0), "missing", None, None)
    ex_i = next((i for i, d in enumerate(dates) if d >= ex_date[:10]), None)
    if ex_i is None:
        return SplitPrint(ex_date, ratio, "missing", None, None)

    expected = 1.0 / ratio
    lo = max(1.8, expected * 0.55)
    hi = max(lo + 0.5, expected * 1.80)
    continuous_ceiling = max(1.35, expected * 0.35)

    start = max(1, ex_i - window)
    end = min(len(closes) - 1, ex_i + window)
    best: tuple[float, int] | None = None
    for i in range(start, end + 1):
        prev, cur = closes[i - 1], closes[i]
        if prev <= 0 or cur <= 0:
            continue
        obs = cur / prev
        if best is None or obs > best[0]:
            best = (obs, i)
    if best is None:
        return SplitPrint(ex_date, ratio, "missing", ex_i, None)
    obs, idx = best
    if lo <= obs <= hi:
        return SplitPrint(ex_date, ratio, "raw", idx, obs)
    if obs <= continuous_ceiling:
        return SplitPrint(ex_date, ratio, "continuous", ex_i, obs)
    return SplitPrint(ex_date, ratio, "ambiguous", ex_i, obs)


def to_nominal(
    frame: PriceFrame,
    splits: list[tuple[str, float]],
    window: int = 3,
) -> NominalSeries:
    """Return OHLC and volume in printed-share terms.

    Continuous vendor history has pre-split prices scaled into post-split
    dollars (and volume scaled down). Undo that. Raw history is already nominal.
    Ambiguous prints are left unscaled and their nearby bars are flagged.
    """
    classified = [
        classify_split(frame.dates, frame.close, ex, ratio, window) for ex, ratio in splits
    ]
    n = len(frame)
    price_scale = [1.0] * n
    vol_scale = [1.0] * n
    ambiguous: set[int] = set()
    for sp in classified:
        if sp.status == "ambiguous":
            center = sp.post_index if sp.post_index is not None else 0
            for i in range(max(0, center - window), min(n, center + window + 1)):
                ambiguous.add(i)
            continue
        if sp.status != "continuous" or sp.post_index is None or sp.ratio <= 0:
            continue
        for i in range(sp.post_index):
            price_scale[i] *= sp.ratio
            vol_scale[i] /= sp.ratio

    def scaled(values: list[float], scales: list[float]) -> list[float]:
        out: list[float] = []
        for value, scale in zip(values, scales):
            out.append(float(value) * scale if value is not None else value)
        return out

    nominal = PriceFrame(
        dates=list(frame.dates),
        open=scaled(frame.open, price_scale),
        high=scaled(frame.high, price_scale),
        low=scaled(frame.low, price_scale),
        close=scaled(frame.close, price_scale),
        volume=scaled(frame.volume, vol_scale),
    )
    return NominalSeries(frame=nominal, splits=classified, ambiguous=ambiguous)


def path_blocked(entry_i: int, exit_i: int, series: NominalSeries) -> bool:
    """True when the hold touches an ambiguous print or crosses one."""
    if entry_i in series.ambiguous or exit_i in series.ambiguous:
        return True
    dates = series.frame.dates
    for sp in series.splits:
        if sp.status != "ambiguous":
            continue
        if dates[entry_i] < sp.ex_date <= dates[exit_i]:
            return True
    return False
