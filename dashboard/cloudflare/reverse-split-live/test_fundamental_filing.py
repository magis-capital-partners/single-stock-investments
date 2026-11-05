import unittest
import os
import sys
import json
import base64
import subprocess
from pathlib import Path
from fundamental_filing import extract_document,metric_for

META = {'cik': '123', 'company': 'Example Research Ltd', 'form': '6-K', 'filed': '2026-08-15',
        'published_at': '2026-08-15T12:00:00Z', 'observed_at': '2026-11-05T17:00:00Z',
        'source_url': 'https://www.sec.gov/Archives/edgar/data/123/000000012326000001/report.htm',
        'source_sha256': 'a' * 64, 'currency_hint': 'USD', 'report_end': '2026-06-30'}


class FilingExtraction(unittest.TestCase):
    def test_partial_operating_flows_and_all_current_borrowings_do_not_change_the_registered_definitions(self):
        self.assertIsNone(metric_for('NetCashUsedInOperatingActivitiesContinuingOperations'))
        self.assertIsNone(metric_for('CurrentBorrowings'))
        self.assertEqual(metric_for('CurrentPortionOfNoncurrentBorrowings'),'current_debt')
    def test_comparative_currency_columns_do_not_mix_reported_and_translated_amounts(self):
        raw=b'<h2>Consolidated balance sheets</h2><p>Amounts in thousands</p><table><tr><th></th><th colspan="2">June 30, 2026</th></tr><tr><th></th><th>RMB</th><th>US$</th></tr><tr><td>Total assets</td><td>700</td><td>100</td></tr></table>'
        rows=extract_document(raw,META)['facts'];self.assertEqual({(r['currency'],r['value']) for r in rows},{('CNY',700000),('USD',100000)})
    def test_native_pdf_table_preserves_scale_and_the_cli_returns_clean_json(self):
        try:import pymupdf
        except ImportError:self.skipTest('PDF reader is installed in the financial collector workflow')
        doc=pymupdf.open();page=doc.new_page();page.insert_text((40,40),'Consolidated balance sheets. Amounts in thousands of U.S. dollars.')
        for x in [40,300,480]:page.draw_line((x,80),(x,180))
        for y in [80,110,145,180]:page.draw_line((40,y),(480,y))
        page.insert_text((310,100),'June 30, 2026');page.insert_text((50,135),'Total assets');page.insert_text((310,135),'100');page.insert_text((50,170),'Cash and cash equivalents');page.insert_text((310,170),'25')
        raw=doc.tobytes();rows=extract_document(raw,META)['facts'];doc.close();self.assertTrue(any(r['metric']=='total_assets' and r['value']==100000 and r['kind']=='pdf_table' for r in rows))
        output=subprocess.run([sys.executable,str(Path(__file__).with_name('fundamental_filing.py'))],input=json.dumps({'base64':base64.b64encode(raw).decode(),'meta':META}),text=True,capture_output=True,check=True,timeout=45)
        self.assertTrue(json.loads(output.stdout)['facts'])
    def test_scanned_financial_page_produces_reviewable_ocr_without_guessed_amounts(self):
        if not os.environ.get('TESSDATA_PREFIX'):
            if os.environ.get('RS_REQUIRE_OCR_TEST')=='true':self.fail('OCR language data must be configured in the financial collector')
            self.skipTest('OCR language data is required in the financial collector workflow')
        import pymupdf
        source=pymupdf.open();p=source.new_page();p.insert_text((40,60),'Example Research Ltd',fontsize=20);p.insert_text((40,100),'Consolidated balance sheets',fontsize=18);p.insert_text((40,140),'Amounts in U.S. dollars',fontsize=16);p.insert_text((40,180),'June 30, 2026',fontsize=16);p.insert_text((40,220),'Total assets          100',fontsize=18)
        image=p.get_pixmap(dpi=150).tobytes('png');scanned=pymupdf.open();page=scanned.new_page();page.insert_image(page.rect,stream=image);raw=scanned.tobytes();source.close();scanned.close()
        result=extract_document(raw,{**META,'require_company_identity':True,'require_table_identity':True});self.assertFalse(result['facts']);self.assertTrue(any(r['kind']=='ocr' and 'assets' in r['text'].lower() for r in result['candidates']))
    def test_custom_label_linkbase_and_standalone_instance(self):
        text='''<root xmlns:link="http://www.xbrl.org/2003/linkbase" xmlns:xlink="http://www.w3.org/1999/xlink"><link:labelLink><link:loc xlink:label="loc1" xlink:href="company.xsd#company_CustomCashFlow"/><link:label xlink:label="lab1">Net cash used in operating activities</link:label><link:labelArc xlink:from="loc1" xlink:to="lab1"/></link:labelLink></root><xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance" xmlns:company="https://company.example" xmlns:iso4217="http://www.xbrl.org/2003/iso4217"><xbrli:context id="c"><xbrli:entity><xbrli:identifier>123</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2026-01-01</xbrli:startDate><xbrli:endDate>2026-06-30</xbrli:endDate></xbrli:period></xbrli:context><xbrli:unit id="u"><xbrli:measure>iso4217:USD</xbrli:measure></xbrli:unit><company:CustomCashFlow contextRef="c" unitRef="u">1250</company:CustomCashFlow></xbrli:xbrl>'''
        rows=extract_document(text.encode(),META)['facts'];self.assertEqual(len(rows),1);self.assertEqual(rows[0]['metric'],'cfo');self.assertEqual(rows[0]['value'],-1250)
    def test_issuer_ir_identity_and_consolidation_are_required(self):
        raw=b'<h2>Another Company consolidated balance sheets</h2><p>USD</p><table><tr><th></th><th>June 30, 2026</th></tr><tr><td>Total assets</td><td>100</td></tr></table>'
        self.assertFalse(extract_document(raw,{**META,'require_company_identity':True})['facts'])
        self.assertFalse(extract_document(raw,{**META,'require_table_identity':True})['facts'])
        self.assertFalse(extract_document(raw.replace(b'consolidated',b'parent company'),META)['facts'])
    def test_inline_custom_concept_preserves_entity_scale_sign_and_context(self):
        html = '''<html><xbrli:context id="c"><xbrli:entity><xbrli:identifier>0000000123</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2026-01-01</xbrli:startDate><xbrli:endDate>2026-06-30</xbrli:endDate></xbrli:period></xbrli:context><xbrli:unit id="u"><xbrli:measure>iso4217:USD</xbrli:measure></xbrli:unit><ix:nonFraction name="example:NetCashUsedInOperatingActivities" contextRef="c" unitRef="u" scale="3" sign="-">1,250</ix:nonFraction></html>'''
        result = extract_document(html.encode(), META)
        row = next(r for r in result['facts'] if r['metric'] == 'cfo')
        self.assertEqual(row['value'], -1250000)
        self.assertEqual(row['start'], '2026-01-01')
        self.assertEqual(row['end'], '2026-06-30')
        self.assertEqual(row['currency'], 'USD')
        self.assertEqual(row['source_sha256'], 'a' * 64)
        self.assertTrue(row['locator'])
        self.assertFalse(extract_document(html.replace('0000000123', '0000000456').encode(), META)['facts'])

    def test_untagged_comparative_financial_tables_keep_correct_periods(self):
        html = '''<h2>Example Research Ltd consolidated statements of cash flows</h2><p>Amounts in thousands of U.S. dollars. Six months ended June 30.</p><table><tr><th></th><th>2026</th><th>2025</th></tr><tr><td>Net cash used in operating activities</td><td>(1,250)</td><td>(900)</td></tr></table><h2>Consolidated balance sheets</h2><p>Amounts in thousands of U.S. dollars</p><table><tr><th></th><th>June 30, 2026</th><th>December 31, 2025</th></tr><tr><td>Cash and cash equivalents</td><td>2,500</td><td>3,000</td></tr><tr><td>Total assets</td><td>6,000</td><td>7,000</td></tr><tr><td>Long-term debt, noncurrent</td><td>0</td><td>500</td></tr></table>'''
        result = extract_document(html.encode(), META)
        cfo = [r for r in result['facts'] if r['metric'] == 'cfo']
        self.assertEqual([(r['start'], r['end'], r['value']) for r in cfo],
                         [('2026-01-01', '2026-06-30', -1250000), ('2025-01-01', '2025-06-30', -900000)])
        cash = next(r for r in result['facts'] if r['metric'] == 'cash' and r['end'] == '2026-06-30')
        self.assertIsNone(cash['start'])
        self.assertEqual(cash['value'], 2500000)
        debt = next(r for r in result['facts'] if r['metric'] == 'long_term_debt' and r['end'] == '2026-06-30')
        self.assertTrue(debt['explicit_zero'])

    def test_unknown_units_empty_cells_and_segment_facts_cannot_become_verified_values(self):
        html = '''<h2>Example Research Ltd consolidated balance sheets</h2><table><tr><td></td><td>June 30, 2026</td></tr><tr><td>Long-term debt, noncurrent</td><td>—</td></tr><tr><td>Cash and cash equivalents</td><td>500</td></tr></table>'''
        result = extract_document(html.encode(), {**META, 'currency_hint': None})
        self.assertFalse(result['facts'])
        self.assertTrue(result['issues'])

    def test_pro_forma_tables_and_executable_markup_are_not_financial_evidence(self):
        html = '''<script>Cash and cash equivalents 9000000</script><h2>Unaudited pro forma combined balance sheet</h2><p>U.S. dollars</p><table><tr><td></td><td>June 30, 2026</td></tr><tr><td>Cash and cash equivalents</td><td>9,000,000</td></tr></table>'''
        self.assertFalse(extract_document(html.encode(), META)['facts'])


if __name__ == '__main__':
    unittest.main()
