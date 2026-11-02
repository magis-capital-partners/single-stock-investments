#!/usr/bin/env python3
"""Technical Analyst desk self-grading (stdlib only).

Eval store layout (default --eval-dir is the directory holding this file):
  grading_spec.json          pre-registered tests (read-only for this script)
  run_log.jsonl              one row per posted flag (+ held and baseline rows added here)
  tape_snapshots/<date>.json {"rows": {TICKER: technical_summary row, ...}, ...}
  index_announcements.json   provider announcements used by the index tests (optional)

Modes
  --register <candidates.json> [--retro]   append/annotate rows with their pre-registered test
  --backfill-retro                         add test fields to existing rows that lack them (registered_retro: true)
  --daily [--today YYYY-MM-DD]             grade every row whose window has closed
  --report [--out FILE]                    pass rates per rule id and flag kind vs baseline

candidates.json input format (one file per desk run):
{
  "run_date": "2026-11-02",                         # required, YYYY-MM-DD (the desk run / posting date)
  "source": "dashboard/data/technical_summary.json", # optional, copied to new rows
  "source_generated_at": "2026-11-01T22:10:00Z",     # optional, copied to new rows
  "flags": [                                         # posted flags
    {"ticker": "AMZN", "kind": "tape", "flag": "panic RSI 34.1",
     "lens_rules": ["TAPE-01"], "owner_desk": null, "trend_state": "pullback_in_uptrend", "rvol": 2.25},
    {"ticker": "PBT", "kind": "index", "flag": "S&P 600 inclusion_candidate -5.25%",
     "index": "sp600", "action": "add"}             # index/action optional; parsed from flag text if absent
  ],
  "held": [                                          # names held instead of posted
    {"ticker": "GOOGL", "reason": "TAPE-06 gap -11.7%", "counterfactual_flag": "capitulation_candidate rvol 5.41"}
  ],                                                 # counterfactual_flag optional; else derived from the snapshot row
  "baseline": {"n": 20, "exclude": []}               # optional; default n=20, seeded from run_date
}
Idempotent per run_date+ticker+flag: an existing row with the same key gets the test fields added in
place (never duplicated, existing values never changed). Prints the number of flag rows registered.
"""
import argparse, datetime as dt, hashlib, json, os, random, re, statistics, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SPEC_VERSION_DEFAULT = "1.0"

NYSE_HOLIDAYS = {
    "2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03", "2026-05-25", "2026-06-19", "2026-07-03",
    "2026-09-07", "2026-11-26", "2026-12-25",
    "2027-01-01", "2027-01-18", "2027-02-15", "2027-03-26", "2027-05-31", "2027-06-18", "2027-07-05",
    "2027-09-06", "2027-11-25", "2027-12-24",
}
NON_US_SUFFIXES = (".T", ".PA", ".TO", ".V", ".L", ".SA", ".HK", ".AX", ".NZ", ".MX", ".DE", ".ST", ".WA",
                   ".KL", ".SI", ".NS", ".MC", ".AS", ".SW", ".CO", ".HE", ".OL", ".MI")
CAP_STATES = {"stress_building", "panic", "capitulation_candidate", "washed_out"}
TH = {"rsi_deep": 25.0, "rsi_appr": 35.0, "rsi_ob": 70.0, "stretch": 2.0, "trend": 1.25, "cmf": 0.10}
RULE_ALIASES = {**{f"F{i}": f"FLOW-0{i}" for i in range(1, 8)}, **{f"M{i}": f"TAPE-0{i}" for i in range(1, 7)}}
INDEX_DEADLINES = {"russell": "2026-12-11", "sp_dji_us": "2026-12-19", "nasdaq_100": "2026-12-19",
                   "tsx": "2026-12-19", "ftse_uk": "2026-12-19", "msci": "2026-11-30"}
KIND_TEST = {"capitulation": "TA-CAP-5D", "rsi_oversold": "TA-RSI-OS-5D", "rsi_overbought": "TA-RSI-OB-5D",
             "breakout": "TA-BRK-3S", "breakout_lost": "TA-BRKLOST-3S", "z_stretch": "TA-Z-5D",
             "z_trend": "TA-Z-5D", "cmf": "TA-Z-5D", "index_add": "TA-IDX-EVENT", "index_delete": "TA-IDX-EVENT",
             "index_migration": "TA-IDX-EVENT", "index_watch_removed": "TA-IDX-NEG", "index_report": "TA-IDX-REPORT"}
KIND_RULES = {"capitulation": ["FLOW-05", "TAPE-05"], "rsi_oversold": ["FLOW-05", "TAPE-01"],
              "rsi_overbought": ["FLOW-05", "TAPE-01", "TAPE-02"], "breakout": ["FLOW-05", "TAPE-04"],
              "breakout_lost": ["FLOW-05", "TAPE-04"], "z_stretch": ["FLOW-05"], "z_trend": ["FLOW-05"],
              "cmf": ["FLOW-05"], "index_add": ["FLOW-01", "FLOW-04"], "index_delete": ["FLOW-01", "FLOW-04"],
              "index_migration": ["FLOW-01", "FLOW-02", "FLOW-04"], "index_watch_removed": ["FLOW-01", "FLOW-04"],
              "index_report": ["FLOW-04"]}
BASELINE_TESTS = ["TA-CAP-5D", "TA-RSI-OS-5D", "TA-RSI-OB-5D", "TA-BRK-3S", "TA-Z-5D-up", "TA-Z-5D-down"]
TEST_FIELDS = ("flag_kind", "test_id", "test_window_sessions", "base_as_of", "graded_after", "registered_retro")


