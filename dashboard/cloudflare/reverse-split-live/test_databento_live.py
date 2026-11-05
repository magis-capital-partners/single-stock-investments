"""Offline transport normalization. No SDK session or market-data request."""
import unittest
from types import SimpleNamespace
from databento_live import normalize_record


class NormalizationTest(unittest.TestCase):
    def record(self, **kw):
        level = SimpleNamespace(bid_px=10_000_000_000, ask_px=10_100_000_000, bid_sz=7, ask_sz=13)
        values = dict(levels=[level], flags=0, ts_recv=1793804400000000000, ts_event=1793804399999999999, instrument_id=123)
        values.update(kw)
        return SimpleNamespace(**values)

    def test_fixed_prices_share_sizes_and_original_clock(self):
        q = normalize_record(self.record(), 'QA', '2026-11-04T15:00:00Z')
        self.assertEqual(q['bid'], 10)
        self.assertEqual(q['ask_size'], 13)
        self.assertEqual(q['ts_recv_ns'], '1793804400000000000')

    def test_bad_book_or_capture_time_is_rejected(self):
        for flags in (4, 8, 12):
            self.assertIsNone(normalize_record(self.record(flags=flags), 'QA', 'now'))
        for field, value in [('bid_px', 2**63-1), ('ask_px', 0), ('bid_sz', 0), ('ask_sz', 2**32-1)]:
            record = self.record()
            setattr(record.levels[0], field, value)
            self.assertIsNone(normalize_record(record, 'QA', 'now'))


if __name__ == '__main__':
    unittest.main()
