"""Genetic search over policy genomes with adversarial fitness."""
from __future__ import annotations

import numpy as np

from .adversary import adversarial_fitness, stress_returns
from .backtest import simulate
from .persistence import load_population, save_population, seed_genomes
from .policies import apply_policy, random_genome


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
    use_adversary: bool = True,
) -> float:
    policy_name = genome.get("policy", "irr_ranked")
    g = {**genome, "use_latent": True} if latent else dict(genome)

    def policy_fn(_ts: list[str], _qi: int) -> dict[str, float]:
        return apply_policy(policy_name, rows, g, latent)

    res = simulate(tickers, dates, returns_by_ticker, policy_fn, mandate, falsifier_map)
    if res.get("error"):
        return -1e6
    sharpe = res.get("sharpe_annualized", 0.0)
    turnover = res.get("avg_turnover_one_way", 0.0)
    normal = sharpe - kappa * turnover

    if not use_adversary:
        return normal

    stressed_panel = stress_returns(returns_by_ticker)
    res_s = simulate(tickers, dates, stressed_panel, policy_fn, mandate, falsifier_map)
    if res_s.get("error"):
        return normal * 0.5
    stressed = res_s.get("sharpe_annualized", 0.0) - kappa * res_s.get("avg_turnover_one_way", 0.0)
    adv_cfg = (mandate.get("evolution") or {}).get("adversarial_blend", 0.45)
    return adversarial_fitness(normal, stressed, blend=adv_cfg)


def run_ga(
    rows: list[dict],
    panel: dict,
    mandate: dict,
    latent: dict[str, list[float]] | None,
    training: dict,
) -> tuple[dict, list[dict], list[dict]]:
    tickers = [r["ticker"] for r in rows]
    dates = panel["dates"]
    returns_by_ticker = panel["returns_by_ticker"]
    falsifier_map = {r["ticker"]: r.get("falsifier_count", 0) for r in rows}
    kappa = (mandate.get("mandate") or {}).get("turnover_penalty_kappa", 0.35)
    use_adv = (mandate.get("evolution") or {}).get("adversarial_fitness", True)

    pop_size = training.get("ga_population", 24)
    generations = training.get("ga_generations", 12)
    mut_rate = training.get("ga_mutation_rate", 0.15)
    rng = np.random.default_rng(42)

    prior = load_population()
    if prior:
        population = seed_genomes(rng, prior, pop_size)
    else:
        population = [random_genome(rng) for _ in range(pop_size)]

    history: list[dict] = []
    survivors: list[dict] = []

    best_g, best_f = population[0], -1e9
    for gen in range(generations):
        scored = []
        for g in population:
            f = fitness(
                g,
                rows,
                tickers,
                dates,
                returns_by_ticker,
                mandate,
                latent,
                falsifier_map,
                kappa,
                use_adversary=use_adv,
            )
            scored.append((f, g))
            if f > best_f:
                best_f, best_g = f, g
        scored.sort(key=lambda x: -x[0])
        history.append({"generation": gen, "best_fitness": round(best_f, 4)})
        for f, g in scored[:3]:
            survivors.append({"generation": gen, "fitness": round(f, 4), "genome": g})
        next_pop = [scored[0][1], scored[1][1] if len(scored) > 1 else scored[0][1]]
        while len(next_pop) < pop_size:
            i, j = rng.integers(0, min(5, len(scored))), rng.integers(0, min(5, len(scored)))
            parent = scored[min(i, j)][1]
            from .policies import mutate_genome

            next_pop.append(mutate_genome(parent, rng, mut_rate))
        population = next_pop

    save_population(survivors, best_g, best_f)
    return best_g, history, survivors
