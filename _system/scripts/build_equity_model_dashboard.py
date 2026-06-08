#!/usr/bin/env python3
"""Build equity model bundles for dashboard visualization."""
from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "dashboard" / "data"
OUTPUT = DATA_DIR / "equity_models.json"
REGISTRY = ROOT / "_system" / "portfolio" / "equity_model_registry.json"
GITHUB_REPO = "GoldmanDrew/single-stock-investments"

MIN_PANEL_ROWS = 8


def github_blob(rel: str) -> str:
    return f"https://github.com/{GITHUB_REPO}/blob/main/{rel.replace(chr(92), '/')}"


def load_json(path: Path) -> dict | list | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def load_registry() -> list[str]:
    reg = load_json(REGISTRY) or {}
    enabled = reg.get("enabled") or []
    return list(enabled)


def round3(v) -> float | None:
    if v is None or v == "":
        return None
    try:
        return round(float(v), 3)
    except (TypeError, ValueError):
        return None


def parse_panel_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows: list[dict] = []
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            fy = row.get("fy", "")
            half = row.get("half", "")
            label = f"FY{fy}{half}"
            base_fee = round3(row.get("base_fee"))
            perf_fee = round3(row.get("perf_fee"))
            revenue = round3(row.get("revenue"))
            if base_fee is None and perf_fee is None and revenue:
                # infer split when only total revenue present
                pass
            rows.append(
                {
                    "label": label,
                    "period_end": row.get("period_end"),
                    "revenue": revenue,
                    "base_fee": base_fee,
                    "perf_fee": perf_fee,
                    "ordinary": round3(row.get("ordinary")),
                    "net_income": round3(row.get("net_income")),
                    "aum_end_jpym": round3(row.get("aum_end_jpym")),
                    "nikkei_ret": round3(row.get("nikkei_ret")),
                    "is_h2": int(row.get("is_h2") or 0),
                    "headcount": round3(row.get("headcount")),
                }
            )
    return rows[-24:]


def parse_residuals_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out: list[dict] = []
    with path.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            out.append({
                "label": row.get("label"),
                "period_end": row.get("period_end"),
                "target": row.get("target"),
                "actual": round3(row.get("actual")),
                "fitted": round3(row.get("fitted")),
                "residual": round3(row.get("residual")),
                "is_oos": int(row.get("is_oos") or 0),
            })
    return out[-80:]


def parse_forecasts_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out: list[dict] = []
    with path.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            out.append(
                {
                    "horizon": row.get("horizon"),
                    "scenario": row.get("scenario"),
                    "nikkei_ret": round3(row.get("nikkei_ret")),
                    "revenue_m": round3(row.get("revenue_m")),
                    "net_income_m": round3(row.get("net_income_m")),
                    "perf_fee_m": round3(row.get("perf_fee_m")),
                    "revenue_lo80": round3(row.get("revenue_lo80")),
                    "revenue_hi80": round3(row.get("revenue_hi80")),
                    "net_income_lo80": round3(row.get("net_income_lo80")),
                    "net_income_hi80": round3(row.get("net_income_hi80")),
                }
            )
    return out


def liquidity_from_valuation(valuation: dict | None, ticker: str) -> dict:
    if ticker == "7176.T":
        inputs = (valuation or {}).get("inputs") or {}
        price = inputs.get("price")
        return {
            "tier": "illiquid_tpm",
            "exchange": "TOKYO PRO Market",
            "last_print": {
                "date": "2026-01-07",
                "price_jpy": price or 464,
                "volume_shares": 100,
            },
            "warning": (
                "TOKYO PRO Market: extremely thin tape; retail buy restricted. "
                "Confirm broker TPM / qualified-investor access before sizing."
            ),
        }
    return {"tier": "standard", "exchange": None, "last_print": None, "warning": None}


