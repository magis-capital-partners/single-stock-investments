from __future__ import annotations

import json
import unittest
from pathlib import Path

import ci_rebuild_profile

ROOT = Path(__file__).resolve().parents[2]


class ValuationAuthorityCutoverTests(unittest.TestCase):
    def test_full_rebuild_uses_canonical_portfolio_pipeline(self):
        steps = ci_rebuild_profile.PROFILES["full"]
        flattened = [" ".join(step) for step in steps]
        self.assertTrue(any("run_security_decision_pipeline.py" in step for step in flattened))
        self.assertFalse(any("run_ls_algo_valuation_pipeline.py" in step for step in flattened))

    def test_active_mandates_prefer_committee_policy(self):
        for name in ("darwin_mandate.json", "darwin_mandate_roth.json", "darwin_mandate_taxable.json"):
            doc = json.loads((ROOT / "_system" / "portfolio" / name).read_text(encoding="utf-8"))
            self.assertEqual((doc.get("mandate") or {}).get("preferred_policy"), "research_committee", name)

    def test_serving_readers_use_decision_authority(self):
        for name in (
            "build_dashboard_data.py",
            "sync_classification.py",
            "refresh_deep_dive_v2.py",
            "darwin/features.py",
        ):
            source = (ROOT / "_system" / "scripts" / name).read_text(encoding="utf-8")
            self.assertIn("decision_authority", source, name)


if __name__ == "__main__":
    unittest.main()
