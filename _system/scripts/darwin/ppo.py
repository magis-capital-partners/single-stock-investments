"""Lightweight PPO-style policy on portfolio latent state (Phase 3, numpy)."""
from __future__ import annotations

import math

import numpy as np

from .backtest import portfolio_return, quarterly_rebalance_points
from .constraints import apply_constraints
from .policies import policy_softmax_latent


class LatentPPOPolicy:
    """Linear actor on pooled latent factors; REINFORCE-style updates."""

    def __init__(self, n_factors: int, n_assets: int, seed: int = 0):
        rng = np.random.default_rng(seed)
        self.W = rng.normal(0, 0.05, (n_factors, n_assets))
        self.b = np.zeros(n_assets)
        self.n_assets = n_assets

    def logits(self, state: np.ndarray) -> np.ndarray:
        return state @ self.W + self.b

    def weights(self, state: np.ndarray, temperature: float = 0.6) -> np.ndarray:
        z = self.logits(state) / max(temperature, 0.05)
        z -= z.max()
        e = np.exp(z)
        return e / (e.sum() + 1e-9)


def pool_latent(latent: dict[str, list[float]], tickers: list[str], prev_w: dict[str, float]) -> np.ndarray:
    if not tickers:
        return np.zeros(5)
    k = len(next(iter(latent.values()), [0.0]))
    acc = np.zeros(k)
    for t in tickers:
        z = np.array(latent.get(t, [0.0] * k), dtype=float)
        acc += prev_w.get(t, 1.0 / len(tickers)) * z
    return acc


def train_ppo(
    rows: list[dict],
    panel: dict,
    latent: dict[str, list[float]],
    mandate: dict,
    training: dict,
) -> tuple[LatentPPOPolicy, dict]:
    tickers = [r["ticker"] for r in rows]
    dates = panel["dates"]
    returns_by_ticker = panel["returns_by_ticker"]
    n_factors = len(next(iter(latent.values())))
    n_assets = len(tickers)
    steps = training.get("ppo_steps", 40)
    lr = training.get("ppo_lr", 0.05)
    seeds = training.get("ppo_seeds", 3)
    kappa = (mandate.get("mandate") or {}).get("turnover_penalty_kappa", 0.35)
    falsifier_map = {r["ticker"]: r.get("falsifier_count", 0) for r in rows}

    q_idx = quarterly_rebalance_points(dates)
    best_policy = None
    best_sharpe = -1e9
    metrics: dict = {}

    for seed in range(seeds):
        policy = LatentPPOPolicy(n_factors, n_assets, seed=seed + 7)
        prev_w = {t: 1.0 / n_assets for t in tickers}
        rewards_log: list[float] = []

        for _ in range(steps):
            total_reward = 0.0
            prev = None
            for qi in q_idx[:-1]:
                state = pool_latent(latent, tickers, prev_w)
                raw = policy.weights(state)
                w_dict = {tickers[i]: float(raw[i]) for i in range(n_assets)}
                w_dict, _ = apply_constraints(
                    tickers, w_dict, prev, mandate, falsifier_map
                )
                next_i = q_idx[q_idx.index(qi) + 1] if qi in q_idx else qi + 1
                if next_i >= len(dates):
                    continue
                pr = 0.0
                for mi in range(qi + 1, min(next_i + 1, len(dates))):
                    r_row = {
                        t: returns_by_ticker[t][mi]
                        for t in tickers
                        if mi < len(returns_by_ticker[t])
                    }
                    pr += portfolio_return(w_dict, r_row)
                if prev:
                    turn = 0.5 * sum(
                        abs(w_dict.get(t, 0) - prev.get(t, 0)) for t in set(w_dict) | set(prev)
                    )
                else:
                    turn = 0.0
                reward = math.log1p(pr) - kappa * turn
                total_reward += reward
                # policy gradient: encourage weights that earned reward
                grad_scale = reward * lr
                state_col = state.reshape(-1, 1)
                for i, t in enumerate(tickers):
                    policy.W[:, i] += grad_scale * state * w_dict.get(t, 0.0)
                    policy.b[i] += grad_scale * 0.1
                prev = w_dict
                prev_w = w_dict
            rewards_log.append(total_reward)

        # evaluate
        def policy_fn(ts: list[str], _qi: int) -> dict[str, float]:
            state = pool_latent(latent, ts, prev_w)
            raw = policy.weights(state)
            return {ts[i]: float(raw[i]) for i in range(len(ts))}

        from .backtest import simulate

        res = simulate(tickers, dates, returns_by_ticker, policy_fn, mandate, falsifier_map)
        sh = res.get("sharpe_annualized", -999)
        if sh > best_sharpe:
            best_sharpe = sh
            best_policy = policy
            metrics = {"sharpe": sh, "seed": seed, "res": res, "rewards": rewards_log[-5:]}

    return best_policy or LatentPPOPolicy(n_factors, n_assets), metrics


def ppo_weights(
    policy: LatentPPOPolicy,
    rows: list[dict],
    latent: dict[str, list[float]],
    mandate: dict,
    prev: dict[str, float] | None,
) -> dict[str, float]:
    tickers = [r["ticker"] for r in rows]
    prev_w = prev or {t: 1.0 / len(tickers) for t in tickers}
    state = pool_latent(latent, tickers, prev_w)
    raw = policy.weights(state)
    w = {tickers[i]: float(raw[i]) for i in range(len(tickers))}
    falsifier_map = {r["ticker"]: r.get("falsifier_count", 0) for r in rows}
    w, _ = apply_constraints(tickers, w, prev, mandate, falsifier_map)
    return w
