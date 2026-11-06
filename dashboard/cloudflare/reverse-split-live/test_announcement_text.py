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
if __name__=='__main__':unittest.main()
