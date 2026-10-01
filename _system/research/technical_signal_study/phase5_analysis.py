"""Phase 5c: survivorship, beta and trading costs.

1. beta    -- does the panic edge survive beta-adjusted (residual) returns?
2. pit     -- the same tests on the point-in-time S&P 500 (2007-2026), the
              closest free approximation of a survivorship-free universe.
3. bound   -- how many unseen failures it would take to erase the edge,
              against the failures actually missing from the data.
4. costs   -- strategy returns net of Abdi-Ranaldo spread + 2bp commission.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.dataset as ds

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import stats_util as su  # noqa: E402
from common import DATA, INDEX_SIGNALS, RESULTS  # noqa: E402

PANEL = DATA / "phase5_panel.parquet"
MEMBERSHIP = DATA / "sp500_membership.parquet"
PIT_START = 20070101
COMMISSION_RT = 0.0002  # round trip
MIN_STOCKS = 40


def nw(values, lag):
    v = np.asarray(values, float)
    v = v[np.isfinite(v)]
    if len(v) < 30:
        return {"mean": None, "t": None, "n": int(len(v))}
    m = su.nw_mean(v, lag)
    return {"mean": float(m["mean"]), "t": float(m["t"]), "n": int(m["n"])}


def daily_ic(df: pd.DataFrame, score: str, outcome: str) -> pd.Series:
    sub = df[["date", score, outcome]].dropna()
    g = sub.groupby("date")
    x = g[score].rank(pct=True)
    y = g[outcome].rank(pct=True)
    x = x - x.groupby(sub["date"]).transform("mean")
    y = y - y.groupby(sub["date"]).transform("mean")
    t = pd.DataFrame({"date": sub["date"], "xy": x * y, "xx": x * x, "yy": y * y})
    s = t.groupby("date").sum()
    n = sub.groupby("date").size()
    ic = s["xy"] / np.sqrt(s["xx"] * s["yy"])
    return ic[n >= MIN_STOCKS]


def decile_spread(df: pd.DataFrame, score: str, outcome: str) -> pd.DataFrame:
    sub = df[["date", score, outcome]].dropna()
    q = sub.groupby("date")[score].rank(pct=True)
    top = sub[q >= 0.9].groupby("date")[outcome].mean()
    bot = sub[q <= 0.1].groupby("date")[outcome].mean()
    allm = sub.groupby("date")[outcome].mean()
    n = sub.groupby("date").size()
    out = pd.DataFrame({"top": top, "bot": bot, "all": allm, "n": n}).dropna()
    return out[out["n"] >= MIN_STOCKS]


def load(columns, filt=None) -> pd.DataFrame:
    return ds.dataset(PANEL).to_table(columns=columns, filter=filt).to_pandas(strings_to_categorical=True)


def market_regime() -> pd.DataFrame:
    m = pd.read_parquet(INDEX_SIGNALS / "SPY_macro_fear.parquet", columns=["date", "state", "panic"])
    m["date"] = m["date"].str.replace("-", "").astype(np.int32)
    return m.rename(columns={"state": "spy_state", "panic": "spy_panic"})


def entries(df: pd.DataFrame, code_min: int) -> np.ndarray:
    st = df["state"].to_numpy()
    sym = df["sym"]
    same = (sym.cat.codes if hasattr(sym, "cat") else pd.factorize(sym)[0])
    same = np.asarray(same)
    prev_st = np.concatenate([[0], st[:-1]])
    prev_sym = np.concatenate([[-1], same[:-1]])
    return (st >= code_min) & ((prev_st < code_min) | (prev_sym != same))


def event_block(ev: pd.DataFrame, outcome: str) -> dict:
    v = ev[outcome].to_numpy(float)
    month = (ev["date"] // 100).to_numpy()
    m, lo, hi = su.cluster_bootstrap_mean(v, month, B=1500)
    ok = np.isfinite(v)
    return {"n": int(ok.sum()), "months": int(len(np.unique(month[ok]))), "mean": m, "ci95": [lo, hi],
            "hit": float(np.mean(v[ok] > 0)) if ok.any() else None}


def main() -> int:
    out: dict = {}
    # ------------------------------------------------------------------ 1. beta (US dashboard universe)
    cols = ["date", "sym", "us", "dash", "member", "panic", "state", "x21", "x63", "resid21", "resid63", "spread"]
    df = load(cols, ds.field("us") & (ds.field("date") >= 19760101))
    print("loaded", len(df), flush=True)
    dash = df[df["dash"]]
    beta_block = {}
    for o, h in (("x21", 21), ("resid21", 21), ("x63", 63), ("resid63", 63)):
        ic = daily_ic(dash, "panic", o)
        beta_block[f"ic_panic_{o}"] = {**nw(ic.to_numpy(), h),
                                       "since_2010": nw(ic[ic.index >= 20100101].to_numpy(), h)}
        sp = decile_spread(dash, "panic", o)
        beta_block[f"spread_panic_{o}"] = {**nw((sp["top"] - sp["bot"]).to_numpy(), h),
                                           "top_minus_all": nw((sp["top"] - sp["all"]).to_numpy(), h)}
    # events by market regime, raw vs residual
    reg = market_regime()
    dash = dash.sort_values(["sym", "date"]).reset_index(drop=True)
    ev_mask = entries(dash, 2)
    ev = dash[ev_mask].merge(reg, on="date", how="left")
    by = {}
    for name, m in {"spy_calm": ev["spy_state"] == 0, "spy_stress_building": ev["spy_state"] == 1,
                    "spy_panic_or_worse": ev["spy_state"] >= 2, "all": np.ones(len(ev), bool)}.items():
        blk = ev[m]
        by[name] = {"x63": event_block(blk, "x63"), "resid63": event_block(blk, "resid63")}
    beta_block["panic_entries_by_market"] = by
    out["beta"] = beta_block
    print("beta done", flush=True)

    # ------------------------------------------------------------------ 2. PIT S&P 500 (2007-2026)
    pit = df[(df["date"] >= PIT_START) & df["member"]]
    dsame = df[(df["date"] >= PIT_START) & df["dash"]]
    mem = pd.read_parquet(MEMBERSHIP)
    pit_block = {"rows": int(len(pit)), "stocks": int(pit["sym"].nunique())}
    # coverage: observable members per date vs members on the books
    dates = np.sort(pit["date"].unique())
    obs = pit.groupby("date")["sym"].nunique()
    mem = mem.copy()
    def _d(col, default):
        v = mem[col].astype("object").where(mem[col].notna(), default)
        v = v.where(~v.isin(["None", "NaT", "nan", ""]), default)
        return v.astype(str).str.replace("-", "").str[:8].astype(int)

    mem["s"] = _d("start", "1900-01-01")
    mem["e"] = _d("end", "2100-01-01")
    sample_dates = dates[:: max(1, len(dates) // 240)]
    cov_rows = []
    for d in sample_dates:
        on = mem[(mem["s"] <= d) & (mem["e"] > d)]
        cov_rows.append({"date": int(d), "members": int(len(on)), "observed": int(obs.get(d, 0)),
                         "missing_acquired": int(((on["coverage"].str.startswith("missing")) & (on["reason_class"] == "acquired")).sum()),
                         "missing_distress": int(((on["coverage"].str.startswith("missing")) & (on["reason_class"] == "distress")).sum()),
                         "missing_other": int(((on["coverage"].str.startswith("missing")) & (~on["reason_class"].isin(["acquired", "distress"]))).sum())})
    cov = pd.DataFrame(cov_rows)
    pit_block["coverage"] = {"mean_members": float(cov["members"].mean()), "mean_observed": float(cov["observed"].mean()),
                             "mean_share_observed": float((cov["observed"] / cov["members"]).mean()),
                             "mean_missing_acquired": float(cov["missing_acquired"].mean()),
                             "mean_missing_distress": float(cov["missing_distress"].mean()),
                             "mean_missing_other": float(cov["missing_other"].mean())}
    for label, frame in (("pit_members", pit), ("dashboard_same_period", dsame)):
        blk = {}
        for o, h in (("x21", 21), ("resid21", 21), ("x63", 63), ("resid63", 63)):
            ic = daily_ic(frame, "panic", o)
            sp = decile_spread(frame, "panic", o)
            blk[o] = {"ic": nw(ic.to_numpy(), h), "spread": nw((sp["top"] - sp["bot"]).to_numpy(), h),
                      "top_minus_all": nw((sp["top"] - sp["all"]).to_numpy(), h), "dates": int(len(sp))}
        frame = frame.sort_values(["sym", "date"]).reset_index(drop=True)
        evp = frame[entries(frame, 2)].merge(reg, on="date", how="left")
        blk["panic_entries"] = {"all": event_block(evp, "resid63"),
                                "spy_calm": event_block(evp[evp["spy_state"] == 0], "resid63"),
                                "spy_panic_or_worse": event_block(evp[evp["spy_state"] >= 2], "resid63")}
        pit_block[label] = blk
    out["pit"] = pit_block
    print("pit done", flush=True)

    # ------------------------------------------------------------------ 3. survivorship break-even (PIT, 63d)
    sp = decile_spread(pit, "panic", "x63")
    spread = float((sp["top"] - sp["bot"]).mean())
    n_top = float(pit.assign(q=pit.groupby("date")["panic"].rank(pct=True)).query("q >= 0.9").shape[0])
    top_mean = float(sp["top"].mean())
    fail_return = float(np.log(0.25))  # a failure: -75% over 63 sessions
    # k extra top-decile observations at fail_return lower the top-decile mean to the bottom-decile mean when
    # (n_top*top + k*R)/(n_top+k) = bottom  ->  k = n_top*(top-bottom)/(bottom-R)
    bottom_mean = float(sp["bot"].mean())
    k_star = n_top * (top_mean - bottom_mean) / (bottom_mean - fail_return) if bottom_mean > fail_return else None
    distress = mem[(mem["status"] == "removed") & (mem["reason_class"] == "distress") & (mem["e"] >= PIT_START)]
    missing_distress = distress[distress["coverage"].str.startswith("missing")]
    out["survivorship_bound"] = {
        "pit_top_minus_bottom_x63": spread, "pit_top_decile_obs": n_top, "assumed_failure_log_return_63d": fail_return,
        "failure_obs_needed_to_erase_spread": k_star,
        "failure_member_days_equivalent": None if k_star is None else k_star,
        "missing_distress_names_2007_2026": missing_distress[["ticker", "name", "end", "reason"]].to_dict("records"),
        "max_plausible_failure_obs": int(len(missing_distress) * 63),
        "note": "Each missing failure could add at most ~63 top-decile stock-days before it vanished.",
    }
    print("bound done", flush=True)

    # ------------------------------------------------------------------ 4. costs
    cost = {}
    for label, frame in (("dashboard_us_1990_2026", dash[dash["date"] >= 19900101]), ("pit_members_2007_2026", pit)):
        frame = frame[["date", "sym", "panic", "x21", "spread"]].dropna(subset=["panic"])
        dates = np.sort(frame["date"].unique())
        reb = dates[::21]
        prev_top, prev_bot = set(), set()
        rows = []
        for d in reb:
            day = frame[frame["date"] == d].dropna(subset=["x21"])
            if len(day) < MIN_STOCKS:
                continue
            q = day["panic"].rank(pct=True)
            top = day[q >= 0.9]
            bot = day[q <= 0.1]
            gross_ls = float(np.expm1(top["x21"]).mean() - np.expm1(bot["x21"]).mean())
            gross_lo = float(np.expm1(top["x21"]).mean() - np.expm1(day["x21"]).mean())
            t_new = set(top["sym"]) - prev_top
            b_new = set(bot["sym"]) - prev_bot
            turn_t = len(t_new) / max(1, len(top))
            turn_b = len(b_new) / max(1, len(bot))
            sp_t = float(np.nanmean(top["spread"])) + COMMISSION_RT
            sp_b = float(np.nanmean(bot["spread"])) + COMMISSION_RT
            rows.append({"date": int(d), "gross_ls": gross_ls, "cost_ls": turn_t * sp_t + turn_b * sp_b,
                         "gross_lo": gross_lo, "cost_lo": turn_t * sp_t, "turn_t": turn_t, "spread_top": sp_t})
            prev_top, prev_bot = set(top["sym"]), set(bot["sym"])
        r = pd.DataFrame(rows)
        r["net_ls"] = r["gross_ls"] - r["cost_ls"]
        r["net_lo"] = r["gross_lo"] - r["cost_lo"]
        cost[label] = {
            "periods": int(len(r)),
            "long_short_gross_per_21d": nw(r["gross_ls"].to_numpy(), 1), "long_short_net_per_21d": nw(r["net_ls"].to_numpy(), 1),
            "long_short_net_annualized": float(r["net_ls"].mean() * 12),
            "top_decile_vs_universe_gross_per_21d": nw(r["gross_lo"].to_numpy(), 1),
            "top_decile_vs_universe_net_per_21d": nw(r["net_lo"].to_numpy(), 1),
            "mean_turnover_top": float(r["turn_t"].mean()), "mean_roundtrip_cost_top": float(r["spread_top"].mean()),
            "net_since_2010_ls": nw(r.loc[r["date"] >= 20100101, "net_ls"].to_numpy(), 1),
        }
    # event strategy: buy at panic entry, hold 21 / 63, residual return net of one round trip
    ev2 = ev.dropna(subset=["resid21"])
    rt = ev2["spread"].fillna(ev2["spread"].median()) + COMMISSION_RT
    cost["panic_entry_trade"] = {
        "events": int(len(ev2)), "mean_roundtrip_cost": float(rt.mean()),
        "resid21_gross": event_block(ev2, "resid21"),
        "resid21_net_mean": float(np.nanmean(np.expm1(ev2["resid21"]) - rt)),
        "resid63_net_mean": float(np.nanmean(np.expm1(ev2["resid63"]) - rt)),
    }
    out["costs"] = cost
    (RESULTS / "phase5_results.json").write_text(json.dumps(out, indent=1, default=float))
    print(json.dumps({k: (v if k != "pit" else {kk: vv for kk, vv in v.items() if kk in ("rows", "stocks", "coverage")}) for k, v in out.items() if k != "beta"}, indent=1, default=float)[:6000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
