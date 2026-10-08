"""Recompute published derived counts. Does not re-run models or validate private labels."""
from collections import defaultdict
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'artifacts/engineering-vlm-round3-20261008'
summary = json.loads((ROOT/'summary.json').read_text(encoding='utf-8'))
groups = defaultdict(list)
cells = defaultdict(list)
for line in (ROOT/'region-scores.jsonl').read_text(encoding='utf-8').splitlines():
    bundle = json.loads(line)
    rows = [dict(zip(bundle['fields'], values)) for values in bundle['rows']]
    if bundle['suite'] == 'diagnostics':
        for category in bundle['categories']:
            groups[(bundle['stage'], 'diagnostics/'+category+'/'+bundle['view'])].extend(rows)
    elif bundle['suite'] == 'controls':
        groups[(bundle['stage'], 'controls/synthetic')].extend(rows)
    elif bundle['suite'] == 'regions':
        groups[(bundle['stage'], 'regions/'+bundle['kind'])].extend(rows)
    elif bundle['suite'] == 'pages':
        key = bundle['kind'] if bundle['stage'] in ('paddle', 'qwen') else bundle['scene']+'/'+bundle['kind']
        groups[(bundle['stage'], 'pages/'+key)].extend(rows)
        targets = set(bundle.get('cell_target_ids', []))
        cells[(bundle['stage'], bundle['sample_id'])].extend(r for r in rows if r['id'] in targets)

result = {}
for (stage, group), rows in sorted(groups.items()):
    exact, count = sum(r['exact'] for r in rows), len(rows)
    result[stage+'/'+group] = {'exact': exact, 'n': count}
    if stage in summary['models']:
        model = summary['models'][stage]
        expected = model['pages'][group.split('/')[1]] if group.startswith('pages/') else model['local'][group]
        assert exact == expected['exact'], (stage, group, 'exact')
        assert count == expected.get('n', expected.get('regions')), (stage, group, 'count')
        denominator = sum(r['reference_characters'] for r in rows)
        cer = sum(r['edits'] for r in rows)/max(1, denominator)
        assert abs(cer-expected['cer']) < 1e-12, (stage, group, 'cer')
for (stage, sid), rows in cells.items():
    if stage in summary['models'] and rows:
        expected = summary['models'][stage]['cell_targets'][sid]
        assert len(rows) == expected['n']
        assert sum(r['found'] for r in rows) == expected['found_in_valid_cells']
        assert sum(r['exact'] for r in rows) == expected['exact']
assert len(json.loads((ROOT/'case-runs.json').read_text(encoding='utf-8'))) == 894
print(json.dumps({'verified': True, 'counts': result}, ensure_ascii=False, indent=2))
