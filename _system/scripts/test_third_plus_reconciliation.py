import unittest
from third_plus_reconciliation_parse import parse_document, value
from third_plus_reconciliation_financing import extract, money, paragraphs
HEADER='''<html><body><xbrli:context id="c25"><xbrli:entity><xbrli:identifier>1</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2025-01-01</xbrli:startDate><xbrli:endDate>2025-03-31</xbrli:endDate></xbrli:period></xbrli:context><xbrli:context id="c24"><xbrli:entity><xbrli:identifier>1</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2024-01-01</xbrli:startDate><xbrli:endDate>2024-03-31</xbrli:endDate></xbrli:period></xbrli:context><xbrli:unit id="usd"><xbrli:measure>iso4217:USD</xbrli:measure></xbrli:unit>'''
def ix(tag,context,number):return '<ix:nonFraction name="us-gaap:'+tag+'" contextRef="'+context+'" unitRef="usd">'+number+'</ix:nonFraction>'
class ExtractionTests(unittest.TestCase):
    def test_numeric_scale_sign_and_missing(self):
        self.assertEqual(value('1,234',{'scale':'3','sign':'-'}),-1234000)
        self.assertIsNone(value('',{}))
        self.assertIsNone(value('1',{'xsi:nil':'true'}))
        self.assertEqual(value('—',{}),0)
    def test_explicit_zero_cell_uses_repeated_same_table_context(self):
        rows=''
        for tag in ('NetCashProvidedByUsedInOperatingActivitiesContinuingOperations','NetCashProvidedByUsedInInvestingActivities','NetCashProvidedByUsedInFinancingActivities'):
            rows+='<tr><td>Reported</td><td>'+ix(tag,'c25','1')+'</td><td>'+ix(tag,'c24','2')+'</td></tr>'
        rows+='<tr><td>Discontinued</td><td>—</td><td>'+ix('CashProvidedByUsedInOperatingActivitiesDiscontinuedOperations','c24','3')+'</td></tr>'
        doc=parse_document(HEADER+'<table>'+rows+'</table></body></html>',1,'a')
        zero=[f for f in doc['facts'] if f.get('derived_from_literal_zero_cell')]
        self.assertEqual(len(zero),1);self.assertEqual(zero[0]['value'],0);self.assertEqual(zero[0]['end'],'2025-03-31')
        blank=parse_document(HEADER+'<table>'+rows.replace('<td>—</td>','<td></td>')+'</table></body></html>',1,'a')
        self.assertFalse(any(f.get('derived_from_literal_zero_cell') for f in blank['facts']))
    def test_literal_issued_and_outstanding_caption_has_dates_and_class(self):
        text='<html><table><tr><td>March 31, 2025 December 31, 2024</td></tr><tr><td>Common stock, par value $0.0001; 2,232,578 and 1,970,615 Class A shares issued and outstanding, respectively</td></tr></table></html>'
        facts=parse_document(text,1,'a')['facts']
        self.assertEqual([(f['end'],f['value']) for f in facts],[('2025-03-31',2232578),('2024-12-31',1970615)])
        self.assertEqual(facts[0]['dimensions'][0]['member'],'us-gaap:CommonClassAMember')
    def test_plain_issued_count_is_not_relabeled_outstanding(self):
        doc=parse_document('<html><tr><td>Common stock, shares issued: 690,022 at December 31, 2025</td></tr></html>',1,'a')
        self.assertFalse(doc['facts'])
    def test_decimal_cash_proceeds_are_not_split_at_the_decimal(self):
        result=extract('The Company issued and sold common stock. The Company received net proceeds of $3.8 million from the offering.')
        self.assertTrue(any(c['state']=='actual_sale_or_cash_receipt_candidate' for c in result))
        self.assertTrue(any(a['value']==3800000 for c in result for a in c['amounts']))
    def test_future_sale_is_not_an_actual_completed_sale(self):
        result=extract('The common stock will be issued and sold pursuant to the registration statement.')
        self.assertTrue(result);self.assertTrue(all(c['state']=='terms_or_other_context' for c in result))
    def test_malformed_million_suffix_is_flagged_not_promoted_to_cash(self):
        result=money('The gross proceeds were approximately $4,000,000 million.')
        self.assertEqual(result[0]['value'],None);self.assertEqual(result[0]['classification'],'inconsistent_numeric_scale_requires_review')
    def test_agent_expense_is_not_gross_proceeds(self):
        result=money('The agent received 7% of gross proceeds and reimbursement of $75,000 of expenses.')
        self.assertNotEqual(result[0]['classification'],'gross_proceeds')
    def test_full_table_body_is_scanned_even_when_div_paragraphs_exist(self):
        parts=paragraphs('<html><div>Header text and administrative details for the company.</div><table><tr><td>The Company closed the common stock offering on May 1, 2025.</td></tr></table></html>')
        self.assertTrue(any('closed the common stock offering' in p for p in parts))
    def test_additional_closing_is_captured(self):
        rows=extract('The Company issued convertible notes. On February 13, 2026, the parties held an additional closing. The convertible note was issued for cash.')
        self.assertTrue(any('additional closing' in c['sentence'] and c['state']=='explicit_completion_candidate' for c in rows))
if __name__=='__main__':unittest.main()
