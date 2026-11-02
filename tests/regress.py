"""Regression run over local training projects (kept OUT of the repo: data/training/<name>/manifest.json).
manifest: {"name":..., "plans":["a.pdf",...], "reference":"ref_boq.pdf"}
Usage: python tests/regress.py [base_url]   (server must be running). Prints, per project, how many reference
categories we match within 5% / 15% and how many are missing, so a change that makes things worse is visible."""
import json, os, sys, glob, requests
BASE=sys.argv[1] if len(sys.argv)>1 else 'http://localhost:8000'
ROOT=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),'data','training')
tot=dict(ok5=0,ok15=0,both=0,missing=0)
for mf in sorted(glob.glob(os.path.join(ROOT,'*','manifest.json'))):
    d=os.path.dirname(mf); m=json.load(open(mf,encoding='utf-8'))
    pid=requests.post(BASE+'/api/projects',json=dict(name=m['name'])).json()['id']
    fs=[('files',(f,open(os.path.join(d,f),'rb'))) for f in m['plans']]
    requests.post(f'{BASE}/api/projects/{pid}/upload',files=fs); requests.post(f'{BASE}/api/projects/{pid}/run',timeout=600)
    requests.post(f'{BASE}/api/projects/{pid}/reference',files=[('files',open(os.path.join(d,m['reference']),'rb'))])
    c=requests.get(f'{BASE}/api/projects/{pid}/compare').json(); rows=[r for r in c['rows'] if r['ref'] and r['ours']]
    ok5=sum(1 for r in rows if abs(r['dev'])<=5); ok15=sum(1 for r in rows if abs(r['dev'])<=15)
    print(f"{m['name']}: matched {len(rows)}, within 5%: {ok5}, within 15%: {ok15}, missing: {c['missing']}")
    for k,v in dict(ok5=ok5,ok15=ok15,both=len(rows),missing=c['missing']).items(): tot[k]+=v
print('TOTAL',tot)
