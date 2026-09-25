#!/usr/bin/env python3
"""build_research_memory: a rebuild from incomplete inputs may not shrink the memory.

Every evening the drive lane committed ~1,100 claims over the ~12,000 that
intake-full had written that morning (research_memory_evidence.json 15.4MB ->
1.4MB; e.g. 376a075ba45, 04d2d41986f), because its insights profile built the
memory before build_insights had written the gitignored insights.json.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_research_memory as brm  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


def memory(claims: int, *, insight_rows: int, tickers: int = 800, present: int = 800) -> dict:
    return {
        "summary": {"claim_count": claims, "source_count": 1, "ownership_record_count": 0},
        "build_inputs": {
            "insight_rows": insight_rows,
            "tickers": tickers,
            "ticker_dirs_present": present,
        },
    }


def evidence(count: int) -> dict:
    return {"evidence_ledger": [{"claim_id": f"c{i}"} for i in range(count)]}


class SparseShrinkReasonTests(unittest.TestCase):
    PRIOR_MEMORY = {"summary": {"claim_count": 12000}}
    PRIOR_EVIDENCE = evidence(15000)

    def test_missing_insights_and_a_big_drop_refuses(self) -> None:
        reason = brm.sparse_shrink_reason(
            memory(1116, insight_rows=0), evidence(1500), self.PRIOR_MEMORY, self.PRIOR_EVIDENCE
        )
        self.assertEqual(reason, "claims 12000->1116")

    def test_thin_ticker_tree_counts_as_sparse(self) -> None:
        reason = brm.sparse_shrink_reason(
            memory(12000, insight_rows=9000, present=40), evidence(2000),
            self.PRIOR_MEMORY, self.PRIOR_EVIDENCE,
        )
        self.assertEqual(reason, "evidence 15000->2000")

    def test_small_drop_in_sparse_mode_is_allowed(self) -> None:
        self.assertIsNone(
            brm.sparse_shrink_reason(
                memory(10000, insight_rows=0), evidence(13000), self.PRIOR_MEMORY, self.PRIOR_EVIDENCE
            )
        )

    def test_full_inputs_may_shrink(self) -> None:
        self.assertIsNone(
            brm.sparse_shrink_reason(
                memory(3000, insight_rows=9000), evidence(3000), self.PRIOR_MEMORY, self.PRIOR_EVIDENCE
            )
        )

    def test_no_meaningful_prior_is_not_judged(self) -> None:
        self.assertIsNone(
            brm.sparse_shrink_reason(memory(5, insight_rows=0), evidence(5), {}, {})
        )


class MainKeepsThePriorTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        data = Path(self._tmp.name)
        self.output = data / "research_memory.json"
        self.evidence_output = data / "research_memory_evidence.json"
        self.output.write_text(json.dumps({"summary": {"claim_count": 12000}}), encoding="utf-8")
        self.evidence_output.write_text(json.dumps(evidence(15000)), encoding="utf-8")
        self._patches = [
            mock.patch.object(brm, "ROOT", data),
            mock.patch.object(brm, "DATA_DIR", data),
            mock.patch.object(brm, "OUTPUT", self.output),
            mock.patch.object(brm, "EVIDENCE_OUTPUT", self.evidence_output),
            mock.patch.object(
                brm, "build", return_value=(memory(1116, insight_rows=0), evidence(1500))
            ),
        ]
        for patch in self._patches:
            patch.start()

    def tearDown(self) -> None:
        for patch in reversed(self._patches):
            patch.stop()
        self._tmp.cleanup()

    def _claims(self) -> int:
        return json.loads(self.output.read_text(encoding="utf-8"))["summary"]["claim_count"]

    def test_sparse_shrink_keeps_the_committed_files(self) -> None:
        with mock.patch.dict(os.environ, {"RESEARCH_MEMORY_ALLOW_SHRINK": ""}):
            brm.main()
        self.assertEqual(self._claims(), 12000)
        ledger = json.loads(self.evidence_output.read_text(encoding="utf-8"))["evidence_ledger"]
        self.assertEqual(len(ledger), 15000)

    def test_explicit_override_writes(self) -> None:
        with mock.patch.dict(os.environ, {"RESEARCH_MEMORY_ALLOW_SHRINK": "1"}):
            brm.main()
        self.assertEqual(self._claims(), 1116)


class InsightsProfileOrderTests(unittest.TestCase):
    def test_research_memory_is_built_after_insights(self) -> None:
        import ci_rebuild_profile

        steps = [step[0] for step in ci_rebuild_profile.PROFILES["insights"]]
        memory_at = steps.index("_system/scripts/build_research_memory.py")
        insights_at = steps.index("_system/scripts/build_insights.py")
        self.assertGreater(memory_at, insights_at)


if __name__ == "__main__":
    raise SystemExit(unittest.main())