# ----------------------------------------------------------------------------- io
def load_json(p, default=None):
    if not os.path.exists(p):
        return default
    with open(p) as f:
        return json.load(f)


def read_log(path):
    rows = []
    if os.path.exists(path):
        with open(path) as f:
            for line in f:
                if line.strip():
                    rows.append(json.loads(line))
    return rows


def write_log(path, rows):
    d = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".run_log.", suffix=".tmp")
    with os.fdopen(fd, "w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    os.replace(tmp, path)


def write_json(path, obj):
    d = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".tmp.", suffix=".json")
    with os.fdopen(fd, "w") as f:
        json.dump(obj, f, indent=1, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, path)


def get(d, path, default=None):
    cur = d
    for k in path.split("."):
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


def pdate(s):
    return dt.date.fromisoformat(s[:10])


# ------------------------------------------------------------------------ calendar
def is_non_us(ticker):
    return ticker.upper().endswith(NON_US_SUFFIXES)


def is_session(d, cal):
    if d.weekday() >= 5:
        return False
    return cal != "nyse" or d.isoformat() not in NYSE_HOLIDAYS


def add_sessions(day, n, cal):
    d = pdate(day) if isinstance(day, str) else day
    step = 1 if n >= 0 else -1
    k = 0
    while k < abs(n):
        d += dt.timedelta(days=step)
        if is_session(d, cal):
            k += 1
    return d.isoformat()


def cal_for(ticker):
    return "weekday_approx" if is_non_us(ticker) else "nyse"


# ------------------------------------------------------------------------ snapshots
class Tape:
    """Point-in-time index of stored rows: (ticker, as_of) -> (row, snapshot_date). Earliest snapshot wins."""

    def __init__(self, eval_dir):
        self.dir = os.path.join(eval_dir, "tape_snapshots")
        self.snaps = {}
        self.by_key = {}
        self.by_asof = {}
        if os.path.isdir(self.dir):
            for fn in sorted(os.listdir(self.dir)):
                if not re.match(r"\d{4}-\d{2}-\d{2}\.json$", fn):
                    continue
                snap_date = fn[:10]
                data = load_json(os.path.join(self.dir, fn), {})
                rows = data.get("rows", {}) or {}
                self.snaps[snap_date] = data
                for t, r in rows.items():
                    a = r.get("as_of")
                    if not a:
                        continue
                    if (t, a) not in self.by_key:
                        self.by_key[(t, a)] = (r, snap_date)
                        self.by_asof.setdefault(a, []).append((t, r))

    def latest_snapshot(self):
        return max(self.snaps) if self.snaps else None

    def max_asof(self):
        return max(self.by_asof) if self.by_asof else None

    def row(self, ticker, as_of):
        v = self.by_key.get((ticker, as_of))
        return v[0] if v else None

    def snap_rows(self, snap_date):
        return (self.snaps.get(snap_date) or {}).get("rows", {}) or {}

    def implied_spy_5d(self, end_as_of):
        vals = []
        for t, r in self.by_asof.get(end_as_of, []):
            beta = get(r, "context.beta_252d")
            mm = get(r, "context.market_move_5d_pct")
            if r.get("benchmark") == "SPY" and beta is not None and mm is not None and abs(beta) >= 0.5:
                vals.append(mm / beta)
        if len(vals) < 10:
            return None, len(vals)
        return round(statistics.median(vals), 4), len(vals)


# ----------------------------------------------------------------------- classify
NUM = r"(-?\d+(?:\.\d+)?)"
INDEX_PATTERNS = [
    (r"nasdaq-?100", "nasdaq_100"), (r"russell\s*1000|r1000", "russell_1000"),
    (r"russell\s*2000|r2000", "russell_2000"), (r"s&p\s*600|sp600", "sp600"), (r"s&p\s*400|sp400", "sp400"),
    (r"s&p\s*500|sp500", "sp500"), (r"tsx venture", "tsxv"), (r"tsx", "tsx_composite"),
]


def index_family(idx):
    if not idx:
        return None
    if idx.startswith("russell"):
        return "russell"
    if idx in ("sp400", "sp500", "sp600"):
        return "sp_dji_us"
    if idx == "nasdaq_100":
        return "nasdaq_100"
    if idx.startswith("tsx"):
        return "tsx"
    return None


def parse_metric(text, name):
    m = re.search(name + r"\s*" + NUM, text, re.I)
    return float(m.group(1)) if m else None


