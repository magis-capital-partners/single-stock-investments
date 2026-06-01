"""Genetic search over policy genomes (Phase 3)."""
from __future__ import annotations

import numpy as np

from .backtest import simulate
from .policies import apply_policy, mutate_genome, random_genome


def fitness(
    genome: dict,
    rows: list[dict],
    tickers: list[str],
    dates: list[str],
    returns_by_ticker: dict[str, list[float]],
    mandate: dict,
    latent: dict[str, list[float]] | None,
    falsifier_map: dict[str, int],
    kappa: float,
) -> float:
    policy_name = genome.get("policy", "irr_ranked")
    if latent:
        genome = {**genome, "use_latent": True}

    def policy_fn(_ts: list[str], _qi: int) -> dict[str, float]:
        return apply_policy(policy_name, rows, genome, latent)

    res = simulate(tickers, dates, returns_by_ticker, policy_fn, mandate, falsifier_map)
    if res.get("error"):
        return -1e6
    sharpe = res.get("sharpe_annualized", 0.0)
    turnover = res.get("avg_turnover_one_way", 0.0)
    return sharpe - kappa * turnover


def run_ga(
    rows: list[dict],
    panel: dict,
    mandate: dict,
    latent: dict[str, list[float]] | None,
    training: dict,
) -> tuple[dict, list[dict]]:
    tickers = [r["ticker"] for r in rows]
    dates = panel["dates"]
    returns_by_ticker = panel["returns_by_ticker"]
    falsifier_map = {r["ticker"]: r.get("falsifier_count", 0) for r in rows}
    kappa = (mandate.get("mandate") or {}).get("turnover_penalty_kappa", 0.35)

    pop_size = training.get("ga_population", 24)
    generations = training.get("ga_generations", 12)
    mut_rate = training.get("ga_mutation_rate", 0.15)
    rng = np.random.default_rng(42)

    population = [random_genome(rng) for _ in range(pop_size)]
    history: list[dict] = []

    best_g, best_f = population[0], -1e9
    for gen in range(generations):
        scored = []
        for g in population:
            f = fitness(
                g, rows, tickers, dates, returns_by_ticker, mandate, latent, falsifier_map, kappa
            )
            scored.append((f, g))
            if f > best_f:
                best_f, best_g = f, g
        scored.sort(key=lambda x: -x[0])
        history.append({"generation": gen, "best_fitness": round(best_f, 4)})
        # elitism + tournament
        next_pop = [scored[0][1], scored[1][1]]
        while len(next_pop) < pop_size:
            i, j = rng.integers(0, min(5, len(scored))), rng.integers(0, min(5, len(scored)))
            parent = scored[min(i, j)][1]
            next_pop.append(mutate_genome(parent, rng, mut_rate))
        population = next_pop

    return best_g, history
