"""Run the frozen public samples against an existing PP-V5 API (not a server)."""
from __future__ import annotations
import argparse, hashlib, json, mimetypes, os, platform, time
from datetime import datetime, timezone
from pathlib import Path
import httpx
import numpy as np

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--base-url', default='http://127.0.0.1:8089')
    p.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    p.add_argument('--runs', type=int, default=20)
    a=p.parse_args(); out=a.root/'artifacts'/'gpu-20261007'; out.mkdir(parents=True,exist_ok=True)
    headers={'X-API-Key':os.environ['PPOCR_API_KEY']} if os.environ.get('PPOCR_API_KEY') else {}
    report={'date':datetime.now(timezone.utc).isoformat(),'measurement':'serial HTTP request to full response, JSON parsing excluded','warmups':2,'runs':a.runs,'percentile_method':'numpy linear','environment':{'python':platform.python_version(),'platform':platform.platform()},'cases':{}}
    with httpx.Client(base_url=a.base_url,headers=headers,timeout=600) as c:
        h=c.get('/api/v1/health'); h.raise_for_status(); health=h.json()
        report['environment'].update({k:health.get(k) for k in ('backend','accelerator')})
        assert health['status']=='healthy' and health['accelerator']['ready']
        for name,fn in [('engineering','c03-raster.png'),('merged-table','merged-table-scan.pdf')]:
            src=a.root/'samples'/fn; payload=src.read_bytes()
            params={'use_layout':'true','output_format':'json','ocr_lang':'en','ocr_mode':'balanced','conversion_mode':'ocr'}
            case={'input':fn,'sha256':hashlib.sha256(payload).hexdigest(),'parameters':params.copy(),'requests':[]}
            report['cases'][name]=case
            for i in range(2+a.runs):
                start=time.perf_counter(); row={'index':i,'warmup':i<2}
                try:
                    r=c.post('/api/v1/ocr/file/sync',data=params,files={'file':(fn,payload,mimetypes.guess_type(fn)[0] or 'application/octet-stream')})
                    row.update(seconds=time.perf_counter()-start,http_status=r.status_code)
                    r.raise_for_status(); d=r.json(); row['success']=bool(d.get('success',True)); row['characters']=len(d.get('full_text',''))
                    if i==2: (out/f'{name}-response.json').write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf-8')
                except Exception as e:
                    row.update(success=False,error=type(e).__name__,seconds=time.perf_counter()-start)
                case['requests'].append(row)
                print(name,i,round(row['seconds'],3),row['success'],flush=True)
                (out/'benchmark.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
            measured=[r for r in case['requests'] if not r['warmup']]
            times=[r['seconds'] for r in measured if r['success']]
            case['summary']={'success':sum(r['success'] for r in measured),'failed':sum(not r['success'] for r in measured),'p50_seconds':float(np.percentile(times,50)) if times else None,'p95_seconds':float(np.percentile(times,95)) if times else None,'max_seconds':max(times) if times else None}
            start=time.perf_counter()
            try:
                r=c.post('/api/v1/ocr/file/sync',data={**params,'output_format':'docx','direct_download':'true'},files={'file':(fn,payload,mimetypes.guess_type(fn)[0] or 'application/octet-stream')})
                elapsed=time.perf_counter()-start; r.raise_for_status()
                valid=r.content[:2]==b'PK'; case['docx']={'success':valid,'seconds':elapsed,'bytes':len(r.content),'http_status':r.status_code}
                (out/f'{name}-output.docx' if valid else out/f'{name}-docx-error.txt').write_bytes(r.content)
            except Exception as e: case['docx']={'success':False,'seconds':time.perf_counter()-start,'error':type(e).__name__}
            (out/'benchmark.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print('BENCHMARK_COMPLETE',flush=True)
if __name__=='__main__': main()