def classify(flag, kind=None):
    """Map posted flag text to (flag_kind, details). details carries field/value/direction/index/action."""
    text = (flag or "").strip()
    low = text.lower()
    lead = low.split()[0] if low.split() else ""
    det = {}
    idx = None
    for pat, name in INDEX_PATTERNS:
        if re.search(pat, low):
            idx = name
            break
    index_lead = lead.startswith(("sp400", "sp500", "sp600", "s&p", "russell", "r2000", "r1000", "nasdaq"))
    if kind == "index" or index_lead:
        det["index"] = idx
        if "watch removed" in low:
            return "index_watch_removed", det
        if re.search(r"\badd eff|\badded\b|venture composite add|join(ed)? ", low) and ("eff" in low or "news-only" in low or "joined" in low):
            det["action"] = "add"
            return "index_report", det
        if "deletion_risk" in low or "deletion risk" in low or "delete" in low:
            det["action"] = "delete"
            if idx == "russell_1000":
                det["action"] = "migration_to_russell_2000"
                return "index_migration", det
            return "index_delete", det
        det["action"] = "add"
        if idx == "russell_1000" and ("flow-02" in low or "net-sell" in low):
            det["action"] = "migration_to_russell_1000"
            return "index_migration", det
        return "index_add", det
    if lead in CAP_STATES:
        det["state"] = lead
        rest = low[len(lead):]
        for name, fld in (("rsi", "rsi14"), ("stretch_z", "stretch_z"), ("trend_z", "trend_z"), ("cmf", "cmf")):
            m = re.match(r"\s*" + name + r"\s*" + NUM, rest)
            if m:
                det["field"], det["value"] = fld, float(m.group(1))
        return "capitulation", det
    if lead == "breakout":
        if low.startswith("breakout lost"):
            return "breakout_lost", det
        return "breakout", det
    if lead == "rsi":
        v = parse_metric(low, "rsi")
        det["field"], det["value"] = "rsi14", v
        if v is None:
            return "unclassified", det
        if v > TH["rsi_ob"]:
            det["direction"] = 1
            return "rsi_overbought", det
        if v < TH["rsi_appr"]:
            det["direction"] = -1
            return "rsi_oversold", det
        return "unclassified", det
    for name, kd, fld in (("stretch_z", "z_stretch", "stretch_z"), ("trend_z", "z_trend", "trend_z"), ("cmf", "cmf", "cmf")):
        if lead.startswith(name) or (lead == "exhaustion_emerging" and name in low):
            v = parse_metric(low, name)
            if v is None:
                continue
            det["field"], det["value"], det["direction"] = fld, v, (1 if v > 0 else -1)
            if lead == "exhaustion_emerging":
                det["state"] = lead
            return kd, det
    return "unclassified", det


def counterfactual_kind(row):
    """Kind a held name would have been, from its stored snapshot row and the fixed thresholds."""
    if not row:
        return None, {}
    st = get(row, "capitulation.state")
    rsi = get(row, "setup.indicators.rsi_14")
    if st in CAP_STATES:
        return "capitulation", {"state": st}
    if rsi is not None and rsi < TH["rsi_appr"]:
        return "rsi_oversold", {"field": "rsi14", "value": rsi, "direction": -1}
    if rsi is not None and rsi > TH["rsi_ob"]:
        return "rsi_overbought", {"field": "rsi14", "value": rsi, "direction": 1}
    if breakout_met(row):
        return "breakout", {}
    for fld, kd, th in (("stretch_z", "z_stretch", TH["stretch"]), ("trend_z", "z_trend", TH["trend"]), ("cmf", "cmf", TH["cmf"])):
        v = field_value(row, fld)
        if v is not None and abs(v) > th:
            return kd, {"field": fld, "value": v, "direction": 1 if v > 0 else -1}
    return "none", {}


# ------------------------------------------------------------------------- fields
FIELD_PATH = {"rsi14": "setup.indicators.rsi_14", "stretch_z": "scores.stretch_z", "trend_z": "scores.trend_z",
              "cmf": "setup.indicators.chaikin_money_flow_20d", "rvol": "setup.indicators.relative_volume_20d",
              "price_vs_50d_pct": "setup.indicators.price_vs_50d_pct"}


def field_value(row, fld):
    return get(row, FIELD_PATH[fld]) if row else None


def breakout_met(row):
    if not row:
        return None
    d = get(row, "setup.direction")
    p = field_value(row, "price_vs_50d_pct")
    rv = field_value(row, "rvol")
    c = field_value(row, "cmf")
    if None in (p, rv, c):
        return None
    return d == "leading_uptrend" and p > 0 and rv > 1 and c >= 0.10


def beyond(fld, value, ref_value):
    """Is `value` still beyond the threshold the flagged `ref_value` crossed (same side)?"""
    if value is None:
        return None
    if fld == "rsi14":
        if ref_value is not None and ref_value > TH["rsi_ob"]:
            return value > TH["rsi_ob"]
        band = TH["rsi_deep"] if (ref_value is not None and ref_value < TH["rsi_deep"]) else TH["rsi_appr"]
        return value < band
    th = {"stretch_z": TH["stretch"], "trend_z": TH["trend"], "cmf": TH["cmf"]}[fld]
    sign = 1 if (ref_value or 0) > 0 else -1
    return value * sign > th


# --------------------------------------------------------------------- base dates
def base_as_of_for(row, tape):
    """Return (base_as_of, how)."""
    t, rd = row["ticker"], row["run_date"]
    snap = tape.snap_rows(rd)
    if t in snap and snap[t].get("as_of"):
        return snap[t]["as_of"], "snapshot_row"
    src = row.get("source") or ""
    m = re.search(r"as_of (\d{4}-\d{2}-\d{2})", src)
    if m:
        return m.group(1), "source_string"
    fa = (tape.snaps.get(rd) or {}).get("feed_as_of")
    if fa:
        return fa, "snapshot_feed_as_of"
    return add_sessions(rd, -1, cal_for(t)), "inferred_prior_session"


def deadline_for(idx):
    fam = index_family(idx)
    return INDEX_DEADLINES.get(fam) if fam else None


