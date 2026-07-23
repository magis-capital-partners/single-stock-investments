#!/usr/bin/env python3
"""Build monthly World Model snapshot + dashboard morning strip (Courtenay v2).

  python _system/scripts/build_world_model_snapshot.py
  python _system/scripts/build_world_model_snapshot.py --month 2026-07

Writes:
  _system/reference/kpi/history/{YYYY-MM}.json  (cold)
  dashboard/data/world_model.json                 (hot strip)

Includes: exceptions, passes, prediction cards, Superorg digests,
expert-horizon convergence, industry checklists.
"""
from __future__ import annotations

import argparse
import csv
import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import resolve_linkages  # noqa: E402
import world_model_common as wm  # noqa: E402


def _month_str(value: str | None) -> str:
    if value:
        return value[:7]
    return date.today().strftime("%Y-%m")


def _industry_membership() -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    if not wm.INDUSTRY_DIR.exists():
        return out
    for path in sorted(wm.INDUSTRY_DIR.glob("*.json")):
        node = wm.load_json(path) or {}
        nid = str(node.get("node_id") or path.stem)
        for t in node.get("linked_tickers") or []:
            out.setdefault(str(t).upper(), []).append(nid)
    return out


def collect_kpi_state() -> dict:
    broken: list[dict] = []
    stale: list[dict] = []
    unchecked: list[dict] = []
    passes: list[dict] = []
    ledger_summaries: list[dict] = []
    membership = _industry_membership()

    for ticker, path, ledger in wm.iter_kpi_ledgers():
        summary = ledger.get("summary") or wm.summarize_statuses(ledger.get("kpis") or [])
        industry_ids = ledger.get("industry_node_ids") or membership.get(ticker, [])
        ledger_summaries.append({
            "ticker": ticker,
            "as_of": ledger.get("as_of"),
            "theme_ids": ledger.get("theme_ids") or [],
            "industry_node_ids": industry_ids,
            "scaffold": bool((ledger.get("scaffold_meta") or {}).get("generated_by")),
            "summary": summary,
            "path": str(path.relative_to(wm.ROOT)).replace("\\", "/"),
        })
        for kpi in ledger.get("kpis") or []:
            row = {
                "ticker": ticker,
                "kpi_id": kpi.get("kpi_id"),
                "label": kpi.get("label"),
                "status": kpi.get("status"),
                "actual": (kpi.get("actual") or {}).get("value"),
                "expected": kpi.get("expected"),
                "binds_to": kpi.get("binds_to"),
                "last_checked": kpi.get("last_checked"),
                "source": kpi.get("source"),
                "prediction_role": kpi.get("prediction_role"),
                "industry_node_ids": industry_ids,
            }
            st = kpi.get("status")
            if st == "fail":
                broken.append(row)
            elif st == "stale":
                stale.append(row)
            elif st == "unchecked":
                unchecked.append(row)
            elif st == "pass":
                passes.append(row)

    derived = wm.load_json(wm.DERIVED_METRICS)
    drifted: list[dict] = []
    for edge_id, metric in (derived.get("metrics") or {}).items():
        if metric.get("status") in ("missing", "unsupported_formula") or metric.get("stale"):
            drifted.append({
                "edge_id": edge_id,
                "metric": metric.get("metric"),
                "status": metric.get("status"),
                "stale": metric.get("stale"),
                "as_of": metric.get("as_of"),
                "theme_id": metric.get("theme_id"),
                "latest": metric.get("latest"),
            })

    return {
        "broken": broken,
        "stale": stale,
        "unchecked": unchecked,
        "passes": passes,
        "drifted_edges": drifted,
        "ledgers": ledger_summaries,
    }


def load_prediction_cards() -> list[dict]:
    cards = []
    if not wm.PREDICTION_CARDS_DIR.exists():
        return cards
    for path in sorted(wm.PREDICTION_CARDS_DIR.glob("*.json")):
        card = wm.load_json(path)
        if not card:
            continue
        cards.append({
            "theme_id": card.get("theme_id"),
            "label": card.get("label"),
            "phase_transition": (card.get("orientation") or {}).get("phase_transition"),
            "regulatory": (card.get("interference") or {}).get("regulatory"),
            "recursive": (card.get("reinforcement") or {}).get("recursive"),
            "gov_stimulus": (card.get("reinforcement") or {}).get("gov_stimulus"),
            "superorg_ids": (card.get("reinforcement") or {}).get("superorg_ids") or [],
            "tam_magnetism": (card.get("reinforcement") or {}).get("tam_magnetism"),
            "expected_value_note": card.get("expected_value_note"),
            "path": str(path.relative_to(wm.ROOT)).replace("\\", "/"),
        })
    return cards


