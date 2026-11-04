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
        self.assertEqual(g["CAPL"]["persistence_grade"], "held")         # session-1 row missing -> next stored close
        self.assertEqual(g["CAPL"]["persistence_numbers"]["sessions_elapsed"], 2)
        self.assertEqual(g["OBX"]["test_grade"], "pass")
        self.assertEqual(g["OBX"]["persistence_grade"], "held")
        self.assertEqual(g["BRK"]["test_grade"], "fail")                  # session 3 below 50d
        self.assertEqual(g["ZUP"]["test_grade"], "pass")                  # persists + positive return
        self.assertEqual(g["IDXA"]["test_grade"], "pass")
        self.assertIsNone(g["IDXB"].get("test_grade"))                    # deadline not reached yet
        self.assertIsNone(g["STALE"].get("test_grade"))                   # US frontier == window end: could still fill
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
        # a later US close lands without a STALE row for the window end -> now (and only now) no_data
        p = os.path.join(self.f.d, "tape_snapshots", "2026-11-11.json")
        with open(p, "w") as fh:
            json.dump({"rows": {"SPY": row("SPY", "2026-11-10", 102.5)}}, fh)
        self.f.run("--daily", "--today", "2026-12-22")
        self.assertIsNone(self.f.by("STALE").get("test_grade"))         # one session past end: may still fill (M/W/F)
        # US closes stored more than 10 sessions past the window end, still no STALE row -> no_data
        with open(os.path.join(self.f.d, "tape_snapshots", "2026-11-25.json"), "w") as fh:
            json.dump({"rows": {"SPY": row("SPY", "2026-11-24", 103.0)}}, fh)
        self.f.run("--daily", "--today", "2026-12-23")
        self.assertEqual(self.f.by("STALE")["test_grade"], "no_data")

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


def xrow(t, as_of, close, src=None, **kw):
    r = row(t, as_of, close, **kw)
    r["source"] = "yahoo:" + (src or t)
    return r