# -------------------------------------------------------------------- registration
def test_fields(row, tape, spec_version, retro, today, kind_override=None, det_override=None):
    kind, det = (kind_override, det_override) if kind_override else classify(row.get("flag"), row.get("kind"))
    test_id = KIND_TEST.get(kind)
    out = {"flag_kind": kind, "flag_details": det, "test_id": test_id, "test_spec_version": spec_version,
           "registered_on": today, "registered_retro": bool(retro)}
    if not row.get("lens_rules"):
        out["lens_rules_inferred"] = KIND_RULES.get(kind, [])
    if test_id is None:
        out.update({"test_window_sessions": None, "base_as_of": None, "graded_after": None})
        return out
    if test_id.startswith("TA-IDX"):
        idx = det.get("index")
        dl = row["run_date"] if test_id == "TA-IDX-REPORT" else deadline_for(idx)
        out.update({"test_window_sessions": None, "base_as_of": row["run_date"], "test_deadline": dl,
                    "graded_after": dl})
        return out
    base, how = base_as_of_for(row, tape)
    n = 3 if test_id in ("TA-BRK-3S", "TA-BRKLOST-3S") else 5
    cal = cal_for(row["ticker"])
    end = add_sessions(base, n, cal)
    out.update({"test_window_sessions": n, "base_as_of": base, "base_as_of_source": how,
                "base_as_of_inferred": how == "inferred_prior_session", "window_end_as_of": end,
                "persistence_as_of": add_sessions(base, 1, cal), "calendar": cal,
                "graded_after": (pdate(end) + dt.timedelta(days=1)).isoformat()})
    return out


def is_registered(row):
    return row.get("test_id") is not None or row.get("flag_kind") is not None


def baseline_seed(run_date):
    return int(hashlib.sha256(("ta-baseline|" + run_date).encode()).hexdigest()[:12], 16)


def baseline_pool(run_date, tape, log_rows, exclude, retro):
    snap = tape.snap_rows(run_date)
    if snap:
        pool = [t for t, r in snap.items() if t != "SPY" and t not in exclude and r.get("data_quality", "ready") == "ready"]
        return sorted(pool), "same_day_snapshot"
    if not retro:
        return [], "no_snapshot"
    # retro proxy: names logged on/before run_date (not flagged that day) with a stored row at the 5-session end
    prior = {r["ticker"] for r in log_rows if r.get("run_date", "") <= run_date and r.get("cohort", "flag") == "flag"}
    base = add_sessions(run_date, -1, "nyse")
    m = [r for r in log_rows if r.get("run_date") == run_date and r.get("base_as_of")]
    if m:
        base = m[0]["base_as_of"]
    end = add_sessions(base, 5, "nyse")
    pool = sorted(t for t in prior if t not in exclude and t != "SPY" and tape.row(t, end) and not is_non_us(t))
    return pool, "retro_proxy_prior_flagged_with_end_row"


