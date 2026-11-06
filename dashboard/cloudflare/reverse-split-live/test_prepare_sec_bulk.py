import unittest
from prepare_sec_bulk import compact

class CompactTests(unittest.TestCase):
    def test_keeps_required_prior_comparatives_and_preserves_filing_provenance(self):
        rows=[{'end':str(year)+'-12-31','val':year,'filed':str(year+1)+'-03-01','accn':'source-'+str(year),'form':'10-K'} for year in range(2017,2027)]
        raw={'cik':123,'facts':{'us-gaap':{'Assets':{'units':{'USD':rows,'shares':rows}},'UnrelatedConcept':{'units':{'USD':rows}}}}}
        value=compact(raw,{'Assets'},'2023-01-01');facts=value['facts']['us-gaap']
        self.assertEqual(list(facts),['Assets']);self.assertEqual(list(facts['Assets']['units']),['USD'])
        self.assertEqual(len(facts['Assets']['units']['USD']),4)
        self.assertEqual(facts['Assets']['units']['USD'][-1]['accn'],'source-2026')
    def test_old_issuer_keeps_last_three_dates_but_does_not_invent_current_data(self):
        raw={'cik':123,'facts':{'ifrs-full':{'Assets':{'units':{'USD':[{'end':str(y)+'-12-31','val':0} for y in range(2016,2020)]}}}}}
        rows=compact(raw,{'Assets'},'2023-01-01')['facts']['ifrs-full']['Assets']['units']['USD']
        self.assertEqual([r['end'] for r in rows],['2017-12-31','2018-12-31','2019-12-31']);self.assertEqual(rows[-1]['val'],0)
    def test_absent_financial_statements_stay_absent(self):
        self.assertEqual(compact({'cik':123,'facts':{}},{'Assets'},'2023-01-01'),{'cik':123,'entityName':None,'facts':{}})

if __name__=='__main__':unittest.main()
