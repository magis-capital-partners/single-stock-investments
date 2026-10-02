"""Self-test for the vendor loader on synthetic data (no network, temp dirs only)."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import fear_vec  # noqa: E402
import vendor_bars  # noqa: E402


def synthetic(n=900, start="2004-01-02", drift=-0.0008, seed=1):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(start, periods=n).strftime("%Y-%m-%d")
    r = drift + 0.02 * rng.standard_normal(n)
    close = 50 * np.exp(np.cumsum(r))
    return pd.DataFrame({"date": dates, "open": close * 0.999, "high": close * 1.01, "low": close * 0.99,
                         "close": close, "volume": rng.integers(1e5, 1e6, n)})


class VendorLoaderTest(unittest.TestCase):
    def test_loads_and_appends_delisting_return(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            vdir, bars = tmp / "vendor", tmp / "bars"
            vdir.mkdir()
            synthetic().to_csv(vdir / "FAILCO.csv", index=False)
            synthetic(seed=2, drift=0.0003).to_parquet(vdir / "TAKEN.parquet", index=False)
            pd.DataFrame({"ticker": ["FAILCO", "TAKEN"], "delist_date": ["2007-06-01", "2007-06-01"],
                          "delisting_return": [-0.9, 0.0], "reason": ["bankruptcy", "acquired"]}).to_csv(vdir / "delistings.csv", index=False)
            res = vendor_bars.load(vdir, manifest_path=tmp / "manifest.json", bars_dir=bars)
            self.assertEqual(res["errors"], {})
            self.assertEqual(sorted(res["loaded"]), ["FAILCO.VENDOR", "TAKEN.VENDOR"])
            man = json.loads((tmp / "manifest.json").read_text())
            self.assertEqual(man["FAILCO.VENDOR"]["kind"], "vendor_delisted")
            raw = pd.read_parquet(bars / "FAILCO.VENDOR.parquet")
            rows = fear_vec.production_rows(raw)
            # terminal bar carries the -90% delisting return
            self.assertAlmostEqual(rows["close"].iloc[-1] / rows["close"].iloc[-2], 0.1, places=6)
            # and the replay runs on it
            sig = fear_vec.compute(rows, None)
            self.assertEqual(len(sig), len(rows))
            self.assertTrue(np.isfinite(sig["panic"].iloc[-1]))


if __name__ == "__main__":
    unittest.main()
