import sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from examples.copy_fit import _solve_copy_fit
from examples.pdf_routing import PdfConversionDecision,pdf_scan_risk
from examples.literal_guard import protect,restore

class Examples(unittest.TestCase):
    def test_short_text_preserves_font(self):
        r=_solve_copy_fit('DN 50',100,20,12)
        self.assertTrue(r.fits); self.assertEqual((r.text,r.font_size,r.width_scale),('DN 50',12,1))
    def test_impossible_box_is_explicit_failure(self):
        r=_solve_copy_fit('LONGUNBROKENTOKEN'*10,10,5,12)
        self.assertFalse(r.fits); self.assertGreaterEqual(r.font_size,11.5)
    def test_scan_routing_thresholds(self):
        for pages,expected in [(5,True),(6,False),(20,False)]:
            with self.subTest(pages=pages):
                r=pdf_scan_risk(PdfConversionDecision('ocr','scan',pages,0,0))
                self.assertEqual(r.sync_recommended,expected)
        self.assertEqual(pdf_scan_risk(PdfConversionDecision('direct','native',100,100,4000)).estimated_ocr_pages,0)
    def test_symbols_preserved_without_unicode_folding(self):
        s='Diameter Ø12 ±0.10 mm'; p=protect(s,[(9,len(s))])
        self.assertEqual(restore(p,p.request.replace('Diameter','Bore')),('Bore Ø12 ±0.10 mm',True))
    def test_dropped_duplicate_or_mutated_placeholder_fails_closed(self):
        s='A Ø12'; p=protect(s,[(2,len(s))])
        for candidate in ['A 12',p.request+p.tokens[0],p.request.replace('__LITERAL_','__BROKEN_')]:
            with self.subTest(candidate=candidate): self.assertEqual(restore(p,candidate),(s,False))
    def test_overlap_rejected(self):
        with self.assertRaises(ValueError): protect('abcdef',[(0,3),(2,5)])

if __name__=='__main__':unittest.main()
