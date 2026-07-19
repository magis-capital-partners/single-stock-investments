from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from index_valuation_library import build


class ValuationLibraryIndexTests(unittest.TestCase):
    def test_indexes_hashes_and_anchors_without_copying_corpus_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "letter.txt"
            path.write_text(
                "Owner earnings should be linked to reinvestment and incremental return on capital. "
                "A reverse DCF shows what the current price assumes about free cash flow.\n\n"
                "Unrelated paragraph long enough to be scanned but not classified into a valuation method.",
                encoding="utf-8",
            )
            result = build([Path(tmp)], maximum_files=10, maximum_hits_per_method=10)
        hits = result["candidates"]["owner_earnings_reinvestment_dcf"]
        self.assertEqual(result["files_scanned"], 1)
        self.assertEqual(hits[0]["page"], 1)
        self.assertIn("paragraph_sha256", hits[0])
        self.assertNotIn("excerpt", hits[0])


if __name__ == "__main__":
    unittest.main()