def register(eval_dir, cand, retro=False, today=None, spec_version=SPEC_VERSION_DEFAULT, quiet=False):
    today = today or dt.date.today().isoformat()
    log_path = os.path.join(eval_dir, "run_log.jsonl")
    rows = read_log(log_path)
    tape = Tape(eval_dir)
    rd = cand["run_date"]
    keys = {(r.get("run_date"), r.get("ticker"), r.get("flag")): i for i, r in enumerate(rows)}
    n_flag = 0
    added = annotated = 0
    flagged_today = set()
    for f in cand.get("flags", []):
        flagged_today.add(f["ticker"])
        key = (rd, f["ticker"], f["flag"])
        if key in keys:
            r = rows[keys[key]]
            if not is_registered(r):
                for k, v in test_fields(r, tape, spec_version, retro, today).items():
                    r.setdefault(k, v)
                r.setdefault("cohort", "held" if re.search(r"held tape-0\d", r.get("flag", ""), re.I) else "flag")
                annotated += 1
            n_flag += 1
            continue
        r = {"run_date": rd, "ticker": f["ticker"], "kind": f.get("kind", "tape"), "flag": f["flag"],
             "source": f.get("source", cand.get("source")),
             "source_generated_at": f.get("source_generated_at", cand.get("source_generated_at")),
             "owner_desk": f.get("owner_desk"), "lens_rules": f.get("lens_rules") or [],
             "trend_state": f.get("trend_state"), "rvol": f.get("rvol"),
             "verdict": None, "verdict_by": None, "graded_on": None, "grade": None}
        r["cohort"] = "held" if re.search(r"held tape-0\d", f["flag"], re.I) else "flag"
        tf = test_fields(r, tape, spec_version, retro, today)
        if f.get("index"):
            tf["flag_details"]["index"] = f["index"]
            if tf["test_id"] == "TA-IDX-EVENT":
                tf["test_deadline"] = tf["graded_after"] = deadline_for(f["index"])
        if f.get("action"):
            tf["flag_details"]["action"] = f["action"]
        r.update(tf)
        rows.append(r)
        keys[key] = len(rows) - 1
        added += 1
        n_flag += 1
    # held names
    held_added = 0
    held_today = set()
    for h in cand.get("held", []):
        t = h["ticker"]
        held_today.add(t)
        if any(r.get("run_date") == rd and r.get("ticker") == t for r in rows):
            r0 = next(r for r in rows if r.get("run_date") == rd and r.get("ticker") == t)
            r0.setdefault("held_reason", h.get("reason"))
            continue
        cf = h.get("counterfactual_flag")
        r = {"run_date": rd, "ticker": t, "kind": "held", "flag": "held: " + (h.get("reason") or ""),
             "cohort": "held", "held_reason": h.get("reason"), "source": cand.get("source"),
             "source_generated_at": cand.get("source_generated_at"),
             "verdict": None, "verdict_by": None, "graded_on": None, "grade": None}
        if cf:
            kind, det = classify(cf, "tape")
            r["counterfactual_flag"] = cf
        else:
            snaprow = tape.snap_rows(rd).get(t)
            kind, det = counterfactual_kind(snaprow)
            if kind is None:
                kind = "unknown_no_snapshot_row"
        tf = test_fields(r, tape, spec_version, retro, today, kind_override=kind, det_override=det)
        r.update(tf)
        if kind in ("none", "unknown_no_snapshot_row"):
            r["test_note"] = "no counterfactual flag: " + ("snapshot row missing" if kind != "none" else "no threshold crossed")
        rows.append(r)
        held_added += 1
    # baseline
    bl = cand.get("baseline", {}) or {}
    n_bl = int(bl.get("n", 20))
    excl = flagged_today | held_today | set(bl.get("exclude", []))
    excl |= {r["ticker"] for r in rows if r.get("run_date") == rd and r.get("cohort") in ("flag", "held", None)}
    existing_bl = [r for r in rows if r.get("run_date") == rd and r.get("cohort") == "baseline"]
    bl_added = 0
    pool_method = None
    if not existing_bl and n_bl > 0:
        pool, pool_method = baseline_pool(rd, tape, rows, excl, retro)
        seed = baseline_seed(rd)
        sample = random.Random(seed).sample(pool, min(n_bl, len(pool))) if pool else []
        for t in sorted(sample):
            r = {"run_date": rd, "ticker": t, "kind": "baseline", "flag": f"baseline_sample seed={seed}",
                 "cohort": "baseline", "baseline_pool": pool_method, "baseline_pool_size": len(pool),
                 "baseline_tests": BASELINE_TESTS, "verdict": None, "verdict_by": None, "graded_on": None, "grade": None,
                 "test_spec_version": spec_version, "registered_on": today, "registered_retro": bool(retro),
                 "flag_kind": "baseline", "test_id": "BASELINE"}
            snaprow = tape.snap_rows(rd).get(t)
            if snaprow:
                base, how = snaprow["as_of"], "snapshot_row"
            else:
                fr = [x for x in rows if x.get("run_date") == rd and x.get("base_as_of") and x.get("cohort") == "flag"]
                base, how = (fr[0]["base_as_of"], "same_run_flags") if fr else (add_sessions(rd, -1, "nyse"), "inferred_prior_session")
            cal = cal_for(t)
            r.update({"base_as_of": base, "base_as_of_source": how, "calendar": cal,
                      "window_end_as_of": add_sessions(base, 5, cal), "persistence_as_of": add_sessions(base, 1, cal),
                      "test_window_sessions": 5,
                      "graded_after": (pdate(add_sessions(base, 5, cal)) + dt.timedelta(days=1)).isoformat()})
            rows.append(r)
            bl_added += 1
    write_log(log_path, rows)
    if not quiet:
        print(json.dumps({"run_date": rd, "flag_rows_registered": n_flag, "flag_rows_added": added,
                          "flag_rows_annotated": annotated, "held_rows_added": held_added,
                          "baseline_rows_added": bl_added, "baseline_pool": pool_method}))
        print(n_flag)
    return n_flag


def backfill_retro(eval_dir, today=None, spec_version=SPEC_VERSION_DEFAULT):
    today = today or dt.date.today().isoformat()
    log_path = os.path.join(eval_dir, "run_log.jsonl")
    rows = read_log(log_path)
    tape = Tape(eval_dir)
    n = 0
    for r in rows:
        if is_registered(r) or r.get("cohort") == "baseline":
            continue
        tf = test_fields(r, tape, spec_version, True, today)
        for k, v in tf.items():
            r.setdefault(k, v)
        r.setdefault("cohort", "held" if re.search(r"held tape-0\d", r.get("flag", ""), re.I) else "flag")
        n += 1
    write_log(log_path, rows)
    print(json.dumps({"rows_backfilled_retro": n}))
    return n


# ------------------------------------------------------------------------- grading
def window_closed(end_as_of, tape, today):
    mx = tape.max_asof()
    if mx and mx >= end_as_of:
        return True
    return pdate(today) >= pdate(end_as_of) + dt.timedelta(days=4)


def five_session_return(t, base, end, n, tape):
    """Return dict with ret_pct, method, bench_pct, bench_method, or reasons for missing data."""
    out = {}
    b, e = tape.row(t, base), tape.row(t, end)
    if e is None:
        out["missing"] = f"no stored row for {t} with as_of {end}"
        return out
    if b is not None and get(b, "latest.close") and get(e, "latest.close"):
        out["base_close"], out["end_close"] = get(b, "latest.close"), get(e, "latest.close")
        out["ret_pct"] = round((out["end_close"] / out["base_close"] - 1) * 100, 4)
        out["ret_method"] = "stored_closes"
    elif n == 5 and get(e, "measures.return_5d_pct") is not None:
        out["ret_pct"] = get(e, "measures.return_5d_pct")
        out["ret_method"] = "stored_return_5d_pct_at_end_row"
        out["end_close"] = get(e, "latest.close")
    else:
        out["missing"] = f"no stored base close for {t} at {base}"
        return out
    bench = e.get("benchmark") or "SPY"
    out["benchmark"] = bench
    if bench == "SPY":
        sb, se = tape.row("SPY", base), tape.row("SPY", end)
        if sb and se and get(sb, "latest.close") and get(se, "latest.close"):
            out["bench_pct"] = round((get(se, "latest.close") / get(sb, "latest.close") - 1) * 100, 4)
            out["bench_method"] = "SPY_row_closes"
        elif n == 5:
            v, k = tape.implied_spy_5d(end)
            if v is not None:
                out["bench_pct"], out["bench_method"], out["bench_rows_used"] = v, "implied_spy_median_market_move_over_beta", k
    elif n == 5:
        beta, mm = get(e, "context.beta_252d"), get(e, "context.market_move_5d_pct")
        if beta is not None and mm is not None and abs(beta) >= 0.5:
            out["bench_pct"], out["bench_method"] = round(mm / beta, 4), "own_benchmark_market_move_over_beta"
    if "bench_pct" not in out:
        out["missing"] = f"no stored benchmark move for {bench} {base}->{end}"
    else:
        out["excess_return_pct"] = round(out["ret_pct"] - out["bench_pct"], 4)
    return out


