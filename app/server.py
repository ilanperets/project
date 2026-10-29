import json, os, re, shutil, time, uuid
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from . import classify as C, engines as E, boq as B

ROOT=os.environ.get('KAMUYOT_DATA',os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),'data'))
PROJ=os.path.join(ROOT,'projects'); os.makedirs(PROJ,exist_ok=True)
RULES=os.path.join(ROOT,'rules.json')
app=FastAPI(title='מערכת כתבי כמויות')

def _rules():
    try: return json.load(open(RULES,encoding='utf-8'))
    except Exception: return []
def _pdir(pid):
    if not re.fullmatch(r'[a-f0-9]{8}',pid): raise HTTPException(404,'פרויקט לא נמצא')
    return os.path.join(PROJ,pid)
def _load(pid):
    p=os.path.join(_pdir(pid),'project.json')
    if not os.path.exists(p): raise HTTPException(404,'פרויקט לא נמצא')
    return json.load(open(p,encoding='utf-8'))
def _save(pr): json.dump(pr,open(os.path.join(_pdir(pr['id']),'project.json'),'w',encoding='utf-8'),ensure_ascii=False)

@app.get('/api/health')
def health(): return dict(ok=True,types=C.TYPES)

@app.get('/api/projects')
def projects():
    out=[]
    for d in sorted(os.listdir(PROJ)):
        try: pr=_load(d); out.append(dict(id=pr['id'],name=pr['name'],sheets=len(pr['sheets']),has_boq=bool(pr.get('boq'))))
        except Exception: pass
    return out

@app.post('/api/projects')
def create(body:dict):
    pid=uuid.uuid4().hex[:8]; os.makedirs(os.path.join(_pdir(pid),'files'))
    pr=dict(id=pid,name=(body.get('name') or 'פרויקט חדש').strip()[:80],scale=None,sheets=[],boq=None,needs=[],log=[]); _save(pr); return pr

@app.get('/api/projects/{pid}')
def get(pid:str): return _load(pid)

@app.delete('/api/projects/{pid}')
def delete(pid:str): shutil.rmtree(_pdir(pid),ignore_errors=True); return dict(ok=True)

@app.post('/api/projects/{pid}/upload')
async def upload(pid:str,files:list[UploadFile]=File(...)):
    pr=_load(pid); rules=_rules(); seen={s['hash']:s for s in pr['sheets']}; added=[]
    for f in files:
        if not f.filename.lower().endswith('.pdf'): added.append(dict(file=f.filename,error='רק קבצי PDF נתמכים כרגע (DWG בהמשך)')); continue
        sid=uuid.uuid4().hex[:6]; path=os.path.join(_pdir(pid),'files',sid+'.pdf')
        with open(path,'wb') as o: o.write(await f.read())
        h=C.file_hash(path)
        if h in seen:
            os.remove(path); added.append(dict(file=f.filename,dup_of=seen[h]['file'])); continue
        try: ft=C.features(path); cl=C.classify(ft,rules)
        except Exception as e: os.remove(path); added.append(dict(file=f.filename,error='הקובץ לא נקרא: '+str(e)[:80])); continue
        s=dict(sid=sid,file=f.filename,hash=h,w_mm=ft['w_mm'],h_mm=ft['h_mm'],n_draw=ft['n_draw'],layers=ft['layers'],type=cl['type'],conf=cl['conf'],why=cl['why'],floor=None,confirmed=False)
        pr['sheets'].append(s); seen[h]=s; added.append(dict(file=f.filename,sid=sid,type=s['type'],conf=s['conf']))
    pr['boq']=None; _save(pr); return dict(added=added,project=pr)

@app.post('/api/projects/{pid}/sheets/{sid}')
def label(pid:str,sid:str,body:dict):
    pr=_load(pid); s=next((x for x in pr['sheets'] if x['sid']==sid),None)
    if not s: raise HTTPException(404,'גיליון לא נמצא')
    if 'type' in body:
        if body['type'] not in C.TYPES: raise HTTPException(400,'סוג לא מוכר')
        s['type']=body['type']; s['confirmed']=True; s['conf']='confirmed'; s['why']='אושר על ידך'
        rules=[r for r in _rules() if set(r['sig'])!=set(C.sig(s['layers']))]; rules.append(dict(sig=C.sig(s['layers']),type=s['type']))
        os.makedirs(ROOT,exist_ok=True); json.dump(rules,open(RULES,'w',encoding='utf-8'),ensure_ascii=False)
    if 'floor' in body: s['floor']=body['floor'] or None
    pr['boq']=None; _save(pr); return pr

