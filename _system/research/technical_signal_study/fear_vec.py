"""Vectorized, point-in-time replay of the per-stock technical fear model.

Replicates ``build_technical_signals.calculate_snapshot`` (technical-fear-v2 /
capitulation-v1) for EVERY date of a full price history, using only data on or
before each date. The production function is the oracle: ``parity_test.py``
compares this module against it on random (ticker, date) samples.

Every window below mirrors a specific production line; comments name it.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view

TRADING_DAYS = 252
PCT_WINDOW = 756  # production: series[-756:]
MIN_CLEAN = 40

STATE_CODES = {
    "normal": 0,
    "stress_building": 1,
    "panic": 2,
    "capitulation_candidate": 3,
    "exhaustion_emerging": 4,
    "confirmed_exhaustion": 5,
}
STATE_NAMES = {v: k for k, v in STATE_CODES.items()}
PHASE_CODES = {"indeterminate": 0, "trend_intact": 1, "oversold_watch": 2, "stabilizing": 3, "falling_knife": 4}
DIRECTION_CODES = {"mixed_repair": 0, "leading_uptrend": 1, "pullback_in_uptrend": 2, "lagging_downtrend": 3}


# --------------------------------------------------------------------------- bars

def production_rows(raw: pd.DataFrame) -> pd.DataFrame:
    """Replay ``fetch_yahoo_history`` row construction on raw vendor arrays.

    close = adjclose or raw close; OHLC scaled by adjclose/close; rows with a
    missing/non-positive close dropped; duplicate dates -> last wins (dict).
    """
    raw_close = raw["close"].to_numpy(dtype=float)
    adj = raw["adjclose"].to_numpy(dtype=float)
    # `_finite(adjusted) or raw_close`: NaN/0 adjclose falls back to raw close
    close = np.where(np.isfinite(adj) & (adj != 0), adj, raw_close)
    keep = np.isfinite(close) & (close > 0)
    ratio = np.where(np.isfinite(raw_close) & (raw_close > 0), close / np.where(raw_close > 0, raw_close, 1.0), 1.0)
    out = pd.DataFrame({
        "date": raw["date"].to_numpy(),
        "open": raw["open"].to_numpy(dtype=float) * ratio,
        "high": raw["high"].to_numpy(dtype=float) * ratio,
        "low": raw["low"].to_numpy(dtype=float) * ratio,
        "close": close,
        "volume": raw["volume"].to_numpy(dtype=float),
    })[keep]
    out = out.drop_duplicates("date", keep="last").sort_values("date").reset_index(drop=True)
    return out


# ------------------------------------------------------------------ window stats

def _windows(x: np.ndarray, width: int = PCT_WINDOW) -> np.ndarray:
    padded = np.concatenate([np.full(width - 1, np.nan), x])
    return sliding_window_view(padded, width)  # row t = x[t-width+1 .. t]


def rolling_percentile(x: np.ndarray) -> np.ndarray:
    """``_percentile_latest``: share of the prior (<=755) finite values <= current."""
    win = _windows(x)
    hist = win[:, :-1]
    cur = win[:, -1]
    n_hist = np.count_nonzero(~np.isnan(hist), axis=1)
    le = np.count_nonzero(hist <= cur[:, None], axis=1)
    ok = np.isfinite(cur) & (n_hist + 1 >= MIN_CLEAN) & (n_hist > 0)
    out = np.full(len(x), np.nan)
    out[ok] = le[ok] / n_hist[ok]
    return out


def rolling_z(x: np.ndarray, clip: float = 4.0) -> np.ndarray:
    """``_zscore``: (current - mean(prior)) / stdev(prior), clipped to +/-4."""
    win = _windows(x)
    hist = win[:, :-1]
    cur = win[:, -1]
    n_hist = np.count_nonzero(~np.isnan(hist), axis=1)
    ok = np.isfinite(cur) & (n_hist + 1 >= MIN_CLEAN)
    out = np.full(len(x), np.nan)
    if not ok.any():
        return out
    rows = np.flatnonzero(ok)
    for start in range(0, len(rows), 2048):  # chunked: bounded memory on long histories
        sel = rows[start:start + 2048]
        h = hist[sel]
        mean = np.nanmean(h, axis=1)
        sd = np.nanstd(h, axis=1, ddof=1)
        z = np.where(sd <= 1e-12, 0.0, (cur[sel] - mean) / np.where(sd <= 1e-12, 1.0, sd))
        out[sel] = np.clip(z, -clip, clip)
    return out


def fear_pct(x: np.ndarray, lower_is_fear: bool = False) -> np.ndarray:
    p = rolling_percentile(x)
    return 100.0 * (1.0 - p) if lower_is_fear else 100.0 * p


def weighted_score(parts: list[tuple[np.ndarray, float]]) -> np.ndarray:
    """``_weighted_score``: clip each part to [0,100], drop missing, renormalize."""
    num = np.zeros(len(parts[0][0]))
    den = np.zeros(len(parts[0][0]))
    for values, weight in parts:
        ok = np.isfinite(values)
        num += np.where(ok, np.clip(np.where(ok, values, 0.0), 0.0, 100.0) * weight, 0.0)
        den += np.where(ok, weight, 0.0)
    out = np.full(len(num), np.nan)
    good = den > 0
    out[good] = num[good] / den[good]
    return out


def weighted_z(parts: list[tuple[np.ndarray, float]]) -> np.ndarray:
    num = np.zeros(len(parts[0][0]))
    den = np.zeros(len(parts[0][0]))
    for values, weight in parts:
        ok = np.isfinite(values)
        num += np.where(ok, values, 0.0) * np.where(ok, weight, 0.0)
        den += np.where(ok, weight, 0.0)
    out = np.full(len(num), np.nan)
    good = den > 0
    out[good] = num[good] / den[good]
    return out


# ---------------------------------------------------------------- feature series

def _ret(c: np.ndarray, w: int) -> np.ndarray:
    out = np.full(len(c), np.nan)
    if len(c) > w:
        out[w:] = c[w:] / c[:-w] - 1.0
    return out


def _running_mean_distance(c: np.ndarray, w: int) -> np.ndarray:
    """Production keeps a running sum (add close, subtract close[i-w]); replay it exactly."""
    out = np.full(len(c), np.nan)
    s = 0.0
    cl = c.tolist()
    for i, x in enumerate(cl):
        s += x
        if i >= w:
            s -= cl[i - w]
        if i + 1 >= w:
            avg = s / w
            out[i] = x / avg - 1.0 if avg > 0 else np.nan
    return out


def _trailing_mean_prior(x: np.ndarray, w: int, positive_only: bool) -> np.ndarray:
    """mean of finite (and >0 if positive_only) values in x[i-w .. i-1]."""
    vals = np.where(np.isfinite(x) & ((x > 0) if positive_only else True), x, np.nan)
    win = _windows(vals, w + 1)[:, :-1]  # x[i-w .. i-1]
    cnt = np.count_nonzero(~np.isnan(win), axis=1)
    with np.errstate(invalid="ignore"):
        mean = np.nansum(win, axis=1) / np.where(cnt > 0, cnt, 1)
    mean[cnt == 0] = np.nan
    return mean


def feature_series(df: pd.DataFrame) -> dict[str, np.ndarray]:
    """``_rolling_feature_series`` for every index at once."""
    o = df["open"].to_numpy(dtype=float)
    h = df["high"].to_numpy(dtype=float)
    l = df["low"].to_numpy(dtype=float)
    c = df["close"].to_numpy(dtype=float)
    v = df["volume"].to_numpy(dtype=float)
    n = len(c)
    idx = np.arange(n)
    f: dict[str, np.ndarray] = {}
    f["return_1d"] = _ret(c, 1)
    f["return_5d"] = _ret(c, 5)
    f["return_20d"] = _ret(c, 20)
    peak = pd.Series(c).rolling(252, min_periods=1).max().to_numpy()
    f["drawdown_252d"] = c / peak - 1.0
    f["distance_50d"] = _running_mean_distance(c, 50)

    # volume_log_20d: index >= 20 and volume truthy > 0; prior positive volumes mean
    avg_v = _trailing_mean_prior(v, 20, positive_only=True)
    vol_ok = (idx >= 20) & np.isfinite(v) & (v > 0) & np.isfinite(avg_v) & (avg_v > 0)
    f["volume_log_20d"] = np.where(vol_ok, np.log(np.where(vol_ok, v, 1.0) / np.where(vol_ok, avg_v, 1.0)), np.nan)

    pc = np.concatenate([[np.nan], c[:-1]])
    hl_ok = np.isfinite(h) & np.isfinite(l) & (h >= l)
    pc0 = np.where(np.isfinite(pc), pc, np.nan)
    tr = np.maximum.reduce([
        h - l,
        np.where(np.isfinite(pc0), np.abs(h - pc0), 0.0),
        np.where(np.isfinite(pc0), np.abs(l - pc0), 0.0),
    ])
    tr = np.where(hl_ok, tr, np.nan)
    with np.errstate(invalid="ignore", divide="ignore"):
        cl = np.where(h > l, (c - l) / (h - l) * 2.0 - 1.0, 0.0)
    cl = np.where(hl_ok, cl, np.nan)
    atr = _trailing_mean_prior(tr, 20, positive_only=False)
    tr_ok = (idx >= 20) & np.isfinite(tr) & np.isfinite(atr) & (atr > 0)
    f["true_range_atr"] = np.where(tr_ok, tr / np.where(tr_ok, atr, 1.0), np.nan)
    gap_ok = np.isfinite(o) & (o != 0) & np.isfinite(pc) & (pc > 0)
    f["gap"] = np.where(gap_ok, o / np.where(gap_ok, pc, 1.0) - 1.0, np.nan)
    f["close_location"] = cl
    f["true_range"] = tr

    lr = np.full(n, np.nan)
    lr[1:] = np.log(c[1:] / c[:-1])
    rv20 = np.full(n, np.nan)
    va = np.full(n, np.nan)
    vcr = np.full(n, np.nan)
    trend = np.full(n, np.nan)
    negc = np.full(n, np.nan)
    down = np.full(n, np.nan)
    if n > 20:
        w20 = sliding_window_view(lr, 20)  # row j = lr[j .. j+19]; for i>=20 use j=i-19
        tail20 = w20[1:]  # i = 20..n-1  -> rows j = 1..n-20
        sd20 = np.std(tail20, axis=1, ddof=1)
        r20 = sd20 * math.sqrt(TRADING_DAYS)
        tail5 = tail20[:, 15:]
        r5 = np.std(tail5, axis=1, ddof=1) * math.sqrt(TRADING_DAYS)
        sq = tail20 * tail20
        sum_sq = sq.sum(axis=1)
        weekly = tail20.reshape(-1, 4, 5).sum(axis=2)
        daily_rms = np.sqrt(sum_sq / 20.0 * TRADING_DAYS)
        weekly_rms = np.sqrt((weekly * weekly).sum(axis=1) / 4.0 * (TRADING_DAYS / 5.0))
        neg = tail20 < 0
        sl = slice(20, n)
        rv20[sl] = r20
        with np.errstate(invalid="ignore", divide="ignore"):
            va[sl] = np.where((r20 > 0), r5 / np.where(r20 > 0, r20, 1.0), np.nan)
            vcr[sl] = np.where(sum_sq > 0, sq.max(axis=1) / np.where(sum_sq > 0, sum_sq, 1.0), np.nan)
            trend[sl] = np.where(daily_rms > 0, weekly_rms / np.where(daily_rms > 0, daily_rms, 1.0), np.nan)
            negc[sl] = neg.sum(axis=1) / 20.0
            down[sl] = np.where(sum_sq > 0, np.where(neg, sq, 0.0).sum(axis=1) / np.where(sum_sq > 0, sum_sq, 1.0), np.nan)
    f["rv_20d"] = rv20
    f["vol_acceleration"] = va
    f["vcr_20d"] = vcr
    f["trend_ratio_20d"] = trend
    f["negative_consistency_20d"] = negc
    f["downside_share_20d"] = down
    return f


# ------------------------------------------------------------- relative strength

def relative_strength(dates: np.ndarray, c: np.ndarray, bench: pd.Series | None, window: int = 60):
    """``_relative_strength_z`` per date: aligned (stock, benchmark) pairs on common
    dates, 60-position relative return, z over trailing 756 aligned values. A stock
    date with no benchmark bar inherits the last aligned value (production computes
    the series over aligned rows only, so its last element is the last common date).
    """
    n = len(c)
    rel = np.full(n, np.nan)
    relz = np.full(n, np.nan)
    if bench is None or bench.empty:
        return rel, relz
    bmap = bench.to_dict()
    bvals = np.array([bmap.get(d, np.nan) for d in dates], dtype=float)
    aligned = np.isfinite(bvals) & (bvals != 0)
    pos = np.flatnonzero(aligned)
    if len(pos) <= window:
        return rel, relz
    s = c[pos]
    b = bvals[pos]
    series = np.full(len(pos), np.nan)
    series[window:] = (s[window:] / s[:-window] - 1.0) - (b[window:] / b[:-window] - 1.0)
    z = rolling_z(series)
    # map each stock index to last aligned position <= index
    last = np.searchsorted(pos, np.arange(n), side="right") - 1
    has = last >= 0
    # production returns (None, None) when len(aligned) <= window; aligned count up to i is last+1
    enough = has & (last + 1 > window)
    rel[enough] = series[last[enough]]
    relz[enough] = z[last[enough]]
    return rel, relz


# ---------------------------------------------------------------------- the model

def compute(df: pd.DataFrame, bench: pd.Series | None) -> pd.DataFrame:
    """All published technical-fear outputs for every date of ``df``."""
    df = df.reset_index(drop=True)
    n = len(df)
    dates = df["date"].to_numpy()
    c = df["close"].to_numpy(dtype=float)
    h = df["high"].to_numpy(dtype=float)
    v = df["volume"].to_numpy(dtype=float)
    f = feature_series(df)

    rel, relz = relative_strength(dates, c, bench)

    pct = {
        "return_1d_fear": fear_pct(f["return_1d"], True),
        "return_5d_fear": fear_pct(f["return_5d"], True),
        "return_20d_fear": fear_pct(f["return_20d"], True),
        "drawdown_fear": fear_pct(f["drawdown_252d"], True),
        "distance_50d_fear": fear_pct(f["distance_50d"], True),
        "volume_climax": fear_pct(f["volume_log_20d"]),
        "range_climax": fear_pct(f["true_range_atr"]),
        "gap_fear": fear_pct(f["gap"], True),
        "volatility_fear": fear_pct(f["rv_20d"]),
        "vol_acceleration": fear_pct(f["vol_acceleration"]),
        "vcr": fear_pct(f["vcr_20d"]),
        "trend_shape": fear_pct(f["trend_ratio_20d"]),
        "negative_consistency": fear_pct(f["negative_consistency_20d"]),
        "downside_share": fear_pct(f["downside_share_20d"]),
    }
    cl = f["close_location"]
    close_location_fear = np.where(np.isfinite(cl), np.clip((1.0 - cl) * 50.0, 0, 100), np.nan)
    relative_fear = np.where(np.isfinite(relz), np.clip(50.0 - 22.0 * relz, 0, 100), np.nan)
    fam = {
        "price_dislocation": weighted_score([
            (pct["return_1d_fear"], 0.15), (pct["return_5d_fear"], 0.25),
            (pct["return_20d_fear"], 0.20), (pct["drawdown_fear"], 0.20),
            (pct["distance_50d_fear"], 0.20)]),
        "selling_climax": weighted_score([
            (pct["volume_climax"], 0.28), (pct["range_climax"], 0.28),
            (pct["gap_fear"], 0.16), (close_location_fear, 0.18), (pct["vcr"], 0.10)]),
        "volatility_stress": weighted_score([
            (pct["volatility_fear"], 0.38), (pct["vol_acceleration"], 0.27),
            (pct["vcr"], 0.15), (pct["downside_share"], 0.20)]),
        "relative_path_stress": weighted_score([
            (relative_fear, 0.45), (pct["negative_consistency"], 0.30),
            (pct["trend_shape"], 0.25)]),
    }
    pressure = weighted_score([(fam["price_dislocation"], 0.50), (fam["relative_path_stress"], 0.30),
                               (pct["negative_consistency"], 0.20)])
    panic = weighted_score([(fam["price_dislocation"], 0.30), (fam["selling_climax"], 0.35),
                            (fam["volatility_stress"], 0.20), (fam["relative_path_stress"], 0.15)])

    # confirmations (latest row vs prior row / prior five volumes)
    r1 = f["return_1d"]
    positive = np.isfinite(r1) & (r1 > 0)
    upper = np.isfinite(cl) & (cl > 0)
    prior_high = np.concatenate([[np.nan], h[:-1]])
    reclaimed = np.isfinite(prior_high) & (prior_high != 0) & (c > prior_high)
    vv = np.where(np.isfinite(v), v, np.nan)
    recent_peak = pd.Series(vv).shift(1).rolling(5, min_periods=1).max().to_numpy()
    cooled = np.isfinite(vv) & (vv != 0) & np.isfinite(recent_peak) & (recent_peak != 0) & (vv < 0.75 * np.nan_to_num(recent_peak, nan=0.0))
    exhaustion = weighted_score([
        (np.where(positive, 100.0, 0.0), 0.20),
        (np.where(np.isfinite(cl), np.clip((cl + 1.0) * 50.0, 0, 100), np.nan), 0.30),
        (np.where(reclaimed, 100.0, 0.0), 0.30),
        (np.where(cooled, 100.0, 0.0), 0.20),
    ])

    cov_inputs = [*fam.values(), pressure, panic, exhaustion, f["vcr_20d"], f["trend_ratio_20d"],
                  f["true_range_atr"], cl]
    coverage = 100.0 * sum(np.isfinite(x).astype(int) for x in cov_inputs) / len(cov_inputs)
    extreme = sum((np.nan_to_num(x, nan=0.0) >= 70).astype(int) for x in fam.values())
    confirmations = positive.astype(int) + upper.astype(int) + reclaimed.astype(int) + cooled.astype(int)
    panic0 = np.nan_to_num(panic, nan=-1.0)
    candidate = (np.isfinite(panic) & (panic0 >= 80) & (np.nan_to_num(fam["selling_climax"], nan=0.0) >= 65)
                 & (extreme >= 3) & (coverage >= 75))
    exh0 = np.nan_to_num(exhaustion, nan=-1.0)
    state = np.zeros(n, dtype=np.int8)
    state[np.isfinite(pressure) & (np.nan_to_num(pressure, nan=-1) >= 60)] = STATE_CODES["stress_building"]
    state[np.isfinite(panic) & (panic0 >= 70)] = STATE_CODES["panic"]
    state[candidate] = STATE_CODES["capitulation_candidate"]
    state[candidate & np.isfinite(exhaustion) & (exh0 >= 40)] = STATE_CODES["exhaustion_emerging"]
    state[candidate & np.isfinite(exhaustion) & (exh0 >= 65) & (confirmations >= 2)] = STATE_CODES["confirmed_exhaustion"]

    # trend / stretch z (display scores)
    ret20z = rolling_z(_ret(c, 20))
    ret60z = rolling_z(_ret(c, 60))
    ret120z = rolling_z(_ret(c, 120))
    d50z = rolling_z(_running_mean_distance(c, 50))
    d200z = rolling_z(_running_mean_distance(c, 200))
    trend_z = weighted_z([(ret20z, 0.20), (ret60z, 0.25), (ret120z, 0.20), (relz, 0.35)])
    stretch_z = weighted_z([(d50z, 0.55), (d200z, 0.45)])

    # setup (phase / direction / pressure / participation)
    sma50 = pd.Series(c).rolling(50).mean().to_numpy()
    sma200 = pd.Series(c).rolling(200).mean().to_numpy()
    diff = np.diff(c, prepend=np.nan)
    gains = pd.Series(np.where(diff > 0, diff, 0.0)).rolling(14).mean().to_numpy()
    losses = pd.Series(np.where(diff < 0, -diff, 0.0)).rolling(14).mean().to_numpy()
    with np.errstate(invalid="ignore", divide="ignore"):
        rsi = np.where(losses == 0, 100.0, 100.0 - 100.0 / (1.0 + gains / np.where(losses == 0, 1.0, losses)))
    rsi[:14] = np.nan
    l_ = df["low"].to_numpy(dtype=float)
    mf_ok = np.isfinite(h) & np.isfinite(l_) & np.isfinite(c) & np.isfinite(v) & (h > l_)
    with np.errstate(invalid="ignore", divide="ignore"):
        mult = np.where(mf_ok, ((c - l_) - (h - c)) / np.where(mf_ok, h - l_, 1.0), 0.0)
    mfv = pd.Series(np.where(mf_ok, mult * np.nan_to_num(v), 0.0)).rolling(20).sum().to_numpy()
    tv = pd.Series(np.where(mf_ok, np.nan_to_num(v), 0.0)).rolling(20).sum().to_numpy()
    cmf = np.where(tv > 0, mfv / np.where(tv > 0, tv, 1.0), np.nan)
    above50 = np.isfinite(sma50) & (sma50 != 0) & (c > np.nan_to_num(sma50, nan=np.inf))
    above200 = np.isfinite(sma200) & (sma200 != 0) & (c > np.nan_to_num(sma200, nan=np.inf))
    relpct = rel * 100.0
    rel_none = ~np.isfinite(relpct)
    direction = np.full(n, DIRECTION_CODES["mixed_repair"], dtype=np.int8)
    direction[above200] = DIRECTION_CODES["pullback_in_uptrend"]
    direction[~above50 & ~above200 & (rel_none | (np.nan_to_num(relpct) < 0))] = DIRECTION_CODES["lagging_downtrend"]
    direction[above50 & above200 & (rel_none | (np.nan_to_num(relpct) >= 0))] = DIRECTION_CODES["leading_uptrend"]
    oversold = np.isfinite(rsi) & (rsi < 35)
    # production reads the ROUNDED published exhaustion here (scores rounded to 0.1)
    exh_pub = np.where(np.isfinite(exhaustion), np.round(exhaustion, 1), 0.0)
    phase = np.full(n, PHASE_CODES["indeterminate"], dtype=np.int8)
    phase[oversold] = PHASE_CODES["oversold_watch"]
    phase[direction == DIRECTION_CODES["leading_uptrend"]] = PHASE_CODES["trend_intact"]
    stab = np.isin(state, [STATE_CODES["exhaustion_emerging"], STATE_CODES["confirmed_exhaustion"]]) | (exh_pub >= 40)
    phase[stab] = PHASE_CODES["stabilizing"]
    knife = np.isin(state, [STATE_CODES["panic"], STATE_CODES["capitulation_candidate"]]) & (exh_pub < 40)
    phase[knife] = PHASE_CODES["falling_knife"]

    out = pd.DataFrame({
        "date": dates,
        "pressure": pressure, "panic": panic, "exhaustion": exhaustion, "coverage": coverage,
        "state": state,
        **{f"fam_{k}": v_ for k, v_ in fam.items()},
        "extreme_families": extreme.astype(np.int8),
        "confirmations": confirmations.astype(np.int8),
        "conf_positive": positive, "conf_upper": upper, "conf_reclaimed": reclaimed, "conf_cooled": cooled,
        "relative60": rel, "relative60_z": relz,
        "trend_z": trend_z, "stretch_z": stretch_z,
        "rsi14": rsi, "cmf20": cmf, "direction": direction, "phase": phase,
        **{f"pct_{k}": v_ for k, v_ in pct.items()},
        "f_return_5d": f["return_5d"], "f_return_20d": f["return_20d"], "f_drawdown_252d": f["drawdown_252d"],
        "f_distance_50d": f["distance_50d"], "f_rv_20d": f["rv_20d"], "f_volume_log_20d": f["volume_log_20d"],
        "f_close_location": cl,
    })
    return out
