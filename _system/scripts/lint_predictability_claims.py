#!/usr/bin/env python3
"""Lint Magis / World Model claim language against predictability bans.

  python _system/scripts/lint_predictability_claims.py
  python _system/scripts/lint_predictability_claims.py --strict

Warn by default (exit 0 with findings). --strict exits 1 on hits.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import predictability as pred  # noqa: E402
import world_model_common as wm  # noqa: E402

ROOT = wm.ROOT


def scan_text(path: Path, text: str) -> list[str]:
    hits = pred.find_banned_phrases(text)
    return [f"{path.relative_to(ROOT).as_posix()}: {h}" for h in hits]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--strict",
        action="store_true",
        help="Exit 1 when banned phrases are found (default: warn only)",
    )
    args = ap.parse_args()

    findings: list[str] = []

    strip_path = wm.DASHBOARD_WORLD_MODEL
    if strip_path.exists():
        doc = wm.load_json(strip_path)
        strip = doc.get("strip") or {}
        # Context rows must never be P4
        for key in ("broken", "stale", "passes", "unchecked", "prediction_cards", "expert_horizons", "superorgs"):
            for row in strip.get(key) or []:
                if not isinstance(row, dict):
                    continue
                cls = row.get("predictability_class")
                if cls == "P4_allocation":
                    findings.append(
                        f"{strip_path.relative_to(ROOT).as_posix()}: "
                        f"{key} row has forbidden predictability_class=P4_allocation"
                    )
        for h in strip.get("expert_horizons") or []:
            if (h or {}).get("predictability_class") not in (None, "P0_ill_defined"):
                findings.append(
                    f"{strip_path.relative_to(ROOT).as_posix()}: "
                    f"horizon {(h or {}).get('domain')} must be P0_ill_defined"
                )
        blob = " ".join([
            str(strip.get("summary") or ""),
            str(strip.get("ev_stance") or ""),
            str(strip.get("disclaimer") or ""),
        ])
        findings.extend(scan_text(strip_path, blob))

    # Deep-dive World Model context sections (recent)
    for path in sorted(ROOT.glob("*/research/deep_dive_*.md"))[-80:]:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if "World Model" not in text and "world model" not in text.lower():
            continue
        # Only scan the World Model subsection when present
        lower = text.lower()
        idx = lower.find("world model")
        chunk = text[idx: idx + 4000] if idx >= 0 else text[:2000]
        findings.extend(scan_text(path, chunk))

    if not findings:
        print("lint_predictability_claims: ok")
        return 0

    print(f"lint_predictability_claims: {len(findings)} finding(s)")
    for line in findings[:80]:
        print(f"  - {line}")
    if len(findings) > 80:
        print(f"  ... {len(findings) - 80} more")
    return 1 if args.strict else 0


if __name__ == "__main__":
    raise SystemExit(main())