FLOOR={'ground':'קומת קרקע','first':'קומה א׳','second':'קומה ב׳','roof':'גג'}

@app.post('/api/projects/{pid}/run')
def run(pid:str):
    pr=_load(pid); sheets=pr['sheets']; log=[]; lines=[]; assumptions=[]
    path=lambda s:os.path.join(_pdir(pid),'files',s['sid']+'.pdf')
    scale=None
    for s in sheets:
        if s['type']=='foundation_piles':
            sc,ok,tot=E.calibrate_scale(path(s))
            if sc: scale=sc; log.append(f"כיול קנה מידה מכלונסאות: 1:{sc} ({ok} מתוך {tot} עיגולים בקטרים תקניים)"); break
    if not scale:
        scale=50; assumptions.append(dict(t='קנה מידה 1:50 הונח',why='לא נמצאה תוכנית כלונסאות לכיול. כל המדידות נשענות על ההנחה הזו',how='אשר קנה מידה, או העלה תוכנית יסודות'))
    pr['scale']=scale
    fps=[s for s in sheets if s['type']=='floor_plan']
    for s in fps:
        if not s['floor']: assumptions.append(dict(t=f"באיזו קומה גיליון \"{s['file']}\"?",why='אי אפשר לקרוא את שם הקומה מהגיליון (טקסט וקטורי)',gives='תיאור הסעיפים ואיטום גג',how='בחר קומה בטבלת הגיליונות'))
    for s in sheets:
        t=s['type']
        try:
            if t=='foundation_piles':
                l,info=E.piles(path(s),scale); lines+=l; log.append(f"{s['file']}: כלונסאות {info}")
            elif t=='floor_plan':
                fl=FLOOR.get(s['floor'],'קומה לא מסומנת')
                if s['floor']=='roof':
                    l,info=E.roof(path(s),scale); lines+=l; log.append(f"{s['file']}: גג {info}")
                    l,info=E.walls(path(s),scale,'מעקות גג'); lines+=l
                else:
                    l,info=E.walls(path(s),scale,fl); lines+=l; log.append(f"{s['file']}: קירות {info}")
                    if info.get('extra_plan'): assumptions.append(dict(t=f"בגיליון \"{s['file']}\" זוהו שתי תוכניות דומות",why='נבחרה הגדולה מביניהן',how='אשר שזו הנכונה'))
            elif t=='elevation':
                l,info=E.openings(path(s),scale); lines+=l; log.append(f"{s['file']}: פתחים {info}")
            elif t=='electrical':
                l,info=E.rooms(path(s),scale)
                for x in l: x['desc']+=f" (גיליון {s['file']})"
                lines+=l; log.append(f"{s['file']}: חללים {info}")
        except Exception as e: log.append(f"{s['file']}: שגיאה בחישוב: {str(e)[:100]}")
    present={s['type'] for s in sheets}
    needed={e[4] for e in B.EXPECTED}
    missing=sorted(t for t in needed if t not in present)
    unbuilt=sorted(t for t in present if t not in B.BUILT and t in needed or t=='unknown' and t in present)
    rows=B.build(pr['name'],lines,present)
    pr['boq']=rows; pr['needs']=B.needs(sheets,missing,unbuilt,assumptions); pr['log']=log; _save(pr)
    return dict(boq=rows,needs=pr['needs'],log=log,scale=scale)

@app.get('/api/projects/{pid}/export.xlsx')
def export(pid:str):
    pr=_load(pid)
    if not pr.get('boq'): raise HTTPException(400,'עוד לא חושב כתב')
    out=os.path.join(_pdir(pid),'boq.xlsx'); B.to_xlsx(pr['boq'],pr['name'],out,pr['needs']); return FileResponse(out,filename='kamuyot_boq.xlsx')

STATIC=os.path.join(os.path.dirname(os.path.abspath(__file__)),'static')
if os.path.isdir(STATIC): app.mount('/',StaticFiles(directory=STATIC,html=True),name='ui')