def load_superorg_digests() -> list[dict]:
    out = []
    if not wm.SUPERORG_DIR.exists():
        return out
    for path in sorted(wm.SUPERORG_DIR.glob("*.json")):
        org = wm.load_json(path)
        if not org:
            continue
        pillars = org.get("pillars") or {}
        traffic = {
            name: (meta or {}).get("status")
            for name, meta in pillars.items()
        }
        out.append({
            "org_id": org.get("org_id"),
            "label": org.get("label"),
            "ticker": org.get("ticker"),
            "tickers": org.get("tickers"),
            "role": org.get("role"),
            "summary": org.get("summary"),
            "pillars": traffic,
            "stance_implication": org.get("stance_implication"),
            "path": str(path.relative_to(wm.ROOT)).replace("\\", "/"),
        })
    return out


def _horizon_rows(domain: str) -> list[dict]:
    path = wm.EXPERT_HORIZONS_DIR / f"{domain}.csv"
    if not path.exists():
        return []
    rows = []
    with path.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            try:
                years = float(row.get("years_ahead") or "")
            except ValueError:
                continue
            rows.append({
                "date": row.get("date"),
                "speaker": row.get("speaker"),
                "org": row.get("org"),
                "years_ahead": years,
                "quote_note": row.get("quote_note"),
            })
    rows.sort(key=lambda r: r.get("date") or "")
    return rows


def load_expert_horizons() -> list[dict]:
    domains = []
    if not wm.EXPERT_HORIZONS_DIR.exists():
        return domains
    for path in sorted(wm.EXPERT_HORIZONS_DIR.glob("*.csv")):
        domain = path.stem
        rows = _horizon_rows(domain)
        if len(rows) < 2:
            convergence = "insufficient_history"
            delta = None
        else:
            first, last = rows[0]["years_ahead"], rows[-1]["years_ahead"]
            delta = round(last - first, 2)
            # Courtenay/Musk: years_ahead falling = accelerating / converging
            if delta < -1:
                convergence = "converging"
            elif delta > 1:
                convergence = "receding"
            else:
                convergence = "flat"
        domains.append({
            "domain": domain,
            "convergence": convergence,
            "years_ahead_delta": delta,
            "latest": rows[-1] if rows else None,
            "quote_count": len(rows),
            "in_base_irr": False,
            "path": str(path.relative_to(wm.ROOT)).replace("\\", "/"),
        })
    return domains


def load_industry_nodes() -> list[dict]:
    out = []
    if not wm.INDUSTRY_DIR.exists():
        return out
    for path in sorted(wm.INDUSTRY_DIR.glob("*.json")):
        node = wm.load_json(path)
        if not node:
            continue
        kind = node.get("kind") or "thesis"
        out.append({
            "node_id": node.get("node_id"),
            "label": node.get("label"),
            "kind": kind,
            "checklist": node.get("checklist"),
            "linked_theme_ids": node.get("linked_theme_ids") or [],
            "linked_horizon_domains": node.get("linked_horizon_domains") or [],
            "linked_tickers": node.get("linked_tickers") or [],
            "path": str(path.relative_to(wm.ROOT)).replace("\\", "/"),
        })
    return out


def _industry_scope_line(industry: list) -> str:
    thesis = [n for n in industry if (n.get("kind") or "thesis") != "horizon_industry"]
    horizon = [n for n in industry if n.get("kind") == "horizon_industry"]
    thesis_labels = ", ".join(n.get("label") or n.get("node_id") or "?" for n in thesis) or "none"
    horizon_labels = ", ".join(n.get("label") or n.get("node_id") or "?" for n in horizon) or "none"
    return (
        f"Industries: {len(industry)} "
        f"({len(thesis)} thesis: {thesis_labels}; "
        f"{len(horizon)} horizon: {horizon_labels}). "
        f"Macro is a regime card, not an industry."
    )


