from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import build_research_agent_manifest
import ir_adapter_gate


class AgentEvidenceGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, relative: str, value) -> None:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(value) if isinstance(value, (dict, list)) else str(value)
        path.write_text(text, encoding="utf-8")

    def test_research_hash_ignores_dispatch_reason(self):
        self.write("AAA/investor-documents/DOWNLOAD_MANIFEST.json", [{"filingDate": "2026-07-18"}])
        with patch.object(build_research_agent_manifest, "ROOT", self.root):
            first = build_research_agent_manifest.build_manifest("AAA", "new_documents")
            second = build_research_agent_manifest.build_manifest("AAA", "manual_material_change")
        self.assertTrue(first["ready"])
        self.assertEqual(first["evidence_hash"], second["evidence_hash"])

    def test_working_ir_adapter_suppresses_vicki(self):
        self.write("AAA/.onboard_status.json", {"download_detail": "ir_gap"})
        self.write("AAA/investor-documents/ir_adapter.json", {"deterministic_status": "working"})
        with patch.object(ir_adapter_gate, "ROOT", self.root):
            result = ir_adapter_gate.evaluate("AAA")
        self.assertFalse(result["eligible"])
        self.assertEqual(result["reason"], "deterministic_adapter_working")

    def test_failed_adapter_admits_vicki(self):
        self.write("AAA/.onboard_status.json", {"download_detail": "ir_gap"})
        self.write("AAA/investor-documents/ir_adapter.json", {"deterministic_status": "failed"})
        with patch.object(ir_adapter_gate, "ROOT", self.root):
            result = ir_adapter_gate.evaluate("AAA")
        self.assertTrue(result["eligible"])
        self.assertEqual(result["reason"], "adapter_failed")


if __name__ == "__main__":
    unittest.main()
