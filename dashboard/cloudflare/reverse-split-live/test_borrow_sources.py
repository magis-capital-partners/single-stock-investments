import unittest
from public_borrow import parse
from flex_borrow import normalize
from databento_live import BookCredits


class BorrowSourcesTest(unittest.TestCase):
    def test_public_fee_percent_to_fraction_and_missing_is_not_zero(self):
        raw = b'#BOF|2026.11.05|10:00:00\n#SYM|AVAILABLE|FEERATE|\nQA|>1000|125.0|\nQB|0|NA|\n#EOF|2\n'
        result = parse(raw, {'QA', 'QB'}, '2026-11-05T15:01:00+00:00')
        self.assertEqual(result['rows'][0]['apr'], 1.25)
        self.assertTrue(result['rows'][0]['available_at_least'])
        self.assertIsNone(result['rows'][1]['apr'])
        self.assertFalse(result['locate_approved'])
        with self.assertRaises(ValueError):
            parse(raw.replace(b'#EOF|2', b'#EOF|3'), {'QA'}, '2026-11-05T15:01:00+00:00')

    def test_flex_actual_position_reference_is_redacted_and_not_a_paper_charge(self):
        raw = b'<FlexQueryResponse><FlexStatement accountId="QA_PRIVATE"><BorrowFeeDetails><BorrowFeeDetail symbol="QA" currency="USD" valueDate="20261104" quantity="100" price="10" borrowFeeRate="150" borrowFee="-4.50"/></BorrowFeeDetails></FlexStatement></FlexQueryResponse>'
        result = normalize(raw, '2026-11-05T12:00:00+00:00')
        row = result['rows'][0]
        self.assertEqual(row['apr'], 1.5)
        self.assertEqual(row['components'][0]['reported_fee_raw'], '-4.50')
        self.assertTrue(row['actually_charged'])
        self.assertFalse(row['shadow_fee_actually_charged'])
        self.assertNotIn('QA_PRIVATE', str(result))
        with self.assertRaises(ValueError):
            normalize(raw.replace(b'BorrowFeeDetails', b'UnknownSection'), '2026-11-05T12:00:00+00:00')
        with self.assertRaises(ValueError):
            normalize(b'<!DOCTYPE a>'+raw, '2026-11-05T12:00:00+00:00')

    def test_book_positive_changes_are_measured_before_throttling(self):
        credits = BookCredits()
        row = {'ticker': 'QA', 'bid': 10, 'ask': 11, 'bid_size': 100, 'ask_size': 50}
        self.assertEqual(credits.update(row)['book_credit']['short'], 100)
        self.assertEqual(credits.update(row)['book_credit']['short'], 100)
        credits.update({**row, 'bid_size': 20})
        self.assertEqual(credits.update(row)['book_credit']['short'], 180)
        self.assertNotEqual(credits.epoch, BookCredits().epoch)

    def test_large_ytd_report_is_filtered_and_row_identity_survives_later_downloads(self):
        detail=b'<HardToBorrowDetail symbol="QA" currency="USD" valueDate="20261104" quantity="100" price="10" conid="12345" borrowFeeRate="150" borrowFee="-4.50"/>'
        raw=b'<FlexQueryResponse><!--'+b'x'*8_000_001+b'--><FlexStatement accountId="QA_PRIVATE" toDate="20261104"><HardToBorrowDetails>'+detail+detail+b'</HardToBorrowDetails></FlexStatement></FlexQueryResponse>'
        first=normalize(raw,'2026-11-05T12:00:00+00:00',{'QA'})
        second=normalize(raw.replace(b'<!--',b'<!--different-download-'),'2026-11-06T12:00:00+00:00',{'QA'})
        self.assertEqual(first['rows'][0]['observation_key'],second['rows'][0]['observation_key'])
        self.assertEqual(len(first['rows']),1)
        self.assertEqual(first['rows'][0]['component_count'],2)
        self.assertNotEqual(first['rows'][0]['components'][0]['observation_key'],first['rows'][0]['components'][1]['observation_key'])
        self.assertEqual(first['report_to_date'],'2026-11-04')
        self.assertEqual(normalize(raw,'2026-11-05T12:00:00+00:00',{'OTHER'})['rows'],[])
