"""Behavior examples, not engineering OCR accuracy tests."""
import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from examples.engineering_tolerances import annotation_groups


def inputs():
    return [{'id': 'nominal', 'texts': ['1.046'], 'bbox': [100, 100, 200, 150], 'angle': 0},
            {'id': 'upper', 'texts': ['+.003'], 'bbox': [205, 93, 255, 115], 'angle': 0},
            {'id': 'lower', 'texts': ['.002'], 'bbox': [206, 127, 256, 150], 'angle': 0}]


class Tolerances(unittest.TestCase):
    def test_association_does_not_invent_diameter_or_minus(self):
        groups = inputs()
        result = annotation_groups(groups)
        self.assertEqual(result[0]['candidate_text'], '1.046 +.003 .002')
        self.assertTrue(result[0]['needs_review'])
        self.assertEqual(groups, inputs())

    def test_cell_boundary_prevents_join(self):
        self.assertEqual(annotation_groups(inputs(), [[90, 80, 202, 160], [203, 80, 300, 160]]), [])

    def test_rotated_multichar_neighbor_is_not_a_deviation(self):
        groups = inputs(); groups[1]['angle'] = 90
        self.assertEqual(annotation_groups(groups), [])


if __name__ == '__main__':
    unittest.main()
