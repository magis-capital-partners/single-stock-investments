"""Persist surviving policy genomes across runs (Workstream C)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .config import MODEL_DIR


POPULATION_PATH = MODEL_DIR / "population.json"
LINEAGE_PATH = MODEL_DIR / "lineage.json"


def load_population() -> list[dict]:
    if not POPULATION_PATH.exists():
        return []
    try:
        data = json.loads(POPULATION_PATH.read_text(encoding="utf-8"))
        return data.get("genomes") or []
    except json.JSONDecodeError:
        return []


def save_population(genomes: list[dict], best: dict, fitness: float) -> None:
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    ranked = sorted(genomes, key=lambda g: g.get("fitness", -1e9), reverse=True)[:8]
    payload = {
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "best_fitness": fitness,
        "genomes": ranked,
        "champion": best,
    }
    POPULATION_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def append_lineage(event: dict) -> list[dict]:
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    log: list[dict] = []
    if LINEAGE_PATH.exists():
        try:
            log = json.loads(LINEAGE_PATH.read_text(encoding="utf-8")).get("events") or []
        except json.JSONDecodeError:
            log = []
    log.append({**event, "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")})
    log = log[-20:]
    LINEAGE_PATH.write_text(json.dumps({"events": log}, indent=2) + "\n", encoding="utf-8")
    return log


def seed_genomes(rng, base: list[dict], n: int) -> list[dict]:
    """Seed GA from prior survivors."""
    from .policies import mutate_genome, random_genome

    seeds = [g.get("genome") or g for g in base if g.get("genome") or g.get("policy")]
    out = []
    for g in seeds[:4]:
        out.append(dict(g))
    while len(out) < n:
        if seeds and rng.random() < 0.6:
            parent = seeds[rng.integers(0, len(seeds))]
            genome = parent.get("genome") or parent
            out.append(mutate_genome(genome, rng, 0.12))
        else:
            out.append(random_genome(rng))
    return out[:n]