class MixedSessionRegression(unittest.TestCase):
    """Nov 2 2026 bug: overseas rows built mid-session (stamped with Monday's date) made --daily treat Monday's US
    session as closed and mark US calls no_data. A session is closed for a row only when that row's own exchange
    has a completed close stored; US rows never inherit closure from other markets."""

    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="ta_eval_mixed_")
        os.makedirs(os.path.join(self.d, "tape_snapshots"))
        shutil.copy(os.path.join(HERE, "grading_spec.json"), self.d)
        # base Mon 2026-11-02 -> end Mon 2026-11-09 (5 sessions)
        self.days = ["2026-11-02", "2026-11-03", "2026-11-04", "2026-11-05", "2026-11-06"]
        for i, day in enumerate(self.days):
            rows = {"SPY": xrow("SPY", day, 100 + i * 0.2), "USX": xrow("USX", day, 10 - i * 0.1, rsi=20),
                    "7203.T": xrow("7203.T", day, 3000 + 10 * i, bench="1321.T", mm5=1.0, beta=1.0, rsi=20),
                    "MC.PA": xrow("MC.PA", day, 600, bench="IEUR", mm5=1.0, beta=1.0, rsi=20),
                    "LSEG": xrow("LSEG", day, 90, src="LSEG.L", bench="IEUR", mm5=1.0, beta=1.0, rsi=20)}
            # evening build after the US close (22:12Z) -> every row's as_of is a completed close
            nxt = (grade.pdate(day) + grade.dt.timedelta(days=1)).isoformat()
            self.snap(nxt, rows, day + "T22:12:21Z")  # built that evening, filed under the next calendar day
        # Monday-morning build (10:34Z = 05:34 ET): US rows are Friday's close; Tokyo already closed Monday;
        # Paris and London are mid-session but stamped as_of Monday.
        self.morning_rows = {
            "SPY": xrow("SPY", "2026-11-06", 101.0), "USX": xrow("USX", "2026-11-06", 9.6, rsi=20),
            "7203.T": xrow("7203.T", "2026-11-09", 3100, bench="1321.T", mm5=1.0, beta=1.0, r5=3.3),
            "MC.PA": xrow("MC.PA", "2026-11-09", 610, bench="IEUR", mm5=1.0, beta=1.0),
            "LSEG": xrow("LSEG", "2026-11-09", 91, src="LSEG.L", bench="IEUR", mm5=1.0, beta=1.0)}
        self.snap("2026-11-09", self.morning_rows, "2026-11-09T10:34:41Z")
        legacy_wrong = {"run_date": "2026-11-03", "ticker": "OLDUS", "kind": "tape", "flag": "RSI 20.0",
                        "flag_kind": "rsi_oversold", "test_id": "TA-RSI-OS-5D", "test_window_sessions": 5,
                        "base_as_of": "2026-11-02", "window_end_as_of": "2026-11-09", "persistence_as_of": "2026-11-03",
                        "test_grade": "no_data", "test_graded_on": "2026-11-09",
                        "test_numbers": {"missing": "no stored row for OLDUS with as_of 2026-11-09"}, "drew_verdict": "keep"}
        legacy_ok = dict(legacy_wrong, ticker="OLDOK", test_grade="pass", test_numbers={"excess_return_pct": 1.0})
        with open(os.path.join(self.d, "run_log.jsonl"), "w") as f:
            for r in (legacy_wrong, legacy_ok):
                f.write(json.dumps(r) + "\n")
        cand = {"run_date": "2026-11-03", "flags": [
            {"ticker": "USX", "kind": "tape", "flag": "RSI 20.0"},
            {"ticker": "7203.T", "kind": "tape", "flag": "RSI 20.0"},
            {"ticker": "MC.PA", "kind": "tape", "flag": "RSI 20.0"},
            {"ticker": "LSEG", "kind": "tape", "flag": "RSI 20.0"}], "baseline": {"n": 0}}
        with open(os.path.join(self.d, "cand.json"), "w") as f:
            json.dump(cand, f)

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def snap(self, date, rows, gen):
        with open(os.path.join(self.d, "tape_snapshots", date + ".json"), "w") as f:
            json.dump({"rows": rows, "generated_at": gen}, f)

    def run_g(self, *a):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            grade.main(["--eval-dir", self.d] + list(a))
        return buf.getvalue()

    def rows(self):
        return {r["ticker"]: r for r in grade.read_log(os.path.join(self.d, "run_log.jsonl"))}

    def test_frontiers_are_per_exchange(self):
        tape = grade.Tape(self.d)
        self.assertEqual(tape.frontier["US"], "2026-11-06")          # Monday US close not stored yet
        self.assertEqual(tape.frontier["T"], "2026-11-09")           # Tokyo closed 06:30Z Monday
        self.assertEqual(tape.frontier["PA"], "2026-11-06")          # Paris mid-session row ignored
        self.assertEqual(tape.exchange_for("LSEG"), "L")             # exchange from the row's own symbol
        self.assertIsNone(tape.row("MC.PA", "2026-11-09"))
        self.assertIsNone(tape.row("LSEG", "2026-11-09"))
        self.assertIsNotNone(tape.row("7203.T", "2026-11-09"))
        self.assertEqual(grade.exchange_of({"source": "yahoo:BF-B"}, "BF.B"), "US")
        self.assertEqual(grade.exchange_of({}, "HEI.A"), "US")

    def test_morning_run_keeps_us_pending_and_reopens_premature_no_data(self):
        self.run_g("--register", os.path.join(self.d, "cand.json"), "--today", "2026-11-03")
        self.run_g("--daily", "--today", "2026-11-09")
        g = self.rows()
        self.assertIsNone(g["USX"].get("test_grade"))                 # was the bug: must not be no_data
        self.assertIsNone(g["MC.PA"].get("test_grade"))
        self.assertIsNone(g["LSEG"].get("test_grade"))
        self.assertIn(g["7203.T"]["test_grade"], ("pass", "fail"))    # Tokyo's own close is stored
        self.assertEqual(g["7203.T"]["test_numbers"]["end_resolution"]["exchange"], "T")
        # earlier premature no_data reopened with an audit trail; pass row and drew_verdict untouched
        self.assertIsNone(g["OLDUS"]["test_grade"])
        self.assertEqual(g["OLDUS"]["test_grade_superseded"][0]["grade"], "no_data")
        self.assertEqual(g["OLDUS"]["drew_verdict"], "keep")
        self.assertEqual(g["OLDOK"]["test_grade"], "pass")
        self.assertNotIn("test_grade_superseded", g["OLDOK"])
        # evening build lands Monday's closes -> US rows grade; OLDUS (no row at all, frontier == end) stays pending
        eve = {k: dict(v) for k, v in self.morning_rows.items()}
        eve["SPY"] = xrow("SPY", "2026-11-09", 101.5)
        eve["USX"] = xrow("USX", "2026-11-09", 9.9)
        eve["MC.PA"] = xrow("MC.PA", "2026-11-09", 612, bench="IEUR", mm5=1.0, beta=1.0)
        eve["LSEG"] = xrow("LSEG", "2026-11-09", 92, src="LSEG.L", bench="IEUR", mm5=1.0, beta=1.0)
        self.snap("2026-11-10", eve, "2026-11-09T22:12:21Z")
        self.run_g("--daily", "--today", "2026-11-10")
        g = self.rows()
        self.assertEqual(g["USX"]["test_grade"], "fail")              # -1% vs SPY +1.5%
        self.assertEqual(g["USX"]["test_numbers"]["bench_method"], "SPY_row_closes")
        self.assertIn(g["MC.PA"]["test_grade"], ("pass", "fail"))
        self.assertEqual(g["MC.PA"]["test_numbers"]["end_close"], 612)  # the completed close, not the 610 mid-session print
        self.assertIsNone(g["OLDUS"].get("test_grade"))
        self.assertEqual(g["7203.T"]["test_graded_on"], "2026-11-09")  # never regraded


