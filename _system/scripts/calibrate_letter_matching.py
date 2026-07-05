#!/usr/bin/env python3
"""Calibration / precision harness for the letter -> ticker matcher.

Usage:
  python _system/scripts/calibrate_letter_matching.py            # summary report
  python _system/scripts/calibrate_letter_matching.py --dump     # per-pair review file
  python _system/scripts/calibrate_letter_matching.py --gold     # precision/recall vs gold.jsonl

Gold format (one JSON object per line) in _eval/gold.jsonl:
  {"source_file": "<relative path>", "true_tickers": ["ICE", "GRVY"]}

Precision/recall are computed against emitted (Tier>=B) mentions for the labeled
letters only. A CI-style threshold check is applied when --gold is used.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

import letter_matching as lm  # noqa: E402
from vault_paths import letters_root  # noqa: E402

LETTERS_ROOT = letters_root()
SECURITY_MASTER_PATH = ROOT / "_system" / "reference" / "securities" / "security_master.json"
EVAL_DIR = LETTERS_ROOT / "_eval"
GOLD_PATH = EVAL_DIR / "gold.jsonl"
DUMP_PATH = EVAL_DIR / "match_review.jsonl"

PRECISION_FLOOR = 0.90
RECALL_FLOOR = 0.80


def load_master() -> lm.SecurityMaster:
    data = json.loads(SECURITY_MASTER_PATH.read_text(encoding="utf-8"))
    return lm.SecurityMaster.from_dict(data)


def scan_letters() -> list[Path]:
    files: list[Path] = []
    for ext in ("*.txt", "*.md"):
        files.extend(LETTERS_ROOT.rglob(ext))
    return sorted({f.resolve() for f in files})


def rel(path: Path) -> str:
    return str(path.relative_to(ROOT)).replace("\\", "/")


def summary(master: lm.SecurityMaster) -> None:
    tiers: Counter[str] = Counter()
    rules: Counter[str] = Counter()
    emitted = 0
    letters = 0
    for path in scan_letters():
        letters += 1
        text = path.read_text(encoding="utf-8", errors="ignore")
        for m in lm.match_letter(text, master):
            tiers[m["tier"]] += 1
            for r in m["rules"]:
                rules[r] += 1
            if lm.TIER_RANK[m["tier"]] >= lm.TIER_RANK["B"]:
                emitted += 1
    total = sum(tiers.values())
    a, b, c = tiers["A"], tiers["B"], tiers["C"]
    explicit_share = (a / emitted) if emitted else 0
    high_conf_share = ((a + b) / total) if total else 0
    print(f"letters scanned         : {letters}")
    print(f"total candidate pairs   : {total}")
    print(f"  Tier A (explicit)     : {a}")
    print(f"  Tier B (name/bare)    : {b}")
    print(f"  Tier C (excluded)     : {c}")
    print(f"emitted (Tier>=B)       : {emitted}")
    print(f"explicit share of emit  : {explicit_share:.1%}")
    print(f"high-confidence share   : {high_conf_share:.1%}  (A+B of all candidates)")
    print("\nrule firings:")
    for r, n in rules.most_common():
        print(f"  {r:18} {n}")


def dump(master: lm.SecurityMaster) -> None:
    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    with DUMP_PATH.open("w", encoding="utf-8") as fh:
        for path in scan_letters():
            text = path.read_text(encoding="utf-8", errors="ignore")
            for m in lm.match_letter(text, master):
                fh.write(json.dumps({
                    "source_file": rel(path),
                    "ticker": m["ticker"],
                    "tier": m["tier"],
                    "rules": m["rules"],
                    "action": m["action"],
                    "mention_count": m["mention_count"],
                    "evidence": m["evidence"],
                }, ensure_ascii=False) + "\n")
    print(f"Wrote {rel(DUMP_PATH)} — review and copy true positives into {rel(GOLD_PATH)}")


def evaluate(master: lm.SecurityMaster) -> int:
    if not GOLD_PATH.exists():
        print(f"No gold file at {rel(GOLD_PATH)}. Run --dump, label, then retry.")
        return 1
    gold = [json.loads(ln) for ln in GOLD_PATH.read_text(encoding="utf-8").splitlines() if ln.strip()]
    tp = fp = fn = 0
    per_letter: list[dict] = []
    for row in gold:
        path = ROOT / row["source_file"]
        if not path.exists():
            print(f"  ! missing {row['source_file']}")
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        emitted = {m["ticker"] for m in lm.emitted_mentions(lm.match_letter(text, master))}
        truth = {str(t).upper() for t in row.get("true_tickers", [])}
        l_tp = emitted & truth
        l_fp = emitted - truth
        l_fn = truth - emitted
        tp += len(l_tp); fp += len(l_fp); fn += len(l_fn)
        per_letter.append({"file": row["source_file"], "fp": sorted(l_fp), "fn": sorted(l_fn)})
    precision = tp / (tp + fp) if (tp + fp) else 1.0
    recall = tp / (tp + fn) if (tp + fn) else 1.0
    print(f"labeled letters : {len(gold)}")
    print(f"TP/FP/FN        : {tp}/{fp}/{fn}")
    print(f"precision       : {precision:.3f}  (floor {PRECISION_FLOOR})")
    print(f"recall          : {recall:.3f}  (floor {RECALL_FLOOR})")
    for row in per_letter:
        if row["fp"] or row["fn"]:
            print(f"  {row['file']}")
            if row["fp"]:
                print(f"     false positives: {row['fp']}")
            if row["fn"]:
                print(f"     false negatives: {row['fn']}")
    ok = precision >= PRECISION_FLOOR and recall >= RECALL_FLOOR
    print("\nRESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 2


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", action="store_true", help="write per-pair review file")
    ap.add_argument("--gold", action="store_true", help="evaluate against gold.jsonl")
    args = ap.parse_args()
    master = load_master()
    if args.dump:
        dump(master)
        return 0
    if args.gold:
        return evaluate(master)
    summary(master)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
