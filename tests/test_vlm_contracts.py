import json
import unittest

from examples.vlm_evidence import attach_vlm_evidence, compose_reviewed_annotations
from examples.vlm_geometry import qwen_page, table_geometry


class VLMContracts(unittest.TestCase):
    def test_evidence_never_rewrites_or_accepts_source(self):
        source = {'unique_regions': [{'unique_region_id': 'a', 'source_text': '5', 'candidates': [], 'needs_review': False}],
                  'regions': [{'unique_region_id': 'a', 'source_text': '5', 'needs_review': False}]}
        result = attach_vlm_evidence(source, [{'unique_region_id': 'a', 'text': 'Ø5', 'confidence': 1, 'status': 'ok'}])
        self.assertEqual(result['regions'][0]['source_text'], '5')
        self.assertIsNone(result['regions'][0]['candidates'][0]['confidence'])
        self.assertTrue(result['needs_review'])
        self.assertFalse(source['regions'][0]['needs_review'])

    def test_timeout_stays_visible(self):
        result = attach_vlm_evidence({'unique_regions': [{'unique_region_id': 'a'}]},
                                     [{'unique_region_id': 'a', 'status': 'timeout', 'text': ''}])
        self.assertEqual(result['unique_regions'][0]['candidates'][0]['status'], 'timeout')
        self.assertTrue(result['needs_review'])

    def test_no_inferred_diameter_or_minus(self):
        group = {'parts': [{'region_id': str(i), 'role': role, 'text': text}
                           for i, (role, text) in enumerate([('nominal','1.046'),('upper','+.003'),('lower','.002')])]}
        regions = [{'unique_region_id':'2','candidates':[{'text':'-.002','status':'ok'}]}]
        result = compose_reviewed_annotations([group], regions)[0]
        self.assertEqual(result['reviewed_candidates'][0]['text'], '1.046 +.003 -.002')
        self.assertTrue(result['needs_review'])
        self.assertEqual(group['parts'][2]['text'], '.002')
        regions[0]['candidates'][0]['status'] = 'output_truncated'
        failed = compose_reviewed_annotations([group], regions)[0]
        self.assertNotIn('-.002', failed['reviewed_candidates'][0]['text'])

    def test_coordinates_keep_unicode_identity(self):
        result = qwen_page(json.dumps({'regions':[{'text':'∅5','bbox':[100,100,300,200]}],'tables':[]}),2000,1000)
        self.assertEqual(result['lines'][0]['bbox'],[200,100,600,200])
        self.assertEqual(result['lines'][0]['text'],'∅5')

    def test_malformed_geometry_is_failure(self):
        with self.assertRaises(ValueError):
            qwen_page('{"regions":[],"tables":null}',100,100)
        with self.assertRaises(ValueError):
            qwen_page(json.dumps({'regions':[{'text':'A','bbox':[0,0,1200,20]}],'tables':[]}),100,100)

    def test_table_cells_require_spans_and_consistent_edges(self):
        table={'bbox':[0,0,100,100],'rows':1,'cols':2,'cells':[
            {'row':0,'col':0,'rowspan':1,'colspan':1,'bbox':[0,0,50,100]},
            {'row':0,'col':1,'rowspan':1,'colspan':1,'bbox':[50,0,100,100]}]}
        self.assertTrue(table_geometry(table,100,100))
        table['cells'][0]['bbox'][2]=20
        self.assertFalse(table_geometry(table,100,100))


if __name__=='__main__':
    unittest.main()
