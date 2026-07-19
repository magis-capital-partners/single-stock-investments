from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import download_us_investor_docs as downloader


class DownloadManifestTests(unittest.TestCase):
    def test_manifest_paths_are_repository_relative(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_root = downloader.ROOT
            downloader.ROOT = Path(tmp)
            try:
                path = downloader.ROOT / "MSB/investor-documents/sec-edgar/filing.htm"
                self.assertEqual(
                    downloader.manifest_path(path),
                    "MSB/investor-documents/sec-edgar/filing.htm",
                )
            finally:
                downloader.ROOT = old_root


if __name__ == "__main__":
    unittest.main()