def persistence(row, kind, det, tape):
    t = row["ticker"]
    nx = tape.row(t, row["persistence_as_of"])
    if nx is None:
        return "no_data", {"missing": f"no stored row for {t} with as_of {row['persistence_as_of']}"}
    num = {"as_of": nx.get("as_of")}
    ok = None
    if kind == "capitulation":
        st = get(nx, "capitulation.state")
        num["state"] = st
        ok = st in CAP_STATES
        if det.get("field"):
            v = field_value(nx, det["field"])
            num[det["field"]] = v
            b = beyond(det["field"], v, det.get("value"))
            ok = None if b is None else (ok and b)
    elif kind in ("rsi_oversold", "rsi_overbought", "z_stretch", "z_trend", "cmf"):
        v = field_value(nx, det["field"])
        num[det["field"]] = v
        ok = beyond(det["field"], v, det.get("value"))
    elif kind in ("breakout", "breakout_lost"):
        m = breakout_met(nx)
        num.update({"breakout_rule_met": m, "price_vs_50d_pct": field_value(nx, "price_vs_50d_pct"),
                    "rvol": field_value(nx, "rvol"), "cmf": field_value(nx, "cmf"), "direction": get(nx, "setup.direction")})
        ok = None if m is None else (m if kind == "breakout" else (not m))
    else:
        return None, {}
    if ok is None:
        return "no_data", num
    return ("held" if ok else "faded"), num


def cmp(v, op, th):
    return {">": v > th, "<": v < th, "==": v == th}[op]


def grade_tape_test(row, test, kind, det, tape, spec_tests):
    t, base = row["ticker"], row["base_as_of"]
    n = row["test_window_sessions"]
    cal = row.get("calendar") or cal_for(t)
    num = {"base_as_of": base, "window_end_as_of": row["window_end_as_of"], "calendar": cal}
    if test in ("TA-BRK-3S", "TA-BRKLOST-3S"):
        res = []
        for k in (1, 2, 3):
            a = add_sessions(base, k, cal)
            r = tape.row(t, a)
            if r is None:
                num["missing"] = f"no stored row for {t} with as_of {a}"
                return "no_data", num
            p = field_value(r, "price_vs_50d_pct")
            m = breakout_met(r)
            res.append({"as_of": a, "price_vs_50d_pct": p, "breakout_rule_met": m, "close": get(r, "latest.close")})
        num["sessions"] = res
        if test == "TA-BRK-3S":
            if any(x["price_vs_50d_pct"] is None for x in res):
                return "no_data", num
            return ("pass" if all(x["price_vs_50d_pct"] > 0 for x in res) else "fail"), num
        if any(x["breakout_rule_met"] is None for x in res):
            return "no_data", num
        return ("pass" if not any(x["breakout_rule_met"] for x in res) else "fail"), num
    rr = five_session_return(t, base, row["window_end_as_of"], n, tape)
    num.update(rr)
    if test in ("TA-CAP-5D", "TA-RSI-OS-5D", "TA-RSI-OB-5D"):
        if "excess_return_pct" not in rr:
            return "no_data", num
        mc = spec_tests[test]["pass_condition"]["machine"]
        return ("pass" if cmp(rr["excess_return_pct"], mc["op"], mc["threshold"]) else "fail"), num
    if test == "TA-Z-5D":
        if "ret_pct" not in rr:
            return "no_data", num
        pg, pn = persistence(row, kind, det, tape)
        num["persistence_component"] = pg
        num["return_sign_x_direction"] = (1 if rr["ret_pct"] > 0 else -1 if rr["ret_pct"] < 0 else 0) * det.get("direction", 0)
        if pg == "no_data":
            return "no_data", num
        return ("pass" if pg == "held" and num["return_sign_x_direction"] > 0 else "fail"), num
    return None, num


def match_announcement(anns, ticker, idx, action):
    out = []
    for a in anns:
        if a.get("ticker") != ticker:
            continue
        if action and action.startswith("migration_to_"):
            target = action[len("migration_to_"):]
            if a.get("index") not in (idx, target):
                continue
        elif a.get("index") != idx or (action and a.get("action") != action):
            continue
        out.append(a)
    return out