class MonWedFriCadence(unittest.TestCase):
    """Digest stores snapshots Mon/Wed/Fri 08:12 ET only, each holding the previous session's closes.
    Stored US closes are therefore Tue, Thu and Fri; Mon and Wed closes are never stored."""

    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="ta_eval_mwf_")
        os.makedirs(os.path.join(self.d, "tape_snapshots"))
        shutil.copy(os.path.join(HERE, "grading_spec.json"), self.d)
        self.universe = ["UA", "UB", "UC", "UD", "UE", "FLG", "HLD", "SPY"]
        with open(os.path.join(self.d, "universe.json"), "w") as f:
            json.dump({"built": "2026-11-02", "private": True,
                       "all_names": [{"ticker": t, "roles": ["long"]} for t in self.universe]}, f)
        with open(os.path.join(self.d, "run_log.jsonl"), "w") as f:
            pass

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def px(self, t, day):
        k = (grade.pdate(day) - grade.pdate("2026-10-26")).days
        return {"SPY": 100 + 0.1 * k, "BRK": 20 + 0.05 * k, "CAP": 10 + 0.2 * k, "OUT": 50.0}.get(t, 30 + 0.01 * k)

    def build(self, start, end, skip=(), tickers=("SPY", "BRK", "CAP", "UA", "UB", "UC", "UD", "UE", "FLG", "HLD", "OUT1", "OUT2")):
        d = grade.pdate(start)
        while d <= grade.pdate(end):
            ds = d.isoformat()
            if d.weekday() in (0, 2, 4) and grade.is_session(d, "nyse") and ds not in skip:
                prev = grade.add_sessions(ds, -1, "nyse")
                rows = {}
                for t in tickers:
                    r = row(t, prev, self.px(t, prev), rsi=20 if t == "CAP" else 50, state="panic" if t == "CAP" else "normal",
                            p50=2.0 if t == "BRK" else 0.5, direction="leading_uptrend" if t == "BRK" else "stable",
                            rvol=1.6 if t == "BRK" else 1.0, cmf=0.2 if t == "BRK" else 0.0)
                    r["source"] = "yahoo:" + t
                    rows[t] = r
                with open(os.path.join(self.d, "tape_snapshots", ds + ".json"), "w") as f:
                    json.dump({"rows": rows, "generated_at": ds + "T13:12:00Z"}, f)
            d += grade.dt.timedelta(days=1)

    def run_g(self, *a):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            grade.main(["--eval-dir", self.d] + list(a))
        return buf.getvalue()

    def rows(self):
        return grade.read_log(os.path.join(self.d, "run_log.jsonl"))

    def by(self, t, rd=None):
        return next(r for r in self.rows() if r["ticker"] == t and (rd is None or r["run_date"] == rd))

    def reg(self, rd, flags, held=(), baseline=None):
        p = os.path.join(self.d, f"cand_{rd}.json")
        with open(p, "w") as f:
            json.dump({"run_date": rd, "flags": flags, "held": [{"ticker": h, "reason": "x"} for h in held],
                       "baseline": baseline if baseline is not None else {"n": 0}}, f)
        return self.run_g("--register", p, "--today", rd)

    def test_window_end_on_unstored_session_uses_next_close(self):
        self.build("2026-10-26", "2026-11-04")
        # run Mon 11-02: base = Fri 10-30 close (in Mon snapshot). 3S end = Wed 11-04 (never stored) -> Thu 11-05
        self.reg("2026-11-02", [{"ticker": "BRK", "kind": "tape", "flag": "breakout CMF 0.200"},
                                {"ticker": "CAP", "kind": "tape", "flag": "panic RSI 20.0"}])
        self.run_g("--daily", "--today", "2026-11-04")            # Wed: no stored close on/after Wed 11-04 yet
        self.assertIsNone(self.by("BRK").get("test_grade"))
        self.build("2026-11-05", "2026-11-06")
        self.run_g("--daily", "--today", "2026-11-06")            # Fri snapshot carries Thu 11-05
        b = self.by("BRK")
        self.assertEqual(b["test_grade"], "pass")
        self.assertEqual(b["test_numbers"]["end_as_of_used"], "2026-11-05")
        self.assertEqual(b["test_numbers"]["sessions_elapsed"], 4)
        self.assertEqual(b["test_numbers"]["end_resolution"]["status"], "substituted")
        self.assertEqual([x["as_of"] for x in b["test_numbers"]["sessions"]], ["2026-11-03", "2026-11-05"])
        c = self.by("CAP")
        self.assertEqual(c["persistence_numbers"]["as_of"], "2026-11-03")   # Mon 11-02 never stored
        self.assertEqual(c["persistence_numbers"]["sessions_elapsed"], 2)
        self.assertIsNone(c.get("test_grade"))                    # 5S end Fri 11-06 not stored until Mon 11-09
        self.build("2026-11-07", "2026-11-09")
        self.run_g("--daily", "--today", "2026-11-09")
        c = self.by("CAP")
        self.assertEqual(c["test_grade"], "pass")                 # +0.2/day on 10 vs SPY +0.1/day on 100
        self.assertEqual(c["test_numbers"]["sessions_elapsed"], 5)
        self.assertEqual(c["test_numbers"]["end_resolution"]["status"], "exact")

    def test_holiday_week_and_skipped_run(self):
        # Thanksgiving: base Fri 11-20, 5 sessions -> Mon 11-30 (never stored); Wed 12-02 run also skipped
        self.build("2026-11-16", "2026-12-02", skip=("2026-12-02",))
        self.reg("2026-11-23", [{"ticker": "CAP", "kind": "tape", "flag": "panic RSI 20.0"}])
        self.run_g("--daily", "--today", "2026-12-02")
        self.assertIsNone(self.by("CAP").get("test_grade"))
        self.build("2026-12-03", "2026-12-04")
        self.run_g("--daily", "--today", "2026-12-04")            # Fri 12-04 snapshot carries Thu 12-03
        c = self.by("CAP")
        self.assertEqual(c["test_numbers"]["end_as_of_used"], "2026-12-03")
        self.assertEqual(c["test_numbers"]["sessions_elapsed"], 8)
        self.assertEqual(c["test_grade"], "pass")

    def test_no_data_only_after_ten_further_sessions(self):
        self.build("2026-10-26", "2026-11-06")
        self.reg("2026-11-02", [{"ticker": "GONE", "kind": "tape", "flag": "panic RSI 20.0"}])
        r = self.by("GONE")
        self.assertEqual(r["window_end_as_of"], "2026-11-06")
        # GONE never appears; US frontier advances. End 11-06 + 10 sessions = 11-20
        self.build("2026-11-09", "2026-11-20", tickers=("SPY",))
        self.run_g("--daily", "--today", "2026-11-20")            # frontier Thu 11-19 <= 11-20: still pending
        self.assertIsNone(self.by("GONE").get("test_grade"))
        self.build("2026-11-23", "2026-11-23", tickers=("SPY",))  # Mon 11-23 carries Fri 11-20 close (== limit)
        self.run_g("--daily", "--today", "2026-11-23")
        self.assertIsNone(self.by("GONE").get("test_grade"))
        self.build("2026-11-25", "2026-11-25", tickers=("SPY",))  # Wed 11-25 carries Tue 11-24 > limit
        self.run_g("--daily", "--today", "2026-11-25")
        g = self.by("GONE")
        self.assertEqual(g["test_grade"], "no_data")
        self.assertEqual(g["test_numbers"]["end_resolution"]["status"], "no_close")

    def test_universe_mode_baseline(self):
        self.build("2026-10-26", "2026-11-02")
        out = self.reg("2026-11-02", [{"ticker": "FLG", "kind": "tape", "flag": "panic RSI 20.0"}], held=["HLD"],
                       baseline={"mode": "universe", "n": 20})
        bl = [r for r in self.rows() if r.get("cohort") == "baseline"]
        self.assertEqual(sorted(r["ticker"] for r in bl), ["UA", "UB", "UC", "UD", "UE"])  # universe - flagged - held - SPY
        self.assertTrue(all(r["baseline_pool"] == "universe_same_day_snapshot" for r in bl))
        self.assertTrue(all(r["universe_file"] == "universe.json" and r["baseline_pool_size"] == 5 for r in bl))
        self.assertFalse({"OUT1", "OUT2", "BRK", "CAP"} & {r["ticker"] for r in bl})
        # idempotent: re-registering adds no second baseline
        self.reg("2026-11-02", [{"ticker": "FLG", "kind": "tape", "flag": "panic RSI 20.0"}], held=["HLD"],
                 baseline={"mode": "universe", "n": 20})
        self.assertEqual(len([r for r in self.rows() if r.get("cohort") == "baseline"]), 5)

    def test_existing_grades_unchanged(self):
        self.build("2026-10-26", "2026-11-13")
        legacy = [
            {"run_date": "2026-10-28", "ticker": "CAP", "kind": "tape", "flag": "panic RSI 20.0", "flag_kind": "capitulation",
             "test_id": "TA-CAP-5D", "test_window_sessions": 5, "base_as_of": "2026-10-27", "window_end_as_of": "2026-11-03",
             "persistence_as_of": "2026-10-28", "test_grade": "fail", "test_graded_on": "2026-11-04",
             "test_numbers": {"excess_return_pct": -1.0}, "persistence_grade": "faded", "grade": "faded", "drew_verdict": "keep"},
            {"run_date": "2026-10-28", "ticker": "UA", "kind": "tape", "flag": "RSI 20.0", "flag_kind": "rsi_oversold",
             "test_id": "TA-RSI-OS-5D", "test_window_sessions": 5, "base_as_of": "2026-10-27", "window_end_as_of": "2026-10-28",
             "persistence_as_of": "2026-10-28", "test_grade": "no_data", "test_graded_on": "2026-11-04",
             "test_numbers": {"missing": "x"}, "persistence_grade": "no_data"}]
        with open(os.path.join(self.d, "run_log.jsonl"), "w") as f:
            for r in legacy:
                f.write(json.dumps(r) + "\n")
        self.run_g("--daily", "--today", "2026-11-13")
        got = {r["ticker"]: r for r in self.rows()}
        for r in legacy:
            for k, v in r.items():
                self.assertEqual(got[r["ticker"]][k], v, (r["ticker"], k))


if __name__ == "__main__":
    unittest.main(verbosity=2)
