"""Small, dependency-free inference helpers (no statsmodels on this box)."""
from __future__ import annotations

import numpy as np


def nw_ols(y: np.ndarray, X: np.ndarray, lags: int) -> tuple[np.ndarray, np.ndarray]:
    """OLS coefficients and Newey-West (Bartlett) HAC standard errors.

    Rows must be in time order; overlapping h-day outcomes need lags >= h-1.
    """
    ok = np.isfinite(y) & np.all(np.isfinite(X), axis=1)
    y = y[ok]
    X = X[ok]
    n, k = X.shape
    if n <= k + 2:
        return np.full(k, np.nan), np.full(k, np.nan)
    xtx_inv = np.linalg.pinv(X.T @ X)
    beta = xtx_inv @ (X.T @ y)
    e = y - X @ beta
    xe = X * e[:, None]
    S = xe.T @ xe
    L = min(lags, n - 1)
    for lag in range(1, L + 1):
        w = 1.0 - lag / (L + 1.0)
        G = xe[lag:].T @ xe[:-lag]
        S += w * (G + G.T)
    V = xtx_inv @ S @ xtx_inv
    return beta, np.sqrt(np.maximum(np.diag(V), 0.0))


def nw_mean_diff(r: np.ndarray, d: np.ndarray, lags: int) -> dict:
    """Difference in mean outcome (d=1 minus d=0) with HAC t-stat."""
    X = np.column_stack([np.ones(len(r)), d.astype(float)])
    beta, se = nw_ollsafe(r, X, lags)
    return {"diff": beta[1], "se": se[1], "t": beta[1] / se[1] if se[1] > 0 else np.nan}


def nw_ollsafe(y, X, lags):
    try:
        return nw_ols(y, X, lags)
    except np.linalg.LinAlgError:
        return np.full(X.shape[1], np.nan), np.full(X.shape[1], np.nan)


def nw_mean(r: np.ndarray, lags: int) -> dict:
    r = r[np.isfinite(r)]
    if len(r) < 3:
        return {"mean": np.nan, "se": np.nan, "t": np.nan, "n": len(r)}
    beta, se = nw_ols(r, np.ones((len(r), 1)), lags)
    return {"mean": beta[0], "se": se[0], "t": beta[0] / se[0] if se[0] > 0 else np.nan, "n": len(r)}


def episodes(idx: np.ndarray, gap: int) -> np.ndarray:
    """Cluster sorted event indices: a new episode starts after > gap sessions."""
    if len(idx) == 0:
        return np.array([], dtype=int)
    lab = np.zeros(len(idx), dtype=int)
    for i in range(1, len(idx)):
        lab[i] = lab[i - 1] + (1 if idx[i] - idx[i - 1] > gap else 0)
    return lab


def cluster_bootstrap_mean(values: np.ndarray, clusters: np.ndarray, B: int = 4000, seed: int = 1) -> tuple[float, float, float]:
    """Mean and 95% CI resampling whole clusters (episodes / dates)."""
    ok = np.isfinite(values)
    values = values[ok]
    clusters = clusters[ok]
    if len(values) == 0:
        return np.nan, np.nan, np.nan
    uniq, inv = np.unique(clusters, return_inverse=True)
    sums = np.bincount(inv, weights=values)
    cnts = np.bincount(inv)
    rng = np.random.default_rng(seed)
    k = len(uniq)
    draws = rng.integers(0, k, size=(B, k))
    s = sums[draws].sum(axis=1)
    c = cnts[draws].sum(axis=1)
    boot = s / np.maximum(c, 1)
    return values.mean(), float(np.percentile(boot, 2.5)), float(np.percentile(boot, 97.5))


def spearman(a: np.ndarray, b: np.ndarray) -> float:
    ok = np.isfinite(a) & np.isfinite(b)
    if ok.sum() < 10:
        return np.nan
    ra = _rank(a[ok])
    rb = _rank(b[ok])
    return float(np.corrcoef(ra, rb)[0, 1])


def _rank(x: np.ndarray) -> np.ndarray:
    from scipy.stats import rankdata

    return rankdata(x, method="average") - 1.0


def auc(score: np.ndarray, label: np.ndarray) -> float:
    """Probability a random positive outranks a random negative (Mann-Whitney)."""
    ok = np.isfinite(score) & np.isfinite(label)
    s = score[ok]
    y = label[ok].astype(bool)
    n1 = y.sum()
    n0 = (~y).sum()
    if n1 == 0 or n0 == 0:
        return np.nan
    r = _rank(s) + 1.0
    return float((r[y].sum() - n1 * (n1 + 1) / 2.0) / (n1 * n0))
