"""Offline transport normalization. No SDK session or market-data request."""
import unittest
from types import SimpleNamespace
import databento_live
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
        self.assertFalse(q['mapping_verified'])
        verified = normalize_record(self.record(), 'QA', '2026-11-04T15:00:00Z', mapping_verified=True)
        self.assertTrue(verified['mapping_verified'])
        self.assertEqual(verified['raw_symbol'], 'QA')
        self.assertEqual(verified['instrument_id'], 123)

    def test_bad_book_or_capture_time_is_rejected(self):
        for flags in (4, 8, 12):
            self.assertIsNone(normalize_record(self.record(flags=flags), 'QA', 'now'))
        for field, value in [('bid_px', 2**63-1), ('ask_px', 0), ('bid_sz', 0), ('ask_sz', 2**32-1)]:
            record = self.record()
            setattr(record.levels[0], field, value)
            self.assertIsNone(normalize_record(record, 'QA', 'now'))


    def test_recovered_book_is_forwarded_immediately_after_invalidation(self):
        forwarded = []
        emitted = {}
        book = {"kind": "quote", "ticker": "QA"}
        send = databento_live.forward_book
        for value, at in ((book, 1.0), (None, 1.05), (None, 1.08), (book, 1.1), (book, 1.13)):
            send(value, "QA", emitted, forwarded.append, at)
        self.assertEqual(forwarded, [book, {"kind": "invalidate", "ticker": "QA"}, book])

    def test_reads_sdk_error_text_and_only_marks_the_exact_symbol_error_as_scoped(self):
        classify = databento_live.classify_vendor_error
        self.assertEqual(classify(SimpleNamespace(code=4, err="unresolved"), 4), "symbol_resolution")
        self.assertEqual(classify(SimpleNamespace(code=0, err="permission rejected"), 4), "access_rejected")
        self.assertEqual(classify(SimpleNamespace(code=0, err="symbol service failed"), 4), "vendor_subscription_error")


if __name__ == '__main__':
    unittest.main()
