#!/usr/bin/env python3
"""Unit-style self-tests for grade.py on a small synthetic fixture (stdlib unittest).
Run: python3 test_grade.py   (never touches the real eval store; builds a temp dir)."""
import io, json, os, shutil, sys, tempfile, unittest, contextlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import grade  # noqa: E402
import warnings
warnings.simplefilter("ignore", ResourceWarning)

HERE = os.path.dirname(os.path.abspath(__file__))


def row(t, as_of, close, rsi=50, sz=0.0, tz=0.0, cmf=0.0, rvol=1.0, p50=0.0, direction="stable",
        state="normal", bench="SPY", beta=1.0, mm5=0.0, r5=None):
    return {"ticker": t, "as_of": as_of, "benchmark": bench, "data_quality": "ready",
            "latest": {"close": close}, "scores": {"stretch_z": sz, "trend_z": tz},
            "measures": {"return_5d_pct": r5},
            "context": {"beta_252d": beta, "market_move_5d_pct": mm5},
            "setup": {"direction": direction, "indicators": {"rsi_14": rsi, "chaikin_money_flow_20d": cmf,
                                                             "relative_volume_20d": rvol, "price_vs_50d_pct": p50}},
            "capitulation": {"state": state}}


# sessions: base 2026-11-02 (Mon) ... +5 = 2026-11-09 (Mon)
DAYS = ["2026-11-02", "2026-11-03", "2026-11-04", "2026-11-05", "2026-11-06", "2026-11-09"]
SPY = [100, 100.5, 101, 101, 101.5, 102]           # +2.0%
CAPW = [10, 10.2, 10.5, 10.6, 10.8, 11.0]          # +10%  -> beats SPY (pass)
CAPL = [10, 9.9, 9.8, 9.7, 9.6, 9.5]               # -5%   -> fail
OBX = [50, 50, 50, 50, 50, 50.5]                   # +1%   trails SPY -> overbought pass
BRK = [20, 20.4, 20.6, 20.1, 20.0, 20.2]


class Fixture:
    def __init__(self):
        self.d = tempfile.mkdtemp(prefix="ta_eval_fixture_")
        os.makedirs(os.path.join(self.d, "tape_snapshots"))
        shutil.copy(os.path.join(HERE, "grading_spec.json"), self.d)
        for i, day in enumerate(DAYS):
            snap_date = grade.add_sessions(day, 1, "nyse")  # snapshot written the next morning
            rows = {
                "SPY": row("SPY", day, SPY[i]),
                "CAPW": row("CAPW", day, CAPW[i], rsi=20 if i < 2 else 40, state="capitulation_candidate" if i < 2 else "normal"),
                "CAPL": row("CAPL", day, CAPL[i], rsi=22, state="panic"),
                "OBX": row("OBX", day, OBX[i], rsi=80 if i < 2 else 65),
                "BRK": row("BRK", day, BRK[i], direction="leading_uptrend", p50=[3, 2, 1, -0.5, 1, 1][i], rvol=1.5, cmf=0.2),
                "ZUP": row("ZUP", day, 30 + i, sz=2.5 if i < 2 else 1.0),
                "STALE": row("STALE", "2026-11-02", 5.0),
            }
            for k in range(25):
                rows[f"B{k:02d}"] = row(f"B{k:02d}", day, 10 + (k % 5 - 2) * 0.1 * i, p50=1.0)
            if day == "2026-11-03":
                del rows["CAPL"]  # gap in storage for CAPL at session 1
            json.dump({"rows": rows, "feed_as_of": day}, open(os.path.join(self.d, "tape_snapshots", snap_date + ".json"), "w"))
        legacy = {"run_date": "2026-10-20", "ticker": "OLD", "kind": "tape", "flag": "RSI 20.0", "source": None,
                  "verdict": "agree", "verdict_by": "drew", "drew_verdict": "keep", "graded_on": "2026-10-21", "grade": "held"}
        with open(os.path.join(self.d, "run_log.jsonl"), "w") as f:
            f.write(json.dumps(legacy) + "\n")
        json.dump({"checked_through": "2026-12-20", "announcements": [
            {"provider": "S&P DJI", "index": "sp600", "ticker": "IDXA", "action": "add", "announced_on": "2026-12-04"},
            {"provider": "FTSE Russell", "index": "russell_2000", "ticker": "IDXM", "action": "add", "announced_on": "2026-11-20"}]},
            open(os.path.join(self.d, "index_announcements.json"), "w"))
        self.cand = {"run_date": "2026-11-03", "source": "dashboard/data/technical_summary.json", "flags": [
            {"ticker": "CAPW", "kind": "tape", "flag": "capitulation_candidate RSI 20.0", "lens_rules": ["TAPE-05"]},
            {"ticker": "CAPL", "kind": "tape", "flag": "panic RSI 22.0", "lens_rules": ["M5"]},
            {"ticker": "OBX", "kind": "tape", "flag": "RSI 80.0"},
            {"ticker": "BRK", "kind": "tape", "flag": "breakout CMF 0.200"},
            {"ticker": "ZUP", "kind": "tape", "flag": "stretch_z 2.50"},
            {"ticker": "IDXA", "kind": "index", "flag": "S&P 600 inclusion_candidate -3.0%"},
            {"ticker": "IDXB", "kind": "index", "flag": "S&P 400 inclusion_candidate -1.0%"},
            {"ticker": "IDXM", "kind": "index", "flag": "Russell 1000 deletion_risk -20%"}],
            "held": [{"ticker": "STALE", "reason": "stale row", "counterfactual_flag": "RSI 20.0"},
                     {"ticker": "NOROW", "reason": "thin"}],
            "baseline": {"n": 20}}

    def run(self, *args):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            grade.main(["--eval-dir", self.d] + list(args))
        return buf.getvalue()

    def log(self):
        return grade.read_log(os.path.join(self.d, "run_log.jsonl"))

    def by(self, t):
        return next(r for r in self.log() if r["ticker"] == t)


