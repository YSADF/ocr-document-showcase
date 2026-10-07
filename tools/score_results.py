"""Score public table cells without replacing Ø/∅ or other Unicode symbols.

Scores describe OCR JSON only. DOCX render quality is reviewed separately.
"""
import json, re, zipfile
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
def normalize(s): return re.sub(r'\s+',' ',s).strip()
def distance(a,b):
    row=list(range(len(b)+1))
    for i,x in enumerate(a,1):
        nxt=[i]
        for j,y in enumerate(b,1): nxt.append(min(row[j]+1,nxt[-1]+1,row[j-1]+(x!=y)))
        row=nxt
    return row[-1]

def main():
    out=ROOT/'artifacts/gpu-20261007'
    gt=json.loads((ROOT/'artifacts/merged-table-ground-truth.json').read_text(encoding='utf-8'))
    response=json.loads((out/'merged-table-response.json').read_text(encoding='utf-8'))
    tables=[r['table'] for r in response['regions'] if r.get('table')]
    assert len(tables)==1
    pred=tables[0]; cells={(c['row'],c['col']):c for c in pred['cells']}
    rows=[]; errors=chars=exact=structure=0
    for c in gt['cells']:
        value=cells.get((c['row'],c['col']),{}); expected=normalize(c['text']); actual=normalize(value.get('text',''))
        edits=distance(expected,actual); errors+=edits; chars+=len(expected); exact+=expected==actual
        same=all(c[k]==value.get(k) for k in ('row','col','rowspan','colspan')); structure+=same
        rows.append({'row':c['row'],'col':c['col'],'expected':expected,'predicted':actual,'edit_distance':edits,'span_matches':same})
    key=lambda c:tuple(c[k] for k in ('row','col','rowspan','colspan'))
    expected_merges={key(c) for c in gt['cells'] if c['rowspan']>1 or c['colspan']>1}
    actual_merges={key(c) for c in pred['cells'] if c['rowspan']>1 or c['colspan']>1}
    result={'scope':'one self-created table, 21 cells; OCR JSON only','normalization':'collapse whitespace only; preserve case and Unicode code points',
            'cell_exact':exact,'cell_total':len(rows),'reference_characters':chars,'character_edits':errors,'cer':errors/chars,
            'matching_cell_spans':structure,'predicted_cells':len(pred['cells']),
            'merges':{'true_positive':len(expected_merges&actual_merges),'false_positive':len(actual_merges-expected_merges),'false_negative':len(expected_merges-actual_merges)},'cells':rows,
            'docx':{}}
    ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
    for name in ('engineering','merged-table'):
        with zipfile.ZipFile(out/f'{name}-output.docx') as z: tree=ET.fromstring(z.read('word/document.xml'))
        result['docx'][name]={'native_table_count':len(tree.findall('.//w:tbl',ns)),
            'grid_span_xml_nodes':len(tree.findall('.//w:gridSpan',ns)),
            'vertical_merge_xml_nodes':len(tree.findall('.//w:vMerge',ns)),
            'review_renderer':'LibreOffice -> PDF -> PNG','visual_acceptance':'failed',
            'observations':['Text overlaps in engineering drawing'] if name=='engineering' else ['Table text missing and borders incomplete; title/footer overlap'],
            'scope_note':'XML nodes show structure exists, not that it renders correctly. Microsoft Word was not tested.'}
    (out/'quality.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in {'cells','docx'}},ensure_ascii=False,indent=2))

if __name__=='__main__': main()
