import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from xbrl_context import contextual_metrics

HTML = '''<html xmlns:ix="x"><ix:resources>
<xbrli:context id="prior"><xbrli:entity><xbrli:identifier>2000638</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2024-01-01</xbrli:startDate><xbrli:endDate>2024-12-31</xbrli:endDate></xbrli:period></xbrli:context>
<xbrli:context id="current"><xbrli:entity><xbrli:identifier>2000638</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2025-01-01</xbrli:startDate><xbrli:endDate>2025-12-31</xbrli:endDate></xbrli:period></xbrli:context>
<xbrli:context id="segment"><xbrli:entity><xbrli:identifier>2000638</xbrli:identifier><xbrli:segment><xbrldi:explicitMember>Segment</xbrldi:explicitMember></xbrli:segment></xbrli:entity><xbrli:period><xbrli:startDate>2025-01-01</xbrli:startDate><xbrli:endDate>2025-12-31</xbrli:endDate></xbrli:period></xbrli:context>
<xbrli:unit id="usd"><xbrli:measure>iso4217:USD</xbrli:measure></xbrli:unit>
</ix:resources>
<ix:nonFraction name="us-gaap:NetIncomeLoss" contextRef="prior" unitRef="usd">34,418,803</ix:nonFraction>
<ix:nonFraction name="us-gaap:NetIncomeLoss" contextRef="segment" unitRef="usd" scale="6">999</ix:nonFraction>
<ix:nonFraction name="us-gaap:NetIncomeLoss" contextRef="current" unitRef="usd" sign="-" scale="3">2,315,493.008</ix:nonFraction></html>'''

class XbrlTests(unittest.TestCase):
    def test_sign_scale_chronology_and_consolidation(self):
        m = contextual_metrics(HTML, expected_cik='0002000638')['net_income']
        self.assertAlmostEqual(m['current'], -2315493008)
        self.assertEqual(m['prior'], 34418803)
        self.assertEqual(m['unit'], 'USD')
        self.assertEqual(m['current_period']['end'], '2025-12-31')
        self.assertEqual(m['parser_flags'], [])

    def test_conflicting_contexts_cannot_be_high_confidence(self):
        conflicting = HTML.replace('</html>', '<ix:nonFraction name="us-gaap:NetIncomeLoss" contextRef="current" unitRef="usd">12</ix:nonFraction></html>')
        self.assertIn('conflicting_context_values', contextual_metrics(conflicting)['net_income']['parser_flags'])

    def test_partial_inception_year_is_not_comparable(self):
        html = HTML.replace('2024-01-01', '2024-05-21')
        self.assertIn('non_comparable_periods', contextual_metrics(html)['net_income']['parser_flags'])

    def test_wrong_issuer_is_flagged(self):
        self.assertIn('entity_context_mismatch', contextual_metrics(HTML, expected_cik='123')['net_income']['parser_flags'])

if __name__ == '__main__':
    unittest.main()