def grade_index(row, det, ann, today):
    test = row["test_id"]
    anns = ann.get("announcements", [])
    chk = ann.get("checked_through")
    dl = row.get("test_deadline")
    idx, action = det.get("index"), det.get("action")
    num = {"index": idx, "action": action, "deadline": dl, "announcements_checked_through": chk}
    if not idx or not dl:
        num["missing"] = "index or deadline not parsed from flag"
        return "no_data", num
    m = [a for a in match_announcement(anns, row["ticker"], idx, action if test != "TA-IDX-NEG" else "add")
         if a.get("announced_on", "9999") <= dl]
    num["matches"] = m
    if test == "TA-IDX-REPORT":
        if m:
            return "pass", num
        return ("fail" if chk and chk >= dl else None), num
    if test == "TA-IDX-EVENT":
        if m:
            return "pass", num
        return ("fail" if chk and chk >= dl and today >= dl else None), num
    if test == "TA-IDX-NEG":
        if m:
            return "fail", num
        return ("pass" if chk and chk >= dl and today >= dl else None), num
    return None, num


def daily(eval_dir, today=None):
    today = today or dt.date.today().isoformat()
    spec = load_json(os.path.join(eval_dir, "grading_spec.json"), {})
    spec_tests = {t["id"]: t for t in spec.get("tests", [])}
    log_path = os.path.join(eval_dir, "run_log.jsonl")
    rows = read_log(log_path)
    tape = Tape(eval_dir)
    ann = load_json(os.path.join(eval_dir, "index_announcements.json"), {}) or {}
    stats = {"test_graded": 0, "persistence_graded": 0, "baseline_graded": 0, "legacy_grade_filled": 0, "pending": 0}
    for r in rows:
        tid = r.get("test_id")
        if not tid:
            continue
        kind, det = r.get("flag_kind"), r.get("flag_details") or {}
        if r.get("cohort") == "baseline":
            if r.get("baseline_grades") is not None:
                continue
            if not window_closed(r["window_end_as_of"], tape, today):
                stats["pending"] += 1
                continue
            g, nums = {}, {}
            rr = five_session_return(r["ticker"], r["base_as_of"], r["window_end_as_of"], 5, tape)
            nums["return_5s"] = rr
            for tst in ("TA-CAP-5D", "TA-RSI-OS-5D"):
                g[tst] = "no_data" if "excess_return_pct" not in rr else ("pass" if rr["excess_return_pct"] > 0 else "fail")
            g["TA-RSI-OB-5D"] = "no_data" if "excess_return_pct" not in rr else ("pass" if rr["excess_return_pct"] < 0 else "fail")
            g["TA-Z-5D-up"] = "no_data" if "ret_pct" not in rr else ("pass" if rr["ret_pct"] > 0 else "fail")
            g["TA-Z-5D-down"] = "no_data" if "ret_pct" not in rr else ("pass" if rr["ret_pct"] < 0 else "fail")
            cal = r.get("calendar") or cal_for(r["ticker"])
            end3 = add_sessions(r["base_as_of"], 3, cal)
            if window_closed(end3, tape, today):
                pr = {"window_end_as_of": end3, "base_as_of": r["base_as_of"], "test_window_sessions": 3, "ticker": r["ticker"], "calendar": cal}
                gb, nb = grade_tape_test(pr, "TA-BRK-3S", "breakout", {}, tape, spec_tests)
                g["TA-BRK-3S"], nums["breakout_3s"] = gb, nb
            r["baseline_grades"] = g
            r["baseline_numbers"] = nums
            r["baseline_graded_on"] = today
            stats["baseline_graded"] += 1
            continue
        # secondary: persistence (1 session)
        if kind in KIND_TEST and not kind.startswith("index") and r.get("persistence_grade") is None and r.get("persistence_as_of"):
            if window_closed(r["persistence_as_of"], tape, today):
                pg, pn = persistence(r, kind, det, tape)
                if pg:
                    r["persistence_grade"], r["persistence_numbers"], r["persistence_graded_on"] = pg, pn, today
                    stats["persistence_graded"] += 1
                    if r.get("grade") is None and r.get("cohort", "flag") == "flag":
                        r["grade"], r["graded_on"] = pg, today
                        r.setdefault("grade_note", "filled by grade.py --daily from persistence_grade")
                        stats["legacy_grade_filled"] += 1
        # primary test
        if r.get("test_grade") is not None:
            continue
        if tid.startswith("TA-IDX"):
            g, nums = grade_index(r, det, ann, today)
            if g is None:
                stats["pending"] += 1
                continue
        else:
            if not r.get("window_end_as_of") or not window_closed(r["window_end_as_of"], tape, today):
                stats["pending"] += 1
                continue
            g, nums = grade_tape_test(r, tid, kind, det, tape, spec_tests)
        if g is None:
            continue
        r["test_grade"], r["test_numbers"], r["test_graded_on"] = g, nums, today
        stats["test_graded"] += 1
    write_log(log_path, rows)
    print(json.dumps(stats))
    return stats


# --------------------------------------------------------------------------- report
def norm_rules(r):
    rules = r.get("lens_rules") or r.get("lens_rules_inferred") or []
    return sorted({RULE_ALIASES.get(x, x) for x in rules})


def rate(p, f):
    return round(p / (p + f), 4) if (p + f) else None


