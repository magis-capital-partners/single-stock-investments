"""Report sections for phases 5-7 (survivorship/beta/costs, live tracking, recalibration).

Imported by report.py; every number is read from results/*.json.
"""
from __future__ import annotations

import json

from common import RESULTS, SCRIPTS


def _load(name: str, base=RESULTS):
    try:
        return json.loads((base / name).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


P5 = _load("phase5_results.json")
P5U = _load("phase5_universe.json")
L7 = _load("phase7_labels.json")
S7 = _load("phase7_stock.json")
LD7 = _load("phase7_ladder.json")
RD7 = _load("phase7_rebound_diagnostics.json")
EXP = _load("technical_signal_expectations.json", SCRIPTS)


def build_sections(esc, pct, num, tstat, table_html, figure, grouped_columns, legend) -> str:
    def p(x, d=1, sign=True):
        return pct(x, d, sign)

    def ici(v):
        if not v or v.get("mean") is None:
            return "–"
        return f"{num(v['mean'])} ({tstat(v['t'])})"

    parts = []
    # ------------------------------------------------------------------ phase 5
    if P5:
        b = P5["beta"]
        pit = P5["pit"]
        cov = pit["coverage"]
        bound = P5["survivorship_bound"]
        costs = P5["costs"]
        ent = b["panic_entries_by_market"]
        beta_rows = [
            ["Daily rank IC, 21 sessions", ici(b["ic_panic_x21"]), ici(b["ic_panic_resid21"]), ici(b["ic_panic_resid21"]["since_2010"])],
            ["Daily rank IC, 63 sessions", ici(b["ic_panic_x63"]), ici(b["ic_panic_resid63"]), ici(b["ic_panic_resid63"]["since_2010"])],
            ["Top − bottom decile, 21 sessions", ici(b["spread_panic_x21"]), ici(b["spread_panic_resid21"]), "–"],
            ["Panic entries, SPY calm (63 sessions)", p(ent["spy_calm"]["x63"]["mean"], 2), p(ent["spy_calm"]["resid63"]["mean"], 2), "–"],
            ["Panic entries, SPY in panic (63 sessions)", p(ent["spy_panic_or_worse"]["x63"]["mean"], 2), p(ent["spy_panic_or_worse"]["resid63"]["mean"], 2), "–"],
        ]
        pm = pit["pit_members"]
        ds_ = pit["dashboard_same_period"]
        pit_rows = [
            ["Daily rank IC vs beta-adjusted 21 sessions", ici(pm["resid21"]["ic"]), ici(ds_["resid21"]["ic"])],
            ["Daily rank IC vs beta-adjusted 63 sessions", ici(pm["resid63"]["ic"]), ici(ds_["resid63"]["ic"])],
            ["Top − bottom decile, 63 sessions (beta-adj.)", ici(pm["resid63"]["spread"]), ici(ds_["resid63"]["spread"])],
            ["Panic entries → 63 sessions (beta-adj.), all", p(pm["panic_entries"]["all"]["mean"], 2), p(ds_["panic_entries"]["all"]["mean"], 2)],
            ["… when SPY was calm", f"{p(pm['panic_entries']['spy_calm']['mean'], 2)} [{p(pm['panic_entries']['spy_calm']['ci95'][0], 1)}, {p(pm['panic_entries']['spy_calm']['ci95'][1], 1)}]",
             f"{p(ds_['panic_entries']['spy_calm']['mean'], 2)} [{p(ds_['panic_entries']['spy_calm']['ci95'][0], 1)}, {p(ds_['panic_entries']['spy_calm']['ci95'][1], 1)}]"],
        ]
        cost_rows = []
        for label, key in (("Dashboard US stocks, 1990–2026", "dashboard_us_1990_2026"), ("Point-in-time S&P 500, 2007–2026", "pit_members_2007_2026")):
            c = costs[key]
            cost_rows.append([esc(label), ici(c["long_short_gross_per_21d"]), ici(c["long_short_net_per_21d"]), p(c["long_short_net_annualized"], 1),
                              ici(c["top_decile_vs_universe_net_per_21d"]), p(c["mean_roundtrip_cost_top"], 2, False)])
        removed = {}
        for row in (P5U or {}).get("removed_by_reason_and_coverage", []):
            removed.setdefault(row["reason_class"], {})[row["coverage"]] = row["n"]
        cov_rows = [[esc(k.replace("_", " ")), str(sum(v.values())), str(v.get("ok", 0) + v.get("reused_or_late", 0)),
                     str(v.get("missing_error", 0) + v.get("missing_single_bar", 0))] for k, v in removed.items()]
        parts.append(f"""<section id="phase5">
  <h2>Phase 5 · Survivorship, beta and trading costs</h2>
  <p>Three checks on whether the small positive stock-level effect survives contact with reality.</p>
  <h3>Beta-adjusted returns</h3>
  <p>Excess returns against SPY reward high-beta stocks in every rebound. Re-measured as each stock’s return minus its own point-in-time beta times SPY’s, the cross-sectional effect barely moves, so it is not a beta artifact. It is small and has nearly halved since 2010.</p>
  {table_html(["Panic score", "Excess vs SPY", "Beta-adjusted", "Beta-adjusted since 2010"], beta_rows)}
  <h3>A point-in-time S&amp;P 500 instead of today’s dashboard</h3>
  <p>Index membership on every date since 2007 was rebuilt from Wikipedia’s dated change log (the repo already scrapes the current list). Every former member that still trades was added: {P5U['fetched_new'] if P5U else '–'} histories, with reused tickers rejected by date coverage. On an average day {p(cov['mean_share_observed'], 0, False)} of the {cov['mean_members']:.0f} members are observable. The rest are mostly acquired companies ({cov['mean_missing_acquired']:.0f} on an average day) and a few failures ({cov['mean_missing_distress']:.1f}).</p>
  {table_html(["2007–2026", "Point-in-time S&P 500", "Dashboard, same period"], pit_rows)}
  <p>In large caps since 2007 the cross-sectional effect is weak (IC about 0.016). Buying a stock as it <em>enters</em> panic was followed by beta-adjusted <strong>underperformance</strong>, significantly so when the panic was company-specific and the market calm.</p>
  <h3>How many unseen failures would it take?</h3>
  <p>Yahoo cannot serve dead companies, so the survivorship gap was bounded instead of filled. Erasing the point-in-time top-minus-bottom spread ({p(bound['pit_top_minus_bottom_x63'], 2)} over 63 sessions) would need about {bound['failure_obs_needed_to_erase_spread']:,.0f} top-decile stock-days that each lost 75%. The failures actually missing since 2007 ({', '.join(esc(r['ticker']) for r in bound['missing_distress_names_2007_2026'])}) can contribute at most about {bound['max_plausible_failure_obs']}. Survivorship cannot have produced the edge. Removing it would only make a weak result weaker.</p>
  {table_html(["Removed from the index (since 1976, dense from 2007)", "Names", "Still on Yahoo", "Missing (dead or renamed)"], cov_rows)}
  <h3>After trading costs</h3>
  <p>Round-trip costs use the Abdi–Ranaldo effective spread estimated from each stock’s own daily high, low and close, plus 2bp commission, and are charged on actual turnover at 21-session rebalances.</p>
  {table_html(["Panic decile strategy", "Long–short gross / 21 sessions", "Net", "Net per year", "Top decile vs universe, net", "Round trip"], cost_rows)}
  <p class="aside">Ready for real survivorship-free data: <code>vendor_bars.py</code> loads any vendor’s delisted histories (Norgate, Sharadar, CRSP or EODHD exports), including CRSP-style delisting returns. It is tested on a synthetic bankruptcy. Run <code>python vendor_bars.py --vendor-dir …</code>, then the normal pipeline.</p>
</section>""")
    # ------------------------------------------------------------------ phase 6
    if EXP:
        bands = EXP["groups"]["recent"]["risk_band"]
        band_rows = [[esc(k), f"{v['n']:,}", p(v.get("mean_predicted_p_drop15"), 0, False), p(v["p_drop15_63d"], 0, False), p(v["realized_vol21"], 0, False)]
                     for k, v in sorted(bands.items(), key=lambda kv: kv[1].get("mean_predicted_p_drop15") or 0)]
        parts.append(f"""<section id="phase6">
  <h2>Phase 6 · A live track record on the dashboard</h2>
  <p>The only fully honest test is forward. A new step in the nightly technicals job (<code>build_signal_track_record.py</code>) now does three things:</p>
  <ul>
    <li><strong>Logs</strong> every published stock signal, ladder row and SPY market read to a monthly ledger (<code>_system/data/signal_track_record/ledger/</code>). The first write wins, so the ledger is what was actually published. Rows from a session that has not closed are skipped, so a mid-day rerun cannot lock in a partial bar.</li>
    <li><strong>Grades</strong> each row as its 5/21/63-session outcomes mature. Grading uses each ticker’s own adjusted history, so splits and dividends cannot fake a return, and stale snapshots are never graded.</li>
    <li><strong>Publishes</strong> the record next to this study’s backtest expectation for the same signal, so every label on the page carries its own track record.</li>
  </ul>
  <p>The risk page’s ladder now shows, for each rung, what it has been followed by since 1993 and since 2018, beside its live results. Each stock panel states what its current setup has historically meant and what this stock’s own history says about the fear score. The ledger was seeded with the snapshots published on 30 Sep and 1 Oct 2026. 21-session grades start arriving in early November.</p>
  {table_html(["Drop-risk band (2018–2026)", "Stock-days", "Predicted P(another 15% drop)", "Observed", "Next-month vol"], band_rows)}
</section>""")
    # ------------------------------------------------------------------ phase 7
    if L7 and S7:
        lab = L7["labels"]
        base = L7["baseline"]
        lrows = []
        for key, label in (("stabilizing", "“Stabilizing” (v2, ungated)"), ("stabilizing_gated", "“Stabilizing”, gated on real stress"),
                           ("falling_knife", "“Falling knife” (v2)"), ("market_selloff", "Market-driven selloff (v3)"),
                           ("company_selloff", "Company-specific selloff (v3)")):
            r = lab[key]
            cells = [esc(label), p(r["share_of_days"], 0, False)]
            for split in ("train", "valid", "holdout"):
                e = r[split]["entries"]
                cells.append(f"{p(e['resid63'] - base[split]['resid63'], 2)}")
            lrows.append(cells)
        ret = S7["returns"]
        rrows = []
        for key, label in (("panic", "Panic (current)"), ("reversal_5d", "Last 5 days’ loss"), ("ridge21", "Risk-adjusted rank (ridge)"), ("gbr21", "Boosted trees")):
            r = ret[key]
            rrows.append([esc(label), ici(r["train"]["ic_resid21"]), ici(r["valid"]["ic_resid21"]), ici(r["holdout"]["ic_resid21"]), ici(r["holdout"]["ic_resid63"]),
                          ici(r["holdout"]["spread21"]["gross"])])
        risk = S7["risk"]
        krows = []
        for key, label in (("panic_only", "Panic alone"), ("rv_only", "Realized volatility alone"), ("full", "Calibrated model (v3)")):
            krows.append([esc(label), num(risk["holdout"][f"vol_r2_{key}"], 2, False), num(risk["holdout"][f"drop15_{key}"]["auc"], 3, False),
                          num(risk["holdout"][f"drop15_{key}"]["brier"], 4, False)])
        calib = risk["holdout"]["drop15_full"]["calibration"]
        calib_svg = grouped_columns([str(i + 1) for i in range(len(calib))],
                                    [("Predicted", "m1", [c["pred"] for c in calib], None, None, [f"Decile {i + 1}: predicted {p(c['pred'], 0, False)}" for i, c in enumerate(calib)]),
                                     ("Observed", "m2", [c["obs"] for c in calib], None, None, [f"Decile {i + 1}: observed {p(c['obs'], 0, False)} of {c['n']:,}" for i, c in enumerate(calib)])],
                                    width=760, height=240, fmt=lambda v: p(v, 0, False), label="drop-risk calibration, holdout")
        calib_fig = figure("Calibration of the new drop-risk forecast, 2018–2026 holdout",
                           "Stock-days sorted into tenths by predicted probability of another 15% drop within 63 sessions, against how often it happened.",
                           calib_svg, table_html(["Decile", "Predicted", "Observed", "Stock-days"], [[str(i + 1), p(c["pred"], 1, False), p(c["obs"], 1, False), f"{c['n']:,}"] for i, c in enumerate(calib)]),
                           legend_html=legend([("Predicted", "m1"), ("Observed", "m2")]))
        diag = RD7["ic"] if RD7 else None
        diag_rows = []
        if diag:
            for key, label in (("reb", "Risk-adjusted rank"), ("panic", "Panic")):
                d = diag[key]
                diag_rows.append([esc(label), f"{num(d['resid21']['ic'])} ({tstat(d['resid21']['t'])})", f"{num(d['x21']['ic'])} ({tstat(d['x21']['t'])})",
                                  f"{num(d['resid63']['ic'])} ({tstat(d['resid63']['t'])})", f"{num(d['x63']['ic'])} ({tstat(d['x63']['t'])})"])
        ladder_rows = []
        if LD7:
            for split, key in (("Design: S&P 500 1962–2006", "GSPC_1962_2006"), ("Test: SPY 2007–2026", "SPY_2007_2026")):
                res = LD7["design" if split.startswith("Design") else "test"][key]
                for cond, label in (("current:stress+", "Stress (current rule)"), ("current:candidate+", "Exhaustion candidate, current dwell"),
                                    ("fast_up:candidate+", "Exhaustion candidate, 1-session upgrade"), ("window:candidate+", "Exhaustion candidate, 2-of-3 rule")):
                    v = res[cond]
                    ladder_rows.append([esc(split), esc(label), str(v["entries"]), p(v["h63_entry"], 1) if v["h63_entry"] is not None else "–",
                                        p(v["dd_matched_h63"], 1) if v["dd_matched_h63"] is not None else "–"])
        breadth_rows = []
        if LD7:
            for label, key in (("Design 1993–2006", "design_1993_2006"), ("Test 2007–2026", "test_2007_2026")):
                res = LD7["breadth"][key]
                for cond in ("breadth>=0.25", "breadth>=0.50", "ladder_stress+", "vix>=30"):
                    v = res[cond]
                    breadth_rows.append([esc(label), esc(cond.replace(">=", " ≥ ").replace("breadth", "Share of stocks in panic").replace("ladder_stress+", "Ladder at stress+").replace("vix", "VIX")),
                                         str(v["days"]), p(v["h63_all_days_diff"], 1) if v["h63_all_days_diff"] is not None else "–", tstat(v["h63_t"]) if v["h63_t"] is not None else "–"])
        parts.append(f"""<section id="phase7">
  <h2>Phase 7 · Recalibration, judged on a holdout</h2>
  <p>Every candidate improvement was designed on 1990–2009, chosen on 2010–2017, and reported once on 2018–2026. Only changes that held up on the holdout reached the dashboard.</p>
  <h3>Labels: say what the evidence supports</h3>
  <p>Beta-adjusted 63-session return after entering each label, minus the baseline for the same period.</p>
  {table_html(["Label", "Share of days", "Train 1990–2009", "Validate 2010–17", "Holdout 2018–26"], lrows)}
  <p>Gating “stabilizing” on genuine stress did not rescue it: worse than the baseline in two of three periods, and riskier. Both v2 labels are retired. A stock in panic is now described by what drove the selloff, which is consistently informative in the right direction: market-driven selloffs beat company-specific ones in validation and holdout.</p>
  <h3>A better return ranking, and what it does not do</h3>
  {table_html(["Daily rank IC vs beta-adjusted return", "Train", "Validate", "Holdout 21d", "Holdout 63d", "Holdout top−bottom, 21d gross"], rrows)}
  <p>The ridge model uses panic’s own components plus reversal, momentum, beta, liquidity and the market’s state. It roughly triples panic’s holdout power on <em>beta-adjusted</em> returns. Its largest weight says stock fear matters most when the whole market is panicking. The boosted-tree version overfit its training years and was not used.</p>
  {table_html(["Holdout 2018–2026", "Beta-adj. 21d", "Raw vs SPY 21d", "Beta-adj. 63d", "Raw vs SPY 63d"], diag_rows)}
  <p><strong>It does not predict beating SPY.</strong> Against raw returns versus SPY its holdout IC is about 0.01 and not significant, the same as panic’s. It is largely a low-beta, low-volatility tilt: average beta runs from about 1.5 in its bottom tenth to 0.5 in its top tenth. The dashboard therefore calls it a <em>risk-adjusted rank</em> and says so. Its top-minus-bottom spread is also about the size of the round-trip cost, so it is a ranking aid, not a strategy.</p>
  <h3>Calibrated risk instead of a fear score</h3>
  {table_html(["Holdout 2018–2026", "Next-month volatility R²", "Another 15% drop: AUC", "Brier (climatology 0.181)"], krows)}
  {calib_fig}
  <h3>The index ladder: nothing to recalibrate</h3>
  <p>Daily-bar dwell rules that let the exhaustion rungs fire were tested on 1962–2006 and 2007–2026. None produced an edge over days at the same drawdown; most made it worse. The current rule stays, the exhaustion rungs are presented as description, and the stress rung, which held up out of sample, is labelled as the informative one. Capitulation breadth (the share of stocks in panic) looked strong in 1993–2006 but did not survive 2007–2026, so it is shown as context only.</p>
  {table_html(["Period", "Rule", "Entries", "SPY next 63 sessions", "vs same drawdown"], ladder_rows)}
  {table_html(["Period", "Signal", "Days", "63-session edge vs all days", "HAC t"], breadth_rows)}
</section>""")
    return "\n".join(parts)


V3_CHANGES = """<section id="v3">
  <h2>What changed on the dashboard (technical-fear-v3)</h2>
  <ul class="method">
    <li><strong>Labels.</strong> “Falling knife” and “stabilizing” are gone. A stock in panic is a <em>market-driven</em> or <em>company-specific</em> selloff, from a point-in-time beta split of its 20-session move. The copy states what each has historically been followed by.</li>
    <li><strong>Calibrated drop risk and expected volatility</strong> on every stock, in the stock panel and as a holdings column. Holdout AUC 0.66 vs 0.52 for panic; volatility R² 0.54 vs 0.47 for realized volatility.</li>
    <li><strong>Risk-adjusted rank</strong> for US stocks, labelled for what it predicts (beta-adjusted return) and what it doesn’t (beating SPY).</li>
    <li><strong>Track record</strong> beside every signal: backtest expectation plus a live record graded nightly.</li>
    <li><strong>Risk page.</strong> The ladder’s “LIVE” label now requires the intraday model. The per-stock model’s SPY read had been shown as the live ladder. Exhaustion is described honestly, and market panic breadth is shown as context.</li>
    <li>Panic, pressure and exhaustion are unchanged, so history stays comparable.</li>
  </ul>
</section>"""