def build_strip(state: dict, month: str, cards: list, superorgs: list, horizons: list, industry: list) -> dict:
    broken_n = len(state["broken"])
    stale_n = len(state["stale"])
    drift_n = len(state["drifted_edges"])
    unchecked_n = len(state["unchecked"])
    pass_n = len(state["passes"])
    if broken_n:
        label = "broken"
    elif stale_n or drift_n:
        label = "attention"
    else:
        label = "steady"

    headlines: list[dict] = []
    for row in state["broken"][:6]:
        headlines.append({
            "kind": "fail",
            "ticker": row["ticker"],
            "text": f"{row['ticker']} {row['kpi_id']} failed gate",
            "binds_to": row.get("binds_to"),
        })
    for row in state["stale"][:4]:
        headlines.append({
            "kind": "stale",
            "ticker": row["ticker"],
            "text": f"{row['ticker']} {row['kpi_id']} stale",
            "binds_to": row.get("binds_to"),
        })
    for row in state["drifted_edges"][:4]:
        headlines.append({
            "kind": "drift",
            "ticker": None,
            "text": f"edge {row['edge_id']} drifted ({row.get('status')})",
            "edge_id": row["edge_id"],
        })

    phase_likely = [c["theme_id"] for c in cards if c.get("phase_transition") == "likely"]
    converging = [h["domain"] for h in horizons if h.get("convergence") == "converging"]
    industry_scope = _industry_scope_line(industry)
    thesis_n = sum(1 for n in industry if (n.get("kind") or "thesis") != "horizon_industry")
    horizon_ind_n = sum(1 for n in industry if n.get("kind") == "horizon_industry")

    summary = (
        f"World Model: {broken_n} failed, {stale_n} stale, {drift_n} drifted, "
        f"{unchecked_n} unchecked, {pass_n} passing. "
        f"{industry_scope} "
        f"Phase-likely themes: {', '.join(phase_likely) or 'none'}. "
        f"Horizon converging: {', '.join(converging) or 'none'}."
    )
    ev_stance = (
        "Buy dips when orientation+reinforcement hold and KPI gates pass; "
        "do not when thesis KPIs fail. Context only; no auto IRR."
    )

    return {
        "label": label,
        "as_of": date.today().isoformat(),
        "month": month,
        "summary": summary,
        "ev_stance": ev_stance,
        "disclaimer": (
            "Context only. KPI breaks and Superorg pillar gaps flag [HUMAN REVIEW]; "
            "they do not auto-rewrite Lawrence base IRR."
        ),
        "counts": {
            "fail": broken_n,
            "stale": stale_n,
            "unchecked": unchecked_n,
            "pass": pass_n,
            "drifted_edges": drift_n,
            "ledgers": len(state["ledgers"]),
            "prediction_cards": len(cards),
            "superorgs": len(superorgs),
            "expert_horizon_domains": len(horizons),
            "industry_nodes": len(industry),
            "thesis_industries": thesis_n,
            "horizon_industries": horizon_ind_n,
        },
        "industry_scope": industry_scope,
        "headlines": headlines,
        "broken": state["broken"],
        "stale": state["stale"],
        "drifted_edges": state["drifted_edges"],
        "unchecked": state["unchecked"][:20],
        "passes": state["passes"],
        "ledgers": state["ledgers"],
        "prediction_cards": cards,
        "superorgs": superorgs,
        "expert_horizons": horizons,
        "industry_nodes": industry,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--month", help="YYYY-MM snapshot month (default: current)")
    ap.add_argument(
        "--skip-resolve",
        action="store_true",
        help="Do not re-run resolve_linkages before snapshot",
    )
    args = ap.parse_args()
    month = _month_str(args.month)

    if not args.skip_resolve:
        manifest = wm.load_json(wm.LINKAGES_MANIFEST)
        metrics = {}
        for edge in manifest.get("edges") or []:
            resolved = resolve_linkages.resolve_edge(edge)
            if resolved:
                metrics[str(resolved.get("edge_id"))] = resolved
        wm.write_json(
            wm.DERIVED_METRICS,
            {
                "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "as_of": date.today().isoformat(),
                "disclaimer": (
                    "Context only. Derived linkages inform stance and KPI ledgers; "
                    "they never auto-inflate Lawrence base IRR."
                ),
                "edge_count": len(metrics),
                "metrics": metrics,
            },
        )

    state = collect_kpi_state()
    cards = load_prediction_cards()
    superorgs = load_superorg_digests()
    horizons = load_expert_horizons()
    industry = load_industry_nodes()
    strip = build_strip(state, month, cards, superorgs, horizons, industry)

    hot = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "schema_version": "2.0",
        "strip": strip,
    }
    wm.write_json(wm.DASHBOARD_WORLD_MODEL, hot)

    cold = {
        "month": month,
        "generated_at": hot["generated_at"],
        "counts": strip["counts"],
        "broken": state["broken"],
        "stale": state["stale"],
        "drifted_edges": state["drifted_edges"],
        "unchecked": state["unchecked"],
        "passes": state["passes"],
        "ledgers": state["ledgers"],
        "prediction_cards": cards,
        "superorgs": superorgs,
        "expert_horizons": horizons,
        "industry_nodes": industry,
        "derived_metrics_as_of": wm.load_json(wm.DERIVED_METRICS).get("as_of"),
    }
    history_path = wm.KPI_HISTORY_DIR / f"{month}.json"
    wm.write_json(history_path, cold)

    print(f"wrote {wm.DASHBOARD_WORLD_MODEL.relative_to(wm.ROOT)}")
    print(f"wrote {history_path.relative_to(wm.ROOT)}")
    print(
        f"world_model: label={strip['label']} "
        f"fail={strip['counts']['fail']} pass={strip['counts']['pass']} "
        f"cards={strip['counts']['prediction_cards']} "
        f"superorgs={strip['counts']['superorgs']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