def report(eval_dir, out=None, today=None):
    today = today or dt.date.today().isoformat()
    rows = read_log(os.path.join(eval_dir, "run_log.jsonl"))
    flags = [r for r in rows if r.get("test_id") and r.get("cohort", "flag") in ("flag", "held") and r.get("test_id") != "BASELINE"]
    base = [r for r in rows if r.get("cohort") == "baseline" and r.get("baseline_grades")]
    bl_by_date = {}
    for b in base:
        for tst, g in b["baseline_grades"].items():
            bl_by_date.setdefault((b["run_date"], tst), []).append(g)

    def baseline_rate(graded_rows):
        """Date-matched baseline: pool the baseline grades of every (run_date, test) pair that has a graded
        flag in the selection, each pair counted once (no weighting by number of flags)."""
        pairs = set()
        for r in graded_rows:
            tst = r["test_id"]
            if tst == "TA-Z-5D":
                tst = "TA-Z-5D-up" if (r.get("flag_details") or {}).get("direction", 0) > 0 else "TA-Z-5D-down"
            pairs.add((r["run_date"], tst))
        p = f = 0
        for k in pairs:
            gs = bl_by_date.get(k, [])
            p += gs.count("pass")
            f += gs.count("fail")
        return rate(p, f), p + f

    def summarize(sel):
        out = {}
        for label, coh_rows in (("live", [r for r in sel if not r.get("registered_retro")]),
                                ("retro", [r for r in sel if r.get("registered_retro")]),
                                ("all", sel)):
            fl = [r for r in coh_rows if r.get("cohort", "flag") == "flag"]
            hd = [r for r in coh_rows if r.get("cohort") == "held"]
            gp = [r for r in fl if r.get("test_grade") in ("pass", "fail")]
            hp = [r for r in hd if r.get("test_grade") in ("pass", "fail")]
            p = sum(r["test_grade"] == "pass" for r in gp)
            br, bn = baseline_rate(gp)
            out[label] = {
                "registered": len(fl), "graded_n": len(gp), "pass": p, "fail": len(gp) - p,
                "pass_rate": rate(p, len(gp) - p),
                "no_data": sum(r.get("test_grade") == "no_data" for r in fl),
                "pending": sum(r.get("test_grade") is None for r in fl),
                "baseline_pass_rate": br, "baseline_n": bn,
                "held_counterfactual_n": len(hp),
                "held_counterfactual_pass_rate": rate(sum(r["test_grade"] == "pass" for r in hp), sum(r["test_grade"] == "fail" for r in hp)),
                "persistence_held": sum(r.get("persistence_grade") == "held" for r in fl),
                "persistence_faded": sum(r.get("persistence_grade") == "faded" for r in fl),
                "persistence_no_data": sum(r.get("persistence_grade") == "no_data" for r in fl),
                "legacy_grade_held": sum(r.get("grade") == "held" for r in fl),
                "legacy_grade_faded": sum(r.get("grade") == "faded" for r in fl),
            }
        flags_ur = []
        for label in ("live", "all"):
            s = out[label]
            if s["graded_n"] >= 20 and s["pass_rate"] is not None and s["baseline_pass_rate"] is not None and s["pass_rate"] <= s["baseline_pass_rate"]:
                flags_ur.append(label)
        out["under_review_candidate"] = bool(flags_ur)
        out["under_review_basis"] = flags_ur
        return out

    by_rule, by_kind = {}, {}
    for r in flags:
        for rule in norm_rules(r):
            by_rule.setdefault(rule, []).append(r)
        by_kind.setdefault(r.get("flag_kind"), []).append(r)
    rep = {
        "generated_on": today,
        "spec_version": sorted({r.get("test_spec_version") for r in flags if r.get("test_spec_version")}),
        "rows": {"flag": sum(r.get("cohort", "flag") == "flag" for r in flags), "held": sum(r.get("cohort") == "held" for r in rows),
                 "held_with_test": sum(r.get("cohort") == "held" for r in flags),
                 "baseline": sum(r.get("cohort") == "baseline" for r in rows),
                 "baseline_graded": len(base)},
        "by_rule": {k: summarize(v) for k, v in sorted(by_rule.items())},
        "by_flag_kind": {k: summarize(v) for k, v in sorted(by_kind.items(), key=lambda x: str(x[0]))},
        "baseline_by_test": {},
        "notes": [],
    }
    for tst in BASELINE_TESTS:
        gs = [g for b in base for k, g in b["baseline_grades"].items() if k == tst]
        rep["baseline_by_test"][tst] = {"n": gs.count("pass") + gs.count("fail"), "pass_rate": rate(gs.count("pass"), gs.count("fail")),
                                        "no_data": gs.count("no_data")}
    rep["overall"] = summarize(flags)
    if out:
        write_json(out, rep)
    print(json.dumps({"overall": rep["overall"], "rules": {k: {"live": v["live"]["graded_n"], "retro": v["retro"]["graded_n"],
                      "pass_rate_all": v["all"]["pass_rate"], "baseline_all": v["all"]["baseline_pass_rate"],
                      "under_review_candidate": v["under_review_candidate"]} for k, v in rep["by_rule"].items()}}, indent=1))
    return rep


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--eval-dir", default=HERE)
    ap.add_argument("--register")
    ap.add_argument("--retro", action="store_true")
    ap.add_argument("--backfill-retro", action="store_true")
    ap.add_argument("--daily", action="store_true")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--out")
    ap.add_argument("--today")
    a = ap.parse_args(argv)
    spec = load_json(os.path.join(a.eval_dir, "grading_spec.json"), {}) or {}
    sv = spec.get("spec_version", SPEC_VERSION_DEFAULT)
    if a.register:
        register(a.eval_dir, load_json(a.register), retro=a.retro, today=a.today, spec_version=sv)
    if a.backfill_retro:
        backfill_retro(a.eval_dir, today=a.today, spec_version=sv)
    if a.daily:
        daily(a.eval_dir, today=a.today)
    if a.report:
        report(a.eval_dir, out=a.out, today=a.today)
    if not (a.register or a.backfill_retro or a.daily or a.report):
        ap.print_help()


if __name__ == "__main__":
    main()
