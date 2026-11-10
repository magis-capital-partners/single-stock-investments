import unittest
from announcement_text import extract
try:import pymupdf
except ImportError:pymupdf=None
@unittest.skipUnless(pymupdf,'optional local PDF dependency; installed in the live collector')
class AnnouncementTextTests(unittest.TestCase):
    def test_original_pdf_text_is_complete_and_keeps_split_terms(self):
        doc=pymupdf.open();page=doc.new_page();page.insert_text((72,72),'Example announces a 1-for-10 reverse stock split effective November 10, 2026.')
        result=extract(doc.tobytes());doc.close();self.assertTrue(result['complete']);self.assertIn('1-for-10',result['text']);self.assertEqual(result['pages'],1)
    def test_empty_pdf_cannot_be_reported_as_inspected_text(self):
        doc=pymupdf.open();doc.new_page()
        with self.assertRaises(ValueError):extract(doc.tobytes())
        doc.close()
    def test_non_pdf_input_is_rejected(self):
        with self.assertRaises(ValueError):extract(b'<html>not a PDF</html>')
    def test_graphic_pages_return_review_candidates_without_becoming_verified_text(self):
        doc=pymupdf.open();page=doc.new_page();page.draw_rect(pymupdf.Rect(50,50,300,300));page.insert_text((72,72),'Cover')
        result=extract(doc.tobytes());doc.close()
        self.assertFalse(result['complete']);self.assertEqual(result['review_pages'],[1]);self.assertFalse(result['OCR_admitted_to_signals'])
    def test_extended_primary_reader_has_its_own_page_limit_and_standard_remains_strict(self):
        doc=pymupdf.open()
        for i in range(121):
            page=doc.new_page();page.insert_text((72,72),'Readable original primary disclosure page with enough native text '+str(i+1))
        raw=doc.tobytes();doc.close()
        with self.assertRaises(ValueError):extract(raw)
        result=extract(raw,'external_primary_report');self.assertEqual(result['pages'],121);self.assertTrue(result['complete'])
        with self.assertRaises(ValueError):extract(raw,'unbounded')
    def test_extended_reader_still_rejects_over_limit_bytes(self):
        with self.assertRaises(ValueError):extract(b'%PDF-'+b' '*(48*1024*1024),'external_primary_report')
if __name__=='__main__':unittest.main()