def build_production_block(
    results: dict,
    spec_comparison: dict,
    diagnostics: dict,
) -> dict:
    spec = (
        diagnostics.get("production_spec")
        or results.get("production_spec")
        or (spec_comparison or {}).get("production_spec")
        or "v1"
    )
    leaderboard = (spec_comparison or {}).get("leaderboard") or []
    prod_row = next(
        (r for r in leaderboard if r.get("production_default")),
        next((r for r in leaderboard if r.get("spec") == spec), None),
    )
    v1_row = next((r for r in leaderboard if r.get("spec") == "v1"), None)
    v2_row = next((r for r in leaderboard if r.get("spec") == "v2"), None)

    oos_v5 = (results.get("oos_metrics_v5") or {}).get("model_v5") or {}
    if not oos_v5.get("rmse_jpym") and prod_row:
        oos_v5 = {
            "rmse_jpym": prod_row.get("revenue_oos_rmse"),
            "mape_pct": None,
            "n": 9,
        }

    perf_key = f"perf_fee_model_{spec}" if spec != "v1" else "perf_fee_model"
    perf_model = results.get(perf_key) or results.get("perf_fee_model") or {}
    split = perf_model.get("split_base_rates") or {}

    return {
        "spec": spec,
        "walk_forward_key": "model_v5" if spec == "v5" else "model",
        "acceptance_rule": (spec_comparison or {}).get(
            "acceptance_rule",
            "Reject spec if perf_fee_h2_oos_rmse worsens vs prior",
        ),
        "revenue_oos_rmse": prod_row.get("revenue_oos_rmse") if prod_row else oos_v5.get("rmse_jpym"),
        "revenue_oos_r2": prod_row.get("revenue_oos_r2") if prod_row else None,
        "perf_fee_h2_oos_rmse": prod_row.get("perf_fee_h2_oos_rmse") if prod_row else None,
        "perf_fee_h2_oos_r2": prod_row.get("perf_fee_h2_oos_r2") if prod_row else None,
        "v1_perf_fee_h2_oos_rmse": v1_row.get("perf_fee_h2_oos_rmse") if v1_row else None,
        "v2_revenue_oos_rmse": v2_row.get("revenue_oos_rmse") if v2_row else None,
        "v2_perf_fee_h2_oos_rmse": v2_row.get("perf_fee_h2_oos_rmse") if v2_row else None,
        "oos_revenue": oos_v5,
        "forms": {
            "base_fee": results.get("base_fee_model"),
            "perf_fee": perf_model,
            "split_base_rates": split,
            "earnings_bridge": results.get("earnings_bridge"),
        },
    }


def equity_model_summary(bundle: dict) -> dict:
    prod = bundle.get("production") or {}
    oos = prod.get("oos_revenue") or {}
    rev_rmse = oos.get("rmse_jpym")
    naive_rmse = ((bundle.get("oos_metrics") or {}).get("naive_lastyear") or {}).get("rmse_jpym")
    beats_revenue = (
        rev_rmse is not None
        and naive_rmse is not None
        and float(rev_rmse) < float(naive_rmse)
    )
    nowcast = bundle.get("nowcast") or {}
    nc = nowcast.get("nowcast_jpym") or {}
    spec = prod.get("spec") or bundle.get("production_spec") or "v1"
    perf_h2 = prod.get("perf_fee_h2_oos_rmse")
    headline = (
        f"{spec} · Nowcast {nowcast.get('fiscal_half', '')} revenue ¥{nc.get('revenue', 0):,}m"
        if nc.get("revenue")
        else f"{spec} · Earnings model ready"
    )
    if perf_h2 is not None:
        headline += f" · perf H2 OOS ¥{perf_h2:,.0f}m"
    if not beats_revenue and rev_rmse is not None:
        headline += " · revenue level trails seasonal naive"
    diag = bundle.get("diagnostics") or {}
    kpi = ((diag.get("targets") or {}).get("perf_fee_h2_positive") or {}).get("out_of_sample") or {}
    return {
        "ready": True,
        "diagnostics_ready": bundle.get("diagnostics_ready", False),
        "production_spec": spec,
        "as_of": bundle.get("as_of"),
        "headline": headline,
        "model_beats_naive": beats_revenue,
        "model_type": bundle.get("model_type"),
        "perf_fee_h2_oos_r2": kpi.get("r2"),
        "perf_fee_h2_oos_rmse": perf_h2,
        "revenue_oos_rmse": rev_rmse,
    }


