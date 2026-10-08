"""Recompute numeric development scores; raw drawings/full OCR service are private.

This verifies aggregates from published per-region edit counts. It cannot replace
independent human annotation checks or rerun recognition from the drawings.
"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from examples.engineering_metrics import aggregate

root = Path(__file__).resolve().parents[1]/'artifacts/engineering-round2-20261008'
summary = json.loads((root/'summary.json').read_text(encoding='utf-8'))
bundles = [json.loads(line) for line in (root/'region-scores.jsonl').read_text(encoding='utf-8').splitlines()]
rows = [{**{k: v for k, v in b.items() if k != 'rows'}, **dict(zip(summary['region_fields'], r))}
        for b in bundles for r in b['rows']]
verified = {}
for stage, experiment in summary['runs'].items():
    for scene, groups in experiment.items():
        for kind, expected in groups.items():
            group = [r for r in rows if (r['stage'], r['scene'], r['kind']) == (stage, scene, kind)]
            measured = aggregate(group)
            for field, value in measured.items():
                assert value == expected[field], (stage, scene, kind, field)
            verified[f'{stage}/{scene}/{kind}'] = measured
print(json.dumps({'scope': summary['scope'], 'verified': verified,
                  'review_is_recognition_credit': False}, ensure_ascii=False, indent=2))