class GradeTests(unittest.TestCase):
    def setUp(self):
        self.f = Fixture()
        json.dump(self.f.cand, open(os.path.join(self.f.d, "cand.json"), "w"))

    def tearDown(self):
        shutil.rmtree(self.f.d, ignore_errors=True)

    def test_calendar(self):
        self.assertEqual(grade.add_sessions("2026-11-24", 3, "nyse"), "2026-11-30")  # skips Thanksgiving + weekend
        self.assertEqual(grade.add_sessions("2026-11-02", 5, "nyse"), "2026-11-09")

    def test_classify(self):
        self.assertEqual(grade.classify("panic RSI 18.3", "tape")[0], "capitulation")
        self.assertEqual(grade.classify("RSI 81.4", "tape")[0], "rsi_overbought")
        self.assertEqual(grade.classify("RSI 29.0", "tape")[0], "rsi_oversold")
        self.assertEqual(grade.classify("breakout lost CMF 0.061", "tape")[0], "breakout_lost")
        self.assertEqual(grade.classify("trend_z -1.68 (stress_building)", "tape")[1]["direction"], -1)
        self.assertEqual(grade.classify("sp600 watch removed, liquidity 0.992", "tape")[0], "index_watch_removed")
        self.assertEqual(grade.classify("Russell 1000 deletion_risk -42.22%", "index")[0], "index_migration")

    def test_register_idempotent_and_count(self):
        out = self.f.run("--register", os.path.join(self.f.d, "cand.json"), "--today", "2026-11-03")
        self.assertEqual(out.strip().splitlines()[-1], "8")
        n1 = len(self.f.log())
        self.f.run("--register", os.path.join(self.f.d, "cand.json"), "--today", "2026-11-03")
        self.assertEqual(len(self.f.log()), n1)
        bl = [r for r in self.f.log() if r.get("cohort") == "baseline"]
        self.assertEqual(len(bl), 20)
        self.assertFalse({r["ticker"] for r in bl} & {"CAPW", "CAPL", "OBX", "BRK", "ZUP", "STALE", "SPY"})
        r = self.f.by("CAPW")
        self.assertEqual((r["test_id"], r["base_as_of"], r["window_end_as_of"]), ("TA-CAP-5D", "2026-11-02", "2026-11-09"))
        self.assertFalse(r["registered_retro"])

    def test_daily_grades_and_never_regrades(self):
        self.f.run("--register", os.path.join(self.f.d, "cand.json"), "--today", "2026-11-03")
        self.f.run("--daily", "--today", "2026-11-10")
        g = {r["ticker"]: r for r in self.f.log()}
        self.assertEqual(g["CAPW"]["test_grade"], "pass")
        self.assertAlmostEqual(g["CAPW"]["test_numbers"]["excess_return_pct"], 8.0, places=3)
        self.assertEqual(g["CAPW"]["test_numbers"]["bench_method"], "SPY_row_closes")
        self.assertEqual(g["CAPL"]["test_grade"], "fail")
        self.assertEqual(g["CAPL"]["persistence_grade"], "no_data")      # session-1 row missing
        self.assertEqual(g["OBX"]["test_grade"], "pass")
        self.assertEqual(g["OBX"]["persistence_grade"], "held")
        self.assertEqual(g["BRK"]["test_grade"], "fail")                  # session 3 below 50d
        self.assertEqual(g["ZUP"]["test_grade"], "pass")                  # persists + positive return
        self.assertEqual(g["IDXA"]["test_grade"], "pass")
        self.assertIsNone(g["IDXB"].get("test_grade"))                    # deadline not reached yet
        self.assertEqual(g["STALE"]["test_grade"], "no_data")             # stale row never stands in
        self.assertEqual(g["NOROW"]["flag_kind"], "unknown_no_snapshot_row")
        # legacy row untouched
        self.assertEqual((g["OLD"]["grade"], g["OLD"]["verdict"], g["OLD"]["drew_verdict"]), ("held", "agree", "keep"))
        self.assertNotIn("test_grade", g["OLD"])
        # never regrade: tamper with a number, rerun, value must stay
        rows = self.f.log()
        for r in rows:
            if r["ticker"] == "CAPW":
                r["test_grade"] = "fail"
        grade.write_log(os.path.join(self.f.d, "run_log.jsonl"), rows)
        self.f.run("--daily", "--today", "2026-12-21")
        g = {r["ticker"]: r for r in self.f.log()}
        self.assertEqual(g["CAPW"]["test_grade"], "fail")
        self.assertEqual(g["IDXB"]["test_grade"], "fail")                 # window closed without announcement
        self.assertEqual(g["IDXM"]["test_grade"], "pass")                 # migration matched via russell_2000 add
        bl = [r for r in self.f.log() if r.get("cohort") == "baseline"]
        self.assertTrue(all(r.get("baseline_grades") for r in bl))

    def test_implied_spy_fallback_and_retro(self):
        # drop SPY from snapshots, give rows a stored beta-scaled market move -> implied SPY
        for fn in os.listdir(os.path.join(self.f.d, "tape_snapshots")):
            p = os.path.join(self.f.d, "tape_snapshots", fn)
            d = json.load(open(p))
            d["rows"].pop("SPY")
            for r in d["rows"].values():
                r["context"]["beta_252d"], r["context"]["market_move_5d_pct"] = 1.5, 3.0  # implied SPY +2.0%
            json.dump(d, open(p, "w"))
        self.f.run("--register", os.path.join(self.f.d, "cand.json"), "--retro", "--today", "2026-11-12")
        self.f.run("--daily", "--today", "2026-11-12")
        r = self.f.by("CAPW")
        self.assertTrue(r["registered_retro"])
        self.assertEqual(r["test_numbers"]["bench_method"], "implied_spy_median_market_move_over_beta")
        self.assertEqual(r["test_grade"], "pass")

    def test_report(self):
        self.f.run("--register", os.path.join(self.f.d, "cand.json"), "--today", "2026-11-03")
        self.f.run("--daily", "--today", "2026-11-10")
        out = os.path.join(self.f.d, "rep.json")
        self.f.run("--report", "--out", out, "--today", "2026-11-10")
        rep = json.load(open(out))
        self.assertIn("TAPE-05", rep["by_rule"])          # M5 alias normalized
        self.assertEqual(rep["by_rule"]["TAPE-05"]["live"]["graded_n"], 2)
        self.assertIsNotNone(rep["by_flag_kind"]["capitulation"]["live"]["baseline_pass_rate"])
        self.assertFalse(rep["by_rule"]["TAPE-05"]["under_review_candidate"])  # n < 20


if __name__ == "__main__":
    unittest.main(verbosity=2)