def build_ticker_bundle(ticker: str) -> dict | None:
    ticker_dir = ROOT / ticker
    model_dir = ticker_dir / "research" / "model"
    results_path = model_dir / "model_results.json"
    panel_path = model_dir / "panel_halfyear.csv"

    if not results_path.exists() or not panel_path.exists():
        return None

    panel = parse_panel_csv(panel_path)
    if len(panel) < MIN_PANEL_ROWS:
        return None

    results = load_json(results_path) or {}
    diagnostics = load_json(model_dir / "model_diagnostics.json") or {}
    spec_comparison = load_json(model_dir / "spec_comparison.json") or {}
    coeff_bootstrap = load_json(model_dir / "coefficient_bootstrap.json") or {}
    valuation = load_json(ticker_dir / "research" / "valuation.json") or {}
    nowcast = load_json(model_dir / "nowcast_latest.json") or {}
    shares_raw = load_json(ticker_dir / "research" / "shares_outstanding_split_adjusted.json") or {}

    shares_series = []
    for pt in shares_raw.get("series") or []:
        sh = pt.get("split_adjusted_shares")
        if sh is None:
            continue
        # dashboard chart: use post-2022 scale only (avoid pre-split billions)
        if float(sh) > 500_000_000:
            continue
        shares_series.append(
            {"date": pt.get("date"), "split_adjusted_shares": int(sh), "note": pt.get("note")}
        )

    cagr_block = shares_raw.get("cagr_reduction_split_adjusted") or []
    share_cagr = None
    for block in cagr_block:
        if block.get("label") == "pre-2023 split":
            share_cagr = block.get("cagr_reduction_pct")
            break

    inputs = valuation.get("inputs") or {}
    implied = valuation.get("implied_return") or {}
    class_in = valuation.get("classification_inputs") or {}

    production = build_production_block(results, spec_comparison, diagnostics)
    prod_rev_rmse = (production.get("oos_revenue") or {}).get("rmse_jpym")
    naive_rmse = (results.get("oos_metrics") or {}).get("naive_lastyear", {}).get("rmse_jpym")
    loses_to_naive = (
        prod_rev_rmse is not None
        and naive_rmse is not None
        and float(prod_rev_rmse) > float(naive_rmse)
    )

    caveats = list(nowcast.get("caveats") or [])
    if loses_to_naive:
        caveats.insert(
            0,
            f"{production.get('spec', 'v5')} revenue OOS RMSE is worse than same-half-last-year naive; "
            "use model for perf-fee seasonality and pre-report nowcast, not level beats.",
        )

    skeptical = sorted(ticker_dir.glob("research/equity_report_skeptical_*.md"))
    skeptical_rel = (
        f"{ticker}/research/{skeptical[0].name}" if skeptical else None
    )

    rel = ticker
    diagnostics_ready = bool(diagnostics.get("targets"))
    nc = nowcast.get("nowcast_jpym") or {}
    headline = (
        f"{production['spec']} · Nowcast {nowcast.get('fiscal_half', '')} revenue ¥{nc.get('revenue', 0):,}m"
        if nc.get("revenue")
        else f"{production['spec']} · Earnings model ready"
    )
    if production.get("perf_fee_h2_oos_rmse") is not None:
        headline += f" · perf H2 OOS ¥{production['perf_fee_h2_oos_rmse']:,.0f}m"
    if loses_to_naive:
        headline += " · revenue level trails seasonal naive"

    bundle = {
        "model_ready": True,
        "diagnostics_ready": diagnostics_ready,
        "production_spec": production["spec"],
        "production": production,
        "primary_kpi": diagnostics.get("primary_kpi"),
        "model_type": "earnings_semiannual",
        "as_of": results.get("as_of") or valuation.get("as_of"),
        "headline": headline,
        "company": ticker,
        "liquidity": liquidity_from_valuation(valuation, ticker),
        "lawrence": {
            "stance_gate_irr_pct": implied.get("base_pct"),
            "stance": class_in.get("stance") or valuation.get("stance"),
            "owner_cash_mid_cycle_jpy": inputs.get("fcf_per_share"),
            "price_today_jpy": inputs.get("price"),
            "price_source": inputs.get("price_source"),
        },
        "nowcast": nowcast,
        "spec": production.get("forms") or {
            "base_fee": results.get("base_fee_model"),
            "perf_fee": results.get("perf_fee_model"),
            "earnings_bridge": results.get("earnings_bridge"),
        },
        "spec_v1": {
            "base_fee": results.get("base_fee_model"),
            "perf_fee": results.get("perf_fee_model"),
            "earnings_bridge": results.get("earnings_bridge"),
        },
        "oos_metrics": results.get("oos_metrics"),
        "oos_metrics_v2": results.get("oos_metrics_v2"),
        "oos_metrics_v3a": results.get("oos_metrics_v3a"),
        "oos_metrics_v5": results.get("oos_metrics_v5"),
        "diagnostics": diagnostics if diagnostics_ready else None,
        "spec_comparison": spec_comparison,
        "coefficient_bootstrap": coeff_bootstrap,
        "residuals": parse_residuals_csv(model_dir / "residuals_halfyear.csv"),
        "walk_forward": results.get("walk_forward"),
        "panel": panel,
        "forecasts": parse_forecasts_csv(model_dir / "forecasts.csv"),
        "shares": {
            "cagr_reduction_pct": share_cagr,
            "series": shares_series,
        },
        "triangulation": [
            "Lawrence IRR uses mid-cycle owner cash (FY2025 ¥137/sh), not peak FY2026 success-fee earnings.",
            "High synthesis return is not executable on the public TPM tape at last thin print.",
            "Model edge is performance-fee seasonality and pre-report nowcast, not beating seasonal naive on RMSE.",
        ],
        "caveats": caveats,
        "links": {
            "model_report": github_blob(f"{rel}/research/model/earnings_model_report.md"),
            "data_dictionary": github_blob(f"{rel}/research/model/data_dictionary.md"),
            "forecasts_csv": github_blob(f"{rel}/research/model/forecasts.csv"),
            "model_results": github_blob(f"{rel}/research/model/model_results.json"),
            "model_diagnostics": github_blob(f"{rel}/research/model/model_diagnostics.json"),
            "skeptical_report": github_blob(skeptical_rel) if skeptical_rel else None,
        },
    }
    return bundle


def build() -> dict:
    tickers: dict[str, dict] = {}
    summaries: dict[str, dict] = {}

    registry = load_registry()
    for ticker in registry:
        bundle = build_ticker_bundle(ticker)
        if bundle:
            tickers[ticker] = bundle
            summaries[ticker] = equity_model_summary(bundle)

    # auto-discover any ticker with model_results not in registry
    for path in ROOT.glob("*/research/model/model_results.json"):
        ticker = path.parts[-4]
        if ticker.startswith("_") or ticker in tickers:
            continue
        bundle = build_ticker_bundle(ticker)
        if bundle:
            tickers[ticker] = bundle
            summaries[ticker] = equity_model_summary(bundle)

    return {
        "built_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ticker_count": len(tickers),
        "tickers": tickers,
        "summaries": summaries,
    }


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    payload = build()
    OUTPUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {OUTPUT} ({payload['ticker_count']} model tickers)")


if __name__ == "__main__":
    main()
