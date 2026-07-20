from __future__ import annotations

import json
import unittest
from pathlib import Path

import ci_rebuild_profile

ROOT = Path(__file__).resolve().parents[2]


class ValuationAuthorityCutoverTests(unittest.TestCase):
    def test_valuation_pipeline_owned_by_power_zone_only(self):
        # Power Zone Universe is the single owner of the canonical valuation
        # pipeline; the nightly full rebuild must not duplicate it (nor use
        # the legacy ls-algo valuation path).
        steps = ci_rebuild_profile.PROFILES["full"]
        flattened = [" ".join(step) for step in steps]
        self.assertFalse(any("run_security_decision_pipeline.py" in step for step in flattened))
        self.assertFalse(any("run_ls_algo_valuation_pipeline.py" in step for step in flattened))
        power_zone = (ROOT / ".github" / "workflows" / "power-zone-universe.yml").read_text(encoding="utf-8")
        self.assertIn("run_security_decision_pipeline.py", power_zone)

    def test_full_rebuild_does_not_duplicate_activist_lane(self):
        # The dedicated 06:00 Data Pipeline activist job owns the activist slice.
        steps = ci_rebuild_profile.PROFILES["full"]
        flattened = [" ".join(step) for step in steps]
        for script in ("activist_triage.py", "build_activist_feed.py", "auto_resolve_filing_events.py"):
            self.assertFalse(any(script in step for step in flattened), script)

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

    def test_every_onboarding_entry_point_initializes_proof_first_valuation(self):
        onboard = (ROOT / "_system" / "scripts" / "onboard_ticker.py").read_text(encoding="utf-8")
        sp500 = (ROOT / "_system" / "scripts" / "darwin" / "bulk_sp500_onboard.py").read_text(encoding="utf-8")
        self.assertIn("initialize_proof_first_valuation(ticker, today)", onboard)
        self.assertIn("initialize_proof_first_valuation(ticker, today)", sp500)
        self.assertIn("automate_valuation_readiness.py", onboard)
        self.assertIn("--full-rerun", onboard)
        self.assertNotIn("run_security_decision_pipeline.py", onboard)


if __name__ == "__main__":
    unittest.main()
