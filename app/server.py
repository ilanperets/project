import json, os, re, shutil, time, uuid
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from . import fillwalls as FW, agent as AG, refboq as RB, compare as CMP, annotations as ANN, schedules as SCH, wetroom as WR, classify as C, knowledge as KN, engines as E, boq as B, brain as BR, derive as DV, symbols as SY, mapper as MP, sitework as SW, dwg as DW, auth as AU, score as SC
import datetime

ROOT=os.environ.get('KAMUYOT_DATA',os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),'data'))
# per-company data: every path below resolves inside the current company's folder (or the shared folder when auth is off)
PROJ=AU.LP('projects'); RULES=AU.LP('rules.json'); MEM=AU.LP('prices_memory.json')
SYMF=AU.LP('symbols.json'); LMAPF=AU.LP('layermap.json')
def _jl(p,d):
    try: return json.load(open(p,encoding='utf-8'))
    except Exception: return d
def _js(p,v): p=os.fspath(p); os.makedirs(os.path.dirname(p),exist_ok=True); json.dump(v,open(p,'w',encoding='utf-8'),ensure_ascii=False)
app=FastAPI(title='מערכת כתבי כמויות')

# optional password for a hosted copy: set APP_PASSWORD and the browser asks for it (any user name)
import base64, hmac
_OPEN={'/api/health','/api/auth/login','/api/auth/me','/api/auth/logout'}
@app.middleware('http')
async def _gate(request,call_next):
    pw=os.environ.get('APP_PASSWORD')
    if pw and request.url.path!='/api/health':
        ok=False; h=request.headers.get('authorization','')
        if h.startswith('Basic '):
            try: ok=hmac.compare_digest(base64.b64decode(h[6:]).decode('utf-8','ignore').split(':',1)[-1],pw)
            except Exception: ok=False
        if not ok: return JSONResponse({'detail':'נדרשת סיסמה'},status_code=401,headers={'WWW-Authenticate':'Basic realm="kamuyot"'})
    if AU.ENABLED and request.url.path.startswith('/api/'):
        c=AU.resolve(request.cookies.get(AU.COOKIE))
        if request.url.path not in _OPEN and not c: return JSONResponse({'detail':'נדרשת התחברות','login':True},status_code=401)
        if c and request.url.path not in _OPEN and request.url.path not in ('/api/params','/api/spec','/api/engines') and not request.url.path.startswith(('/api/admin','/api/org')):
            if c['user']['role']=='platform' and not c['org_id']: return JSONResponse({'detail':'בחרו חברה לתמיכה כדי לראות נתונים'},status_code=403)
            if c['state']=='blocked': return JSONResponse({'detail':c['why']+'. פנו למנהל המערכת','blocked':True},status_code=403)
        tok=AU.CUR.set(c)
        try: return await call_next(request)
        finally: AU.CUR.reset(tok)
    return await call_next(request)

@app.on_event('startup')
def _boot(): AU.bootstrap()
app.include_router(AU.router)

def _rules():
    try: return json.load(open(RULES,encoding='utf-8'))
    except Exception: return []
def _pdir(pid):
    if not re.fullmatch(r'[a-f0-9]{8}',pid): raise HTTPException(404,'פרויקט לא נמצא')
    return os.path.join(PROJ,pid)
def _load(pid):
    p=os.path.join(_pdir(pid),'project.json')
    if not os.path.exists(p): raise HTTPException(404,'פרויקט לא נמצא')
    pr=json.load(open(p,encoding='utf-8'))
    for k,v in (('materials',[]),('prices',{}),('mprices',{}),('params',{}),('bills',[]),('orders',[]),('sq',{}),('pref',{}),('quotes',[]),('needs',[]),('log',[]),('events',[]),('pending',[]),('stale',False),('checks',{}),('version',1),('status','received'),('client',''),('measurer',''),('reviewer',''),('due',''),('created',''),('updated',''),('changes',None),('delivered_at',''),('variations',[]),('bill_draft',{})): pr.setdefault(k,v)
    return pr
def _ev(pr,t): pr.setdefault('events',[]).append(dict(t=t,at=datetime.datetime.now().isoformat(timespec='minutes'))); pr['events']=pr['events'][-40:]
def _save(pr):
    pr['updated']=datetime.datetime.now().isoformat(timespec='minutes')
    json.dump(pr,open(os.path.join(_pdir(pr['id']),'project.json'),'w',encoding='utf-8'),ensure_ascii=False)

@app.get('/api/health')
def health(): return dict(ok=True,types=C.TYPES)

@app.get('/api/projects')
def projects():
    out=[]; os.makedirs(PROJ,exist_ok=True)
    for d in sorted(os.listdir(PROJ)):
        try: pr=_load(d); out.append(dict(id=pr['id'],name=pr['name'],sheets=len(pr['sheets']),has_boq=bool(pr.get('boq')),status=pr.get('status')))
        except Exception: pass
    return out

@app.post('/api/projects')
def create(body:dict):
    lim=AU.limit('projects')
    if lim is not None and os.path.isdir(PROJ) and len(os.listdir(PROJ))>=lim: raise HTTPException(403,f'המסלול כולל עד {lim} פרויקטים. פנו אלינו לשדרוג')
    pid=uuid.uuid4().hex[:8]; os.makedirs(os.path.join(_pdir(pid),'files'))
    now=datetime.datetime.now().isoformat(timespec='minutes'); pr=dict(id=pid,name=(body.get('name') or 'פרויקט חדש').strip()[:80],client=(body.get('client') or '').strip()[:60],measurer=(body.get('measurer') or '').strip()[:40],reviewer=(body.get('reviewer') or '').strip()[:40],due=(body.get('due') or '')[:10],status='received',version=1,created=now,events=[dict(t='הפרויקט נפתח',at=now)],checks={},scale=None,sheets=[],boq=None,needs=[],log=[],materials=[],prices={},mprices={},params={},bills=[],orders=[],quotes=[]); _save(pr); return pr

@app.post('/api/reset')
def reset(body:dict):
    """wipe all projects; optionally also the learned price memory and classification rules"""
    shutil.rmtree(PROJ,ignore_errors=True); os.makedirs(PROJ,exist_ok=True)
    if body.get('memory'):
        try: os.remove(MEM)
        except OSError: pass
    if body.get('rules'):
        for f in (RULES,SYMF,LMAPF):
            try: os.remove(f)
            except OSError: pass
    return dict(ok=True)

STATUSES=['received','measuring','review','delivered']
@app.post('/api/projects/{pid}/meta')
def meta(pid:str,body:dict):
    pr=_load(pid)
    for k in ('name','client','measurer','reviewer'):
        if k in body: pr[k]=str(body[k]).strip()[:80]
    if 'due' in body: pr['due']=str(body['due'])[:10]
    if 'checks' in body: pr['checks'].update({k:bool(v) for k,v in body['checks'].items()})
    if 'status' in body:
        if body['status'] not in STATUSES: raise HTTPException(400,'סטטוס לא מוכר')
        if body['status']=='review' and not pr.get('boq'): raise HTTPException(400,'אי אפשר לשלוח לבדיקה לפני שחושב כתב')
        if body['status']=='delivered':
            if not all(c['ok'] for c in _checks(pr)): raise HTTPException(400,'לא כל הבדיקות הושלמו')
            pr['delivered_at']=datetime.datetime.now().isoformat(timespec='minutes')
        if pr['status']!=body['status']: _ev(pr,{'received':'הוחזר לשלב קבלה','measuring':'הוחזר למדידה','review':'נשלח לבדיקה','delivered':'נמסר ללקוח'}[body['status']])
        pr['status']=body['status']
    _save(pr); return pr

def _checks(pr):
    ck=pr.get('checks',{}); sh=pr['sheets']; needs=pr.get('needs',[])
    return [dict(k='scale',t='קנה מידה כויל מהתוכנית',auto=True,ok=bool(pr.get('scale')) and not any(n['t'].startswith('קנה מידה') for n in needs)),
     dict(k='sheets',t='כל הגיליונות סווגו',auto=True,ok=bool(sh) and all(x['type']!='unknown' for x in sh)),
     dict(k='high',t='אין ממצאים דחופים פתוחים',auto=True,ok=not any(n['p']=='high' for n in needs),note=f"{sum(1 for n in needs if n['p']=='high')} פתוחים"),
     dict(k='asm',t='ההנחות אושרו',auto=False,ok=bool(ck.get('asm'))),
     dict(k='second',t='בדיקה שנייה בוצעה',auto=False,ok=bool(ck.get('second')),note=pr.get('reviewer') or 'לא הוגדר בודק')]

@app.get('/api/projects/{pid}')
def get(pid:str): return _load(pid)

@app.delete('/api/projects/{pid}')
def delete(pid:str): shutil.rmtree(_pdir(pid),ignore_errors=True); return dict(ok=True)

@app.post('/api/projects/{pid}/reclassify')
def reclassify(pid:str):
    """Re-run sheet identification on a project's sheets (after engine improvements). Sheets the user already confirmed keep their type."""
    pr=_load(pid); rules=_rules(); ch=[]
    for s in pr['sheets']:
        if s.get('confirmed'): continue
        pth=os.path.join(_pdir(pid),'files',s['sid']+'.pdf')
        try: ft=C.features(pth); cl=C.classify(ft,rules)
        except Exception: continue
        if cl['type']!=s['type']: ch.append(dict(file=s['file'],was=s['type'],now=cl['type']))
        s.update(type=cl['type'],conf=cl['conf'],why=cl['why'])
    _save(pr); return dict(changed=ch)

@app.post('/api/projects/{pid}/upload')
async def upload(pid:str,files:list[UploadFile]=File(...)):
    pr=_load(pid); rules=_rules(); seen={s['hash']:s for s in pr['sheets']}; added=[]
    import io, pymupdf
    class _F:
        def __init__(s,fn,b): s.filename=fn; s._b=b
        async def read(s): return s._b
    exp=[]
    for f in files:
        if os.path.splitext(f.filename)[1].lower()=='.pdf':
            b=await f.read()
            try:
                dd=pymupdf.open(stream=b,filetype='pdf')
                if len(dd)>1 and dd[0].rect.width>1000:      # large-format multi-sheet PDF: one sheet per page
                    for i in range(len(dd)):
                        o=pymupdf.open(); o.insert_pdf(dd,from_page=i,to_page=i); exp.append(_F(f"{os.path.splitext(f.filename)[0]}_{i+1}.pdf",o.tobytes()))
                    continue
            except Exception: pass
            exp.append(_F(f.filename,b))
        else: exp.append(f)
    files=exp
    for f in files:
        ext=os.path.splitext(f.filename)[1].lower()
        if ext not in ('.pdf','.dwg'): added.append(dict(file=f.filename,error='נתמכים קבצי PDF ו-DWG בלבד')); continue
        if ext=='.dwg' and not AU.feature('dwg'): added.append(dict(file=f.filename,error='קריאת DWG אינה כלולה במסלול שלכם')); continue
        sid=uuid.uuid4().hex[:6]; path=os.path.join(_pdir(pid),'files',sid+'.pdf'); data=await f.read(); src=None
        if ext=='.dwg':
            src=os.path.join(_pdir(pid),'files',sid+'.dwg')
            with open(src,'wb') as o: o.write(data)
            try: dinfo=DW.dwg_to_pdf(src,path)
            except Exception as e:
                for p_ in (src,path):
                    if os.path.exists(p_): os.remove(p_)
                added.append(dict(file=f.filename,error='קובץ DWG לא נקרא: '+str(e)[:80])); continue
        else:
            with open(path,'wb') as o: o.write(data)
        h=C.file_hash(src or path)
        if h in seen:
            os.remove(path)
            if src: os.remove(src)
            added.append(dict(file=f.filename,dup_of=seen[h]['file'])); continue
        try: ft=C.features(path); cl=C.classify(ft,rules)
        except Exception as e: os.remove(path); added.append(dict(file=f.filename,error='הקובץ לא נקרא: '+str(e)[:80])); continue
        s=dict(sid=sid,file=f.filename,hash=h,w_mm=ft['w_mm'],h_mm=ft['h_mm'],n_draw=ft['n_draw'],layers=ft['layers'],type=cl['type'],conf=cl['conf'],why=cl['why'],floor=None,confirmed=False,version=1,**(dict(source='dwg',dwg=dinfo) if src else {}))
        try: rv=None if (cl['conf']=='high' and cl['why'].startswith('הכותרת')) else C.revision_of(dict(ft,type=cl['type']),path,pr['sheets'],_pdir(pid))
        except Exception: rv=None
        if rv:
            s['pending_of']=rv[0]['sid']; s['sim']=round(rv[1]*100); pr['pending']=[x for x in pr['pending'] if x['hash']!=h]+[s]; seen[h]=s
            added.append(dict(file=f.filename,sid=sid,type=s['type'],conf=s['conf'],revision_of=rv[0]['sid'],sim=s['sim'])); continue
        pr['sheets'].append(s); seen[h]=s; added.append(dict(file=f.filename,sid=sid,type=s['type'],conf=s['conf'],disc=C.DISC.get(s['type'],'')))
    n_ok=sum(1 for a in added if a.get('sid') and not a.get('revision_of'))
    if n_ok: _stash(pr); _ev(pr,f'הועלו {n_ok} תוכניות')
    if n_ok: pr['stale']=True
    _save(pr); return dict(added=added,project=pr)

@app.post('/api/projects/{pid}/sheets/{sid}')
def label(pid:str,sid:str,body:dict):
    pr=_load(pid); s=next((x for x in pr['sheets'] if x['sid']==sid),None)
    if not s: raise HTTPException(404,'גיליון לא נמצא')
    if 'type' in body:
        if body['type'] not in C.TYPES: raise HTTPException(400,'סוג לא מוכר')
        s['type']=body['type']; s['confirmed']=True; s['conf']='confirmed'; s['why']='אושר על ידך'
        rules=[r for r in _rules() if set(r['sig'])!=set(C.sig(s['layers']))]; rules.append(dict(sig=C.sig(s['layers']),type=s['type']))
        _js(RULES,rules)
    if 'type' in body and 'disc' not in body: s.pop('disc',None)
    if 'disc' in body:
        if body['disc'] and body['disc'] not in dict(C.DISCS): raise HTTPException(400,'תחום לא מוכר')
        s['disc']=body['disc'] or None
    if 'floor' in body: s['floor']=body['floor'] or None
    _stash(pr); pr['stale']=True; _save(pr); return pr

def _snap(rows): return {r['desc']:dict(q=r.get('q'),unit=r.get('unit')) for r in (rows or []) if r.get('kind')=='item' and r.get('q') is not None}
def _stash(pr):
    if pr.get('boq') and pr.get('prev_snap') is None: pr['prev_snap']=_snap(pr['boq']); pr['prev_ver']=pr.get('version',1)

@app.post('/api/projects/{pid}/revision')
def revision(pid:str,body:dict):
    """decide what to do with an uploaded sheet that looks like a new revision: replace | add | skip"""
    pr=_load(pid); n=next((x for x in pr['pending'] if x['sid']==body.get('sid')),None)
    if not n: raise HTTPException(404,'אין גיליון ממתין')
    act=body.get('action'); pr['pending']=[x for x in pr['pending'] if x['sid']!=n['sid']]
    old=next((x for x in pr['sheets'] if x['sid']==n.get('pending_of')),None)
    n.pop('pending_of',None); n.pop('sim',None)
    if act=='skip':
        try: os.remove(os.path.join(_pdir(pid),'files',n['sid']+'.pdf'))
        except OSError: pass
        _save(pr); return pr
    _stash(pr)
    if act=='replace' and old:
        for k in ('type','floor','disc','confirmed','conf','why'):
            if k in old: n[k]=old[k]
        n['version']=old.get('version',1)+1; n['prev']=[dict(sid=old['sid'],file=old['file'],version=old.get('version',1))]+old.get('prev',[])
        pr['sheets']=[n if x['sid']==old['sid'] else x for x in pr['sheets']]; _ev(pr,f"גיליון עודכן לגרסה {n['version']}: {n['file'][:30]}")
    elif act in ('add','replace'): pr['sheets'].append(n); _ev(pr,'נוסף גיליון חדש')
    else: raise HTTPException(400,'פעולה לא מוכרת')
    pr['stale']=True; _save(pr); return pr

@app.get('/api/projects/{pid}/sheets/{sid}/view.png')
def view(pid:str,sid:str):
    import fitz
    if not re.fullmatch(r'[a-f0-9]{6}',sid): raise HTTPException(404,'')
    src=os.path.join(_pdir(pid),'files',sid+'.pdf'); out=os.path.join(_pdir(pid),'files',sid+'_big.png')
    if not os.path.exists(src): raise HTTPException(404,'')
    if not os.path.exists(out):
        pg=fitz.open(src)[0]; z=min(3000/pg.rect.width,4.0); pg.get_pixmap(matrix=fitz.Matrix(z,z),alpha=False).save(out)
    return FileResponse(out,media_type='image/png')

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
    slab_areas=[]; ext_per=[]; room_cnt=0; room_per=0.0; labels=_jl(SYMF,{}); lmap=_jl(LMAPF,{})
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
                    if info.get('area_m2'): slab_areas.append(info['area_m2']); ext_per.append(('roof',info['perimeter_m'],info['area_m2']))
                    l,info=E.walls(path(s),scale,'מעקות גג'); lines+=l
                else:
                    l,info=E.walls(path(s),scale,fl); lines+=l; log.append(f"{s['file']}: קירות {info}")
                    if info.get('note')=='לא נמצאה שכבת קירות':
                        try:
                            fl_,fi_=FW.lines(path(s),scale,BR.params(pr).get('wall_height',3.0)); lines+=fl_; log.append(f"{s['file']}: קירות לפי צבעי מילוי {fi_}")
                        except Exception as e: log.append(f"{s['file']}: שגיאת צבעי מילוי {str(e)[:80]}")
                    try:
                        _,ri=E.roof(path(s),scale)
                        if ri.get('area_m2'): slab_areas.append(ri['area_m2'])
                        if ri.get('perimeter_m') and s['floor']: ext_per.append((s['floor'],ri['perimeter_m'],ri['area_m2']))
                    except Exception: pass
                    if info.get('extra_plan'): assumptions.append(dict(t=f"בגיליון \"{s['file']}\" זוהו שתי תוכניות דומות",why='נבחרה הגדולה מביניהן',how='אשר שזו הנכונה'))
            elif t=='tile_layout':
                nr=sum(1 for t2 in sheets[:sheets.index(s)] if t2['type']=='tile_layout')+1
                l,info=WR.tile_layout(path(s),BR.params(pr),f'חדר רחצה {nr}',f'גיליון {sheets.index(s)+1}'); lines+=l; log.append(f"{s['file']}: פריסת אריחים {info}")
            elif t=='wetroom_plan':
                nr=sum(1 for t2 in sheets[:sheets.index(s)] if t2['type']=='wetroom_plan')+1
                l,info=WR.wetroom_plan(path(s),BR.params(pr),f'חדר רחצה {nr}',f'גיליון {sheets.index(s)+1}'); lines+=l; log.append(f"{s['file']}: תוכנית חדר רחצה {info}")
                fl_,fi_=WR.fixtures(path(s),BR.params(pr),labels,f'חדר רחצה {nr}',f'גיליון {sheets.index(s)+1}'); lines+=fl_; log.append(f"{s['file']}: סמלים {fi_}")
            elif t=='elevation':
                l,info=E.facades(path(s),scale)
                if not l: l,info=E.openings(path(s),scale)
                lines+=l; log.append(f"{s['file']}: פתחים {info}")
            elif t=='electrical':
                l,info=E.rooms(path(s),scale)
                nel=sum(1 for t in sheets[:sheets.index(s)] if t['type']=='electrical')+1
                for x in l: x['desc']+=f" (תוכנית חשמל {nel})"
                lines+=l; log.append(f"{s['file']}: חללים {info}"); room_cnt+=info.get('rooms',0) if isinstance(info,dict) else 0; room_per+=info.get('per_m',0) if isinstance(info,dict) else 0
                if labels:
                    sl,si=SY.count(path(s),labels); lines+=sl; log.append(f"{s['file']}: סמלי חשמל {si}")
        except Exception as e: log.append(f"{s['file']}: שגיאה בחישוב: {str(e)[:100]}")
        for layer,m in (lmap.get(t) or {}).items():
            try:
                q=MP.measure(path(s),scale,layer,m['mode'])
                if q: lines.append(dict(ch=int(m['ch']),sub=int(m.get('sub',1)),desc=m['desc'],unit=m['unit'],q=q,st='נמדד',src=f"מיפוי שכבה {layer} ({s['file'][:18]})",need='',cover=[m['desc']]))
            except Exception as e: log.append(f"{s['file']}: שגיאת מיפוי שכבה {layer}: {str(e)[:60]}")
    try:
        sl,sw,si=SCH.lines(sheets,path); lines+=sl; assumptions+=sw
        _da=sum(v.get('area',0) for k,v in si.items() if k=='door_schedule')
        for l in lines:
            if l['desc'].startswith('מחיצות גבס') and l.get('q') and _da and _da<0.4*l['q'] and 'ניכוי פתחים' not in l.get('src',''):
                l['q']=round(l['q']-_da,1); l['src']+=f" · ניכוי פתחי דלתות לפי הרשימה {_da} מ\"ר"
                if l.get('trace'): l['trace']['rows'].append(dict(el='ניכוי פתחי דלתות',dims=f'{_da}',val=-_da,src='רשימת דלתות × מידות'))
                break
        for k,v in si.items(): log.append(f"רשימות {k}: {v['rows']} סוגים, נספרו {v['counted']} בתוכנית"+(f", תגיות לא ברשימה {v['unlisted']}" if v['unlisted'] else ''))
    except Exception as e: log.append(f"רשימות: שגיאה {str(e)[:100]}")
    try:
        al,notes=ANN.lines(sheets,path); lines+=al; pr['plan_notes']=notes
        if al: log.append(f"כמויות כתובות בתוכניות: {len(al)} סעיפים")
    except Exception as e: log.append(f"הערות ותבלאות: שגיאה {str(e)[:100]}")
    if {x['type'] for x in sheets}&{'demolition','ceiling'}:
        for s in sheets:
            if s['type']!='floor_plan': continue
            try:
                from . import partitions as PA
                r=PA.new_partitions(path(s),scale)
                if r:
                    h=3.0; q=round(r['length_m']*h,1)
                    lines.append(dict(ch=22,sub=1,desc='מחיצות גבס חד קרומיות ודו קרומיות עם קונסטרוקציה',unit='מ"ר',q=q,st='נמדד',src=f"אורך מחיצות חדשות בתוכנית {r['length_m']} מ' × גובה {h} מ' (הונח)",need='לאמת גובה מחיצה ומספר קרומים',cover=['מחיצות גבס חד קרומיות ודו קרומיות עם קונסטרוקציה']))
                    assumptions.append(dict(t=f"גובה מחיצות הונח {h} מ'",why='התקרה המונמכת בגובה 2.70 מ׳ אבל המחיצה בדרך כלל עולה עד התקרה העליונה',how='עדכן את גובה המחיצה בסעיף'))
            except Exception as e: log.append(f"{s['file']}: מחיצות שגיאה {str(e)[:60]}")
    for s in sheets:
        if s['type']!='ceiling': continue
        try:
            from . import ceilings as CE
            r=CE.tiles(path(s),scale)
            if r and r['area_m2']>0:
                lines.append(dict(ch=22,sub=1,desc='תקרות אקוסטיות מודולריות',unit='מ"ר',q=r['area_m2'],st='נמדד',src=f"שטח רשת האריחים בתוכנית התקרה ({r['areas']} אזורים, אריח כ-{r['pitch_cm']} ס\"מ), ללא קירות",need='לאמת סוג אריח ושטחי גבס נפרדים',cover=['תקרות אקוסטיות מודולריות']))
                log.append(f"{s['file']}: תקרה אקוסטית {r['area_m2']} מ\"ר")
        except Exception as e: log.append(f"{s['file']}: תקרות שגיאה {str(e)[:60]}")
    try: assumptions+=KN.check(lines,sheets,pr.get('ptype'))
    except Exception as e: log.append(f'בדיקת השלמות: שגיאה {str(e)[:80]}')
    P=BR.params(pr)
    lines+=WR.plumbing_points(lines); lines+=WR.plumbing_pipes(lines,BR.params(pr))
    op_m2=sum(float(re.search(r'([\d.]+) מ"ר',l['need']).group(1)) for l in lines if l['ch']==6 and l['unit']=="יח'" and re.search(r'([\d.]+) מ"ר',l.get('need','')))
    lines+=DV.exterior(ext_per,op_m2,BR.params(pr))
    if any(f!='roof' for f,_,_ in ext_per) and not any(l['desc']=='טיח חוץ' for l in lines): assumptions.append(dict(t='היקף קומות לא נקרא אמין',why='הקו החיצוני של תוכניות הקומות לא נסגר, ולכן טיח וצבע חוץ לא חושבו',how='העלה חזיתות או תוכנית קומה שבה הקירות החיצוניים סגורים'))
    lines+=DV.derive(lines,slab_areas,P)
    if room_per>0: lines.append(dict(ch=10,sub=2,desc='סוקל ופנלים',unit='מ"א',q=round(room_per,1),st='חלקי',src='היקף חללים סגורים בתוכניות החשמל',need='הפחתת רוחבי דלתות ואימות חללים פתוחים',
        trace=dict(formula='סכום היקפי החללים הסגורים (לא מופחתים רוחבי דלתות)',rows=[dict(el='היקף חללים',dims='סכום',val=round(room_per,1),src='זיהוי חללים סגורים בתוכניות החשמל',note='כולל פתחי דלתות, ולכן מעט גבוה',locs=[])],checks=[dict(ok=False,t='לא הופחתו רוחבי דלתות')],params={})))
    _gf=[(f,p,a) for f,p,a in ext_per if f!='roof' and a>=20 and p*p/a<=40] or [(f,p,a) for f,p,a in ext_per if a>=20 and p*p/a<=40]
    _M=dict(footprint=max((a for _,_,a in _gf),default=0),perimeter=max((p for _,p,a in _gf),default=0),floors=len({f for f,_,_ in ext_per if f!='roof'}) or None,total_slab=(sum(l['q'] for l in lines if l['desc'].startswith('ריצוף, שטח נטו') and l.get('q')) or sum(slab_areas)),rooms=room_cnt)
    if _M['footprint']: lines+=SW.site_lines(_M,P)
    else: lines+=[l for l in SW.site_lines(dict(rooms=room_cnt),P)]
    # accuracy guard: in a commercial renovation (demolition / ceiling / flooring sheets present) the residential wall engine is not reliable;
    # its numbers become "needs completion" instead of a wrong figure that looks real
    _types={x['type'] for x in sheets}
    if len(_types&{'demolition','ceiling','flooring','layout'})>=2:
        n_g=0
        for l in lines:
            if l['ch'] in (4,9,11) and l.get('q') is not None and not any(k in (l.get('src') or '') for k in ('צבע מילוי','כתובה','רשימת')):
                l['q']=None; l['st']='דורש השלמה'; l['src']='לא נמדד: בפרויקט שיפוץ מסחרי מדידת הקירות האוטומטית אינה אמינה בלי מקרא קריא'; l['need']='מדידה ידנית או אישור צבעי מילוי'; l.pop('trace',None); n_g+=1
        if n_g: assumptions.append(dict(t=f'{n_g} סעיפי קירות, טיח וצבע לא חושבו',why='זוהה פרויקט שיפוץ מסחרי, ומנוע הקירות הקיים בנוי למגורים ועלול להניב כמות מנופחת',gives='כמות אמינה',how='לאשר צבעי מילוי של מחיצות או להזין כמות'))
    merged={}
    for l in lines:
        k=(l['ch'],l.get('sub',1),l['desc'],l['unit'])
        if k in merged and l['q'] is not None and merged[k]['q'] is not None:
            merged[k]['q']=round(merged[k]['q']+l['q'],2)
            a,b=merged[k].get('trace'),l.get('trace')
            if a and b: a['rows']=a['rows']+b['rows']; a['checks']=a['checks']+b['checks']
        else: merged[k]=l
    lines=list(merged.values())
    pr['lines']=lines; pr['asm']=assumptions; pr['log']=log
    rebuild(pr)
    if pr.get('prev_snap') is not None:
        old=pr['prev_snap']; new=_snap(pr['boq']); ch=[]
        for d in sorted(set(old)|set(new)):
            a=old.get(d,{}).get('q'); b=new.get(d,{}).get('q')
            if a!=b: ch.append(dict(desc=d,unit=(new.get(d) or old.get(d)).get('unit'),old=a,new=b))
        pr['version']=pr.get('prev_ver',1)+1
        pr['changes']=dict(frm=pr['version']-1,to=pr['version'],at=datetime.datetime.now().isoformat(timespec='minutes'),items=ch)
        pr['prev_snap']=None; _ev(pr,f"גרסה {pr['version']}: {len(ch)} סעיפים השתנו")
    else: _ev(pr,'כתב הכמויות חושב')
    if pr.get('status')=='received': pr['status']='measuring'
    pr['stale']=False; _save(pr)
    return pr

def rebuild(pr):
    """BOQ = engine lines + manual items, with quantity overrides and hidden items; then materials and needs"""
    P=BR.params(pr); sheets=pr['sheets']; lines=list(pr.get('lines',[]))
    for m in pr.get('manual',[]): lines.append(dict(ch=m['ch'],sub=m.get('sub',1),desc=m['desc'],unit=m['unit'],q=m['q'],st='ידני',src=m.get('src') or 'הוזן ידנית',need=m.get('need',''),trace=m.get('trace')))
    present={s['type'] for s in sheets}; needed={e[4] for e in B.EXPECTED}
    missing=sorted(t for t in needed if t not in present)
    unbuilt=sorted(t for t in present if t not in B.BUILT and t in needed or t=='unknown' and t in present)
    rows=B.build(pr['name'],lines,present,pr.get('ov'),set(pr.get('hidden',[])),pr.get('chnames'),edits=dict(ren=pr.get('ren',{}),un=pr.get('un',{}),ord=pr.get('ord',{})))
    mats,used=BR.explode(rows,P); asm=list(pr.get('asm',[]))
    for k in used: asm.append(dict(t=f"הנחה: {BR.DEFAULT_PARAMS[k]['label']} = {P[k]}",why=BR.DEFAULT_PARAMS[k]['why'],gives='פירוק לחומרים',how='עדכן בהגדרות הפרויקט'))
    pr['boq']=rows; pr['materials']=mats; pr['needs']=B.needs(sheets,missing,unbuilt,asm)

@app.get('/api/projects/{pid}/report.pdf')
def report_pdf(pid:str,plans:int=1,watch:int=1,crops:int=1,missing:int=1,prm:int=0,ch:str='',only:str=''):
    from . import report as RP
    pr=_load(pid); fd=os.path.join(_pdir(pid),'files'); P=BR.params(pr)
    params=[(BR.DEFAULT_PARAMS[k]['label'],P[k]) for k in ('wall_height','deduct_limit','wp_upturn','room_scale','waste_tile') if k in P]
    out=os.path.join(_pdir(pid),'report.pdf'); RP.to_pdf(RP.build(pr,fd,params,opts=dict(plans=plans,watch=watch,crops=crops,missing=missing,params=prm,chs=(ch.split(',') if ch else None),only=1 if only=='measured' else 0)),out)
    return FileResponse(out,media_type='application/pdf',filename='דוח-חישוב.pdf')

@app.get('/api/projects/{pid}/score')
def project_score(pid:str): return SC.score(_load(pid).get('boq'))

@app.get('/api/projects/{pid}/preflight')
def preflight(pid:str):
    """what is missing or partial, by chapter, and why. Shown before every export."""
    pr=_load(pid); chs=[]; cur=None
    for r in pr.get('boq') or []:
        if r['kind']=='ch' and r['desc']!=pr['name']: cur=dict(code=r['code'][:2],name=r['desc'],missing=[],partial=[],ok=0); chs.append(cur)
        elif r['kind']=='item' and cur is not None:
            it=dict(code=r['code'],desc=r.get('full') or r['desc'],unit=r['unit'],why=r.get('need',''))
            if r['q'] is None: cur['missing'].append(it)
            elif r['st']=='חלקי': cur['partial'].append(it)
            else: cur['ok']+=1
    sheets=[n for n in pr.get('needs',[]) if n['t'].startswith('גיליון מסוג')]
    return dict(chapters=[c for c in chs if c['missing'] or c['partial']],sheets=[dict(t=n['t'].replace('גיליון מסוג: ',''),how=n['how']) for n in sheets],
        n_missing=sum(len(c['missing']) for c in chs),n_partial=sum(len(c['partial']) for c in chs),n_ok=sum(c['ok'] for c in chs))

@app.post('/api/projects/{pid}/builder')
def builder(pid:str,body:dict):
    """add / quantity override / hide / restore / rename chapter, without re-running the engines"""
    pr=_load(pid); a=body.get('action')
    if 'lines' not in pr: pr['lines']=[]
    if a=='add':
        if not body.get('desc') or not body.get('unit'): raise HTTPException(400,'חסר תיאור או יחידה')
        pr.setdefault('manual',[]).append(dict(ch=int(body.get('ch') or 99),sub=int(body.get('sub') or 1),desc=body['desc'].strip(),unit=body['unit'].strip(),q=float(body['q']) if body.get('q') not in ('',None) else None,src=body.get('src'),need=body.get('need',''),trace=body.get('trace')))
        if body.get('chname'): pr.setdefault('chnames',{})[str(int(body['ch']))]=body['chname']
    elif a=='qty':
        pr.setdefault('ov',{})[body['desc']]=float(body['q']) if body.get('q') not in ('',None) else None
    elif a=='rename':
        k=body['desc']; nd=(body.get('new') or '').strip()
        if not nd: raise HTTPException(400,'התיאור ריק')
        m=next((m for m in pr.get('manual',[]) if m['desc']==k),None)
        if m: m['desc']=nd
        else: pr.setdefault('ren',{})[k]=nd
    elif a=='unit':
        k=body['desc']; m=next((m for m in pr.get('manual',[]) if m['desc']==k),None)
        if m: m['unit']=body['unit']
        else: pr.setdefault('un',{})[k]=body['unit']
    elif a=='dup':
        src=next((r for r in pr.get('boq',[]) if r.get('kind')=='item' and (r.get('key') or r['desc'])==body['desc']),None)
        if not src: raise HTTPException(404,'סעיף לא נמצא')
        ch,sub=int(src['code'][:2]),int(src['code'][3:5])
        pr.setdefault('manual',[]).append(dict(ch=ch,sub=sub,desc=src['desc']+' (העתק)',unit=src['unit'],q=src['q'],src='שוכפל מסעיף קיים',need=''))
    elif a=='move':
        grp=body['group']; keys=list(body['keys']); i=keys.index(body['desc']); j=i+int(body['dir'])
        if 0<=j<len(keys):
            keys[i],keys[j]=keys[j],keys[i]; pr.setdefault('ord',{})[grp]=keys
            ca,cb=body['codes'][i],body['codes'][j]; pz=pr.setdefault('prices',{}); pa,pb=pz.get(ca),pz.get(cb)
            for c,v in ((ca,pb),(cb,pa)):
                if v is None: pz.pop(c,None)
                else: pz[c]=v
    elif a=='disc':
        pr.setdefault('disc',{})[str(int(body['ch']))]=float(body.get('pct') or 0)
    elif a=='hide': pr.setdefault('hidden',[]).append(body['desc'])
    elif a=='unhide': pr['hidden']=[d for d in pr.get('hidden',[]) if d!=body['desc']]
    elif a=='rm_manual': pr['manual']=[m for m in pr.get('manual',[]) if m['desc']!=body['desc']]
    else: raise HTTPException(400,'פעולה לא מוכרת')
    rebuild(pr); _save(pr); return pr

@app.post('/api/projects/{pid}/restore')
def restore_edits(pid:str,body:dict):
    """undo support for the workbook: put back the user-editable parts of the bill exactly as they were"""
    pr=_load(pid)
    for k in ('ov','hidden','manual','ren','un','ord','disc','prices','chnames'):
        if k in body: pr[k]=body[k]
    rebuild(pr); _save(pr); return pr

@app.post('/api/projects/{pid}/start')
def start_empty(pid:str):
    """start a BOQ without plans: only the expected items, to be filled by hand"""
    pr=_load(pid); pr['lines']=pr.get('lines',[]); pr['asm']=[]; rebuild(pr); _save(pr); return pr

@app.get('/api/projects/{pid}/sheets/{sid}/thumb.png')
def thumb(pid:str,sid:str):
    import fitz
    if not re.fullmatch(r'[a-f0-9]{6}',sid): raise HTTPException(404,'')
    src=os.path.join(_pdir(pid),'files',sid+'.pdf'); out=os.path.join(_pdir(pid),'files',sid+'.png')
    if not os.path.exists(src): raise HTTPException(404,'')
    if not os.path.exists(out):
        pg=fitz.open(src)[0]; z=min(900/pg.rect.width,2.0); pg.get_pixmap(matrix=fitz.Matrix(z,z),alpha=False).save(out)
    return FileResponse(out,media_type='image/png')

def _filter_rows(rows,ch='',only='',missing='show'):
    """export options: chapters (comma list of NN), only measured, hide items with no quantity"""
    chs={c for c in (ch or '').split(',') if c}
    keep=[]; cur=None
    for r in rows:
        if r['kind']=='ch':
            cur=r['code'][:2]
            if r['desc']==rows[0]['desc'] and r is rows[0]: keep.append(r); continue
        if r['kind']=='item':
            if chs and cur not in chs: continue
            if only=='measured' and (r['q'] is None or r.get('st') in ('ידני',)): continue
            if missing=='hide' and r['q'] is None: continue
        elif chs and cur is not None and cur not in chs and r['kind']!='ch': continue
        keep.append(r)
    out=[]
    for i,r in enumerate(keep):   # drop headings and notes with no items under them
        if r['kind'] in('ch','sub','note') and i>0:
            j=i+1; has=False
            while j<len(keep):
                k=keep[j]['kind']
                if k=='item': has=True;break
                if r['kind']=='ch' and k=='ch': break
                if r['kind']=='sub' and k in('sub','ch'): break
                if r['kind']=='note' and k in('sub','ch'): break
                j+=1
            if not has: continue
        out.append(r)
    return out

@app.get('/api/projects/{pid}/export.xlsx')
def export(pid:str,ch:str='',only:str='',missing:str='show',hide:str='',full:int=0):
    pr=_load(pid)
    if not pr.get('boq'): raise HTTPException(400,'עוד לא חושב כתב')
    out=os.path.join(_pdir(pid),'boq.xlsx'); B.to_xlsx(_filter_rows(pr['boq'],ch,only,missing),pr['name'],out,pr['needs'],prices=pr['prices'],hide=hide.split(','),ctx=(dict(pr=pr,files_dir=os.path.join(_pdir(pid),'files')) if full else None),meta=dict(client=pr.get('client',''),version='v%s'%pr.get('version',1),measurer=pr.get('measurer',''),reviewer=pr.get('reviewer',''),status=pr.get('status',''))); return FileResponse(out,filename='kamuyot_boq.xlsx')



# ---------- pricing, memory, bills, orders ----------
def _mem():
    try: return json.load(open(MEM,encoding='utf-8'))
    except Exception: return []

@app.post('/api/projects/{pid}/params')
def set_params(pid:str,body:dict):
    pr=_load(pid); pr['params']={k:float(v) for k,v in body.items() if k in BR.DEFAULT_PARAMS}; _save(pr); return run(pid) if pr.get('boq') else pr

from .spec import SPEC, CHAPTERS
@app.get('/api/spec')
def spec(): return dict(chapters={str(k):v for k,v in CHAPTERS.items()},items=SPEC)

ENGINES=[
 dict(k='piles',name='כלונסאות',ch='23',st='active',does='סופר כלונסאות לפי קוטר מתוכנית היסודות ומכייל את קנה המידה',needs='אורך כלונס (OCR של טבלת מפלסים) כדי לחשב בטון וזיון מדויקים'),
 dict(k='walls',name='קירות',ch='04',st='partial',does='מודד אורך קירות לפי עובי מתוכנית קומה, לפי קומה',needs='הפרדה בין בלוק לבטון, וגובה קומה מהחתכים'),
 dict(k='rooms',name='חללים וריצוף',ch='10',st='active',does='מזהה חדרים סגורים ומחשב שטח נטו',needs='פיצול חללים פתוחים ושמות חדרים'),
 dict(k='roof',name='גג ואיטום',ch='05',st='active',does='שטח גג לפי קו המעקה החיצוני',needs='-'),
 dict(k='openings',name='פתחים',ch='06',st='partial',does='סופר פתחים ושטחם מחזיתות',needs='פרט דלתות וחלונות לפי תגיות (OCR)'),
 dict(k='plaster',name='טיח וצבע',ch='09, 11',st='estimate',does='הערכה מאורך קירות כפול גובה פחות פתחים',needs='היקף חדרים מדויק ושטחי תקרה'),
 dict(k='concrete',name='בטון, תבניות וזיון',ch='02',st='estimate',does='נגזר: קירות בטון, תקרות לפי שטח ועובי שהונח, כלונסאות לפי אורך שהונח, ותבניות וזיון משקל לפי ק"ג למ"ק',needs='מידות אמיתיות וטבלאות זיון מגיליונות הקונסטרוקציה (OCR)'),
 dict(k='symbols',name='ספריית סמלי חשמל',ch='08',st='partial',does='מקבץ סמלים לפי צורה. מסמנים כל צורה פעם אחת (תאורה, שקע, מפסק...) והיא נספרת בכל תוכנית חשמל',needs='סימון הצורות על ידך. כל תיוג נשמר ומשפר את הדיוק'),
 dict(k='mapper',name='מיפוי שכבות כללי',ch='כל הפרקים',st='active',does='כל שכבה בכל תוכנית PDF מדידה לפי אורך, שטח או ספירה ומשויכת לסעיף. מתאים לאינסטלציה, מיזוג, פיתוח וכל תוכנית עם שכבות',needs='לבחור שכבה וסעיף פעם אחת. ההוראה נשמרת לפי סוג גיליון'),
 dict(k='plumbing',name='אינסטלציה, מיזוג ופיתוח',ch='07, 15, 40, 57',st='partial',does='עובד דרך מיפוי שכבות ברגע שיש תוכנית מהסוג הזה',needs='תוכניות לדוגמה להכרת השכבות ולאימון זיהוי אוטומטי'),
]
@app.get('/api/engines')
def engines_list(): return ENGINES

@app.get('/legacy')
def legacy():
    p=os.environ.get('KAMUYOT_LEGACY') or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),'kamuyot_system_empty.html')
    if not os.path.exists(p): raise HTTPException(404,'אין קובץ')
    return FileResponse(p,media_type='text/html')

@app.get('/api/projects/{pid}/sheets/{sid}/symbols')
def sheet_symbols(pid:str,sid:str):
    if not re.fullmatch(r'[a-f0-9]{6}',sid): raise HTTPException(404,'')
    p=os.path.join(_pdir(pid),'files',sid+'.pdf')
    if not os.path.exists(p): raise HTTPException(404,'')
    labels=_jl(SYMF,{}); pr0=_load(pid); st=next((x['type'] for x in pr0['sheets'] if x['sid']==sid),'')
    g=WR.fixture_groups(p,BR.params(pr0)) if st=='wetroom_plan' else SY.groups(p)
    return dict(labels=SY.LABEL_NAMES,groups=[dict(g={k:v for k,v in x.items() if k!='boxes'},label=labels.get(x['sig'])) for x in g if x['n']>=(1 if st=='wetroom_plan' else 2)][:40],total=sum(x['n'] for x in g),labelled=sum(x['n'] for x in g if labels.get(x['sig'])))

@app.get('/api/projects/{pid}/sheets/{sid}/crop.png')
def sheet_crop(pid:str,sid:str,x:float,y:float,w:float,h:float):
    if not re.fullmatch(r'[a-f0-9]{6}',sid): raise HTTPException(404,'')
    p=os.path.join(_pdir(pid),'files',sid+'.pdf'); out=os.path.join(_pdir(pid),'files',f'{sid}_{int(x)}_{int(y)}.png')
    if not os.path.exists(p): raise HTTPException(404,'')
    if not os.path.exists(out): SY.crop_png(p,x,y,w,h,out)
    return FileResponse(out,media_type='image/png')

@app.post('/api/symbols')
def label_symbol(body:dict):
    lab=_jl(SYMF,{})
    if body.get('label') and body['label'] in SY.LABEL_NAMES: lab[body['sig']]=body['label']
    else: lab.pop(body.get('sig'),None)
    _js(SYMF,lab); return dict(ok=True,n=len(lab))

@app.get('/api/projects/{pid}/sheets/{sid}/layers')
def sheet_layers(pid:str,sid:str):
    pr=_load(pid); s=next((x for x in pr['sheets'] if x['sid']==sid),None)
    if not s: raise HTTPException(404,'')
    cache=os.path.join(_pdir(pid),'files',sid+'.layers.json'); sc=pr.get('scale') or 50
    st=_jl(cache,None)
    if not st or st.get('scale')!=sc:
        st=dict(scale=sc,layers=MP.stats(os.path.join(_pdir(pid),'files',sid+'.pdf'),sc)); _js(cache,st)
    return dict(scale=sc,type=s['type'],layers=st['layers'],map=_jl(LMAPF,{}).get(s['type'],{}))

@app.post('/api/layermap')
def layermap(body:dict):
    m=_jl(LMAPF,{}); t=m.setdefault(body['type'],{})
    if body.get('remove'): t.pop(body['layer'],None)
    else:
        if not body.get('desc') or body.get('mode') not in ('length','area','count','circles'): raise HTTPException(400,'חסר תיאור או שיטת מדידה')
        t[body['layer']]=dict(desc=body['desc'].strip(),ch=int(body.get('ch') or 99),sub=int(body.get('sub') or 1),unit=body.get('unit') or 'מטר',mode=body['mode'])
    _js(LMAPF,m); return dict(ok=True)

@app.get('/api/params')
def params_def(): return BR.DEFAULT_PARAMS

@app.post('/api/projects/{pid}/prices')
def set_prices(pid:str,body:dict):
    pr=_load(pid); pr.setdefault('prices',{}).update({k:float(v) for k,v in (body.get('items') or {}).items() if v not in ('',None)})
    pr.setdefault('mprices',{}).update({k:float(v) for k,v in (body.get('materials') or {}).items() if v not in ('',None)})
    if body.get('remember'):
        mem=_mem(); idx={(m['desc'],m['unit']):m for m in mem}
        for r in pr['boq'] or []:
            if r['kind']=='item' and r['code'] in pr['prices']: idx[(r['desc'],r['unit'])]=dict(desc=r['desc'],unit=r['unit'],price=pr['prices'][r['code']])
        json.dump(list(idx.values()),open(MEM,'w',encoding='utf-8'),ensure_ascii=False)
    _save(pr); return pr

@app.post('/api/projects/{pid}/suggest')
def suggest(pid:str):
    pr=_load(pid); mem=_mem(); out={}
    for r in pr['boq'] or []:
        if r['kind']=='item' and r['code'] not in pr['prices']:
            s=BR.suggest(r['desc'],r['unit'],mem)
            if s: out[r['code']]=s
    return out

@app.post('/api/prices/import')
async def import_prices(file:UploadFile=File(...)):
    """learn prices from any BOQ xlsx: rows with description, unit and price"""
    import openpyxl, io
    wb=openpyxl.load_workbook(io.BytesIO(await file.read()),data_only=True); mem={(m['desc'],m['unit']):m for m in _mem()}; n=0
    for ws in wb:
        for row in ws.iter_rows(values_only=True):
            c=[x for x in row]
            for i in range(len(c)-3):
                d,u,q,p=c[i+1] if i+1<len(c) else None,c[i+2] if i+2<len(c) else None,c[i+3] if i+3<len(c) else None,c[i+4] if i+4<len(c) else None
                if isinstance(d,str) and len(d)>8 and isinstance(u,str) and len(u.strip())<8 and isinstance(p,(int,float)) and p>0:
                    mem[(d.strip(),u.strip())]=dict(desc=d.strip(),unit=u.strip(),price=float(p)); n+=1; break
    json.dump(list(mem.values()),open(MEM,'w',encoding='utf-8'),ensure_ascii=False); return dict(learned=n,total=len(mem))

@app.get('/api/projects/{pid}/summary')
def summary(pid:str):
    pr=_load(pid); rows=pr.get('boq') or []; items=[r for r in rows if r['kind']=='item']
    P=BR.params(pr); tot=BR.totals(rows,pr['prices'])
    by={}
    for r in rows:
        if r['kind']=='ch': cur=r['desc']; by[cur]=dict(total=0,items=0,measured=0,priced=0)
        elif r['kind']=='item' and rows.index(r)>0:
            b=by[cur]; b['items']+=1; b['measured']+= 1 if r.get('q') else 0
            if r.get('q') and pr['prices'].get(r['code']): b['priced']+=1; b['total']+=r['q']*pr['prices'][r['code']]
    by.pop(pr['name'],None)
    billed=sum(b['total'] for b in pr['bills']) if pr['bills'] else 0
    return dict(name=pr['name'],sheets=len(pr['sheets']),items=len(items),measured=sum(1 for r in items if r.get('q')),priced=sum(1 for r in items if r.get('q') and pr['prices'].get(r['code'])),total=tot,chapters=by,bills=len(pr['bills']),billed=billed,orders=len(pr['orders']),needs=len(pr['needs']),
      id=pr['id'],client=pr['client'],status=pr['status'],measurer=pr['measurer'],reviewer=pr['reviewer'],due=pr['due'],version=pr['version'],updated=pr['updated'],created=pr['created'],delivered_at=pr['delivered_at'],
      trust=dict(measured=sum(1 for r in items if r.get('q') is not None and r.get('st')=='נמדד'),manual=sum(1 for r in items if r.get('q') is not None and r.get('st')=='ידני'),est=sum(1 for r in items if r.get('q') is not None and r.get('st') not in ('נמדד','ידני')),missing=sum(1 for r in items if r.get('q') is None)),
      thumb_sid=next((x['sid'] for t in ('floor_plan','foundation_piles') for x in pr['sheets'] if x['type']==t),(pr['sheets'][0]['sid'] if pr['sheets'] else None)),checks=_checks(pr),changes=pr.get('changes'),events=pr.get('events',[])[-8:],high=sum(1 for n in pr['needs'] if n['p']=='high'))

def _bill_rows(pr):
    """BOQ items plus approved variations as extra items (code V<id>), and their prices"""
    rows=list(pr['boq']); prices=dict(pr['prices'])
    for v in pr.get('variations',[]):
        if v.get('status')=='מאושר': rows.append(dict(kind='item',code='V'+str(v['id']),desc='תוספת: '+v['desc'],unit=v['unit'],q=float(v['q']))); prices['V'+str(v['id'])]=float(v['price'])
    return rows,prices
def _bill_summary(pr):
    return dict(rates=dict(retention=BR.params(pr)['retention'],vat=BR.params(pr)['vat']))
@app.get('/api/projects/{pid}/bill_state')
def bill_state(pid:str):
    pr=_load(pid); rows,prices=_bill_rows(pr)
    return dict(rows=[r for r in rows if r['kind']=='item' and r.get('q') and prices.get(r['code'])],prices=prices,chapters={r['code'][:2]:r['desc'] for r in rows if r['kind']=='ch'},bills=pr['bills'],draft=pr.get('bill_draft',{}),variations=pr.get('variations',[]),**_bill_summary(pr))
@app.put('/api/projects/{pid}/bill_draft')
def bill_draft(pid:str,body:dict):
    pr=_load(pid); pr['bill_draft']=dict(pct={k:float(v) for k,v in (body.get('pct') or {}).items()},period=body.get('period',''),mode=body.get('mode','pct')); _save(pr); return dict(ok=True)
@app.post('/api/projects/{pid}/bills')
def new_bill(pid:str,body:dict):
    """body: {pct:{code:cumulative_pct}, period}"""
    pr=_load(pid); P=BR.params(pr); prev=pr['bills'][-1]['pct'] if pr['bills'] else {}
    cum={k:float(v) for k,v in body.get('pct',{}).items()}
    for k,v in prev.items(): cum.setdefault(k,v)
    for k,v in cum.items():
        if v>100.0001 or v<float(prev.get(k,0))-0.0001: raise HTTPException(400,f'אחוז לא תקין בסעיף {k}: {v}%. האחוז המצטבר חייב להיות בין האחוז הקודם ל-100')
    rows,prices=_bill_rows(pr)
    b=BR.bill(rows,prices,cum,prev,P); n=len(pr['bills'])+1; b.update(n=n,date=str(datetime.date.today()),pct=cum,total_this=b['this'])
    pr['bills'].append(dict(n=n,date=b['date'],period=body.get('period',''),status='הוגש',pct=cum,total=b['total'],this=b['this'],retention=b['retention'],vat=b['vat'],net=b['net'],cum=b['cum'])); pr['bill_draft']={}
    _ev(pr,f'חשבון חלקי {n} הוגש'); _save(pr); return b
@app.post('/api/projects/{pid}/bills/{n}/status')
def bill_status(pid:str,n:int,body:dict):
    pr=_load(pid); st=body.get('status')
    if st not in ('הוגש','אושר','שולם'): raise HTTPException(400,'סטטוס לא מוכר')
    if not 1<=n<=len(pr['bills']): raise HTTPException(404,'חשבון לא נמצא')
    b=pr['bills'][n-1]; b['status']=st; b['paid']=str(datetime.date.today()) if st=='שולם' else ''; _ev(pr,f'חשבון {n}: {st}'); _save(pr); return b
@app.post('/api/projects/{pid}/bills/{n}/reopen')
def bill_reopen(pid:str,n:int):
    pr=_load(pid)
    if n!=len(pr['bills']): raise HTTPException(400,'אפשר לפתוח לתיקון רק את החשבון האחרון')
    b=pr['bills'][-1]
    if b.get('status')=='שולם': raise HTTPException(400,'חשבון ששולם אינו ניתן לתיקון')
    pr['bills'].pop(); pr['bill_draft']=dict(pct=b['pct'],period=b.get('period',''),mode='pct'); _ev(pr,f'חשבון {n} נפתח לתיקון'); _save(pr); return dict(ok=True)
@app.get('/api/projects/{pid}/bills/{n}')
def get_bill(pid:str,n:int):
    pr=_load(pid); P=BR.params(pr); i=n-1
    if i<0 or i>=len(pr['bills']): raise HTTPException(404,'חשבון לא נמצא')
    rows,prices=_bill_rows(pr)
    prev=pr['bills'][i-1]['pct'] if i else {}; b=BR.bill(rows,prices,pr['bills'][i]['pct'],prev,P); b.update(n=n,date=pr['bills'][i]['date'],status=pr['bills'][i].get('status','הוגש'),period=pr['bills'][i].get('period','')); return b
@app.get('/api/projects/{pid}/bills/{n}/export.xlsx')
def bill_xlsx(pid:str,n:int):
    import openpyxl
    from openpyxl.styles import Font,PatternFill,Alignment
    b=get_bill(pid,n); pr=_load(pid); wb=openpyxl.Workbook(); ws=wb.active; ws.title=f'חשבון {n}'; ws.sheet_view.rightToLeft=True
    ws.append([f'חשבון חלקי מס\' {n}',pr['name']]); ws.append(['תאריך',b['date'],'תקופה',b.get('period','')]); ws.append([])
    ws.append(['מספר','סעיף','יחידה','כמות בחוזה','מחיר','קודם %','מצטבר %','לחשבון זה']);
    for c in ws[ws.max_row]: c.font=Font(bold=True,color='FFFFFF'); c.fill=PatternFill('solid',fgColor='0D43A0')
    for l in b['lines']:
        if l['cum_pct']!=l['prev_pct']: ws.append([l['code'],l['desc'],l['unit'],l['q'],l['price'],l['prev_pct'],l['cum_pct'],l['this']])
    ws.append([]); 
    for k,v in (('ביצוע בחשבון זה',b['this']),('עיכבון',-b['retention']),('לפני מע"מ',b['net']),('מע"מ',b['vat']),('לתשלום',b['total'])): ws.append(['','','','','','','',k,v][-2:] if False else ['','','','','','',k,v])
    for col,w in zip('ABCDEFGH',[12,48,8,12,10,9,10,14]): ws.column_dimensions[col].width=w
    out=os.path.join(_pdir(pid),f'bill{n}.xlsx'); wb.save(out); return FileResponse(out,filename=f'bill-{n}.xlsx')
@app.get('/api/projects/{pid}/bills/{n}/report.pdf')
def bill_pdf(pid:str,n:int):
    from . import report as RP
    b=get_bill(pid,n); pr=_load(pid); e=RP._e
    rows=''.join(f"<tr><td>{e(l['code'])}</td><td>{e(l['desc'])}</td><td class='num'>{RP._nf(l['q'])} {e(l['unit'])}</td><td class='num'>{RP._nf(l['price'],0)}</td><td class='num'>{RP._nf(l['prev_pct'],0)}%</td><td class='num'>{RP._nf(l['cum_pct'],0)}%</td><td class='num'><b>{RP._nf(l['this'],0)}</b></td></tr>" for l in b['lines'] if l['cum_pct']!=l['prev_pct'])
    tot=''.join(f"<tr><td>{k}</td><td class='num'><b>{RP._nf(v,0)}</b></td></tr>" for k,v in (('ביצוע בחשבון זה',b['this']),('עיכבון',-b['retention']),('לפני מע\"מ',b['net']),('מע\"מ',b['vat']),('לתשלום',b['total'])))
    html=f"<!doctype html><html lang='he' dir='rtl'><meta charset='utf-8'><style>{RP.CSS}</style><body><div class='cover' style='padding:0'><div class='band' style='padding:12mm 12mm'><h1>חשבון חלקי מס' {n}</h1><div class='sub'>{e(pr['name'])} · {e(b['date'])} {e(b.get('period',''))}</div></div></div><table><tr><th>מספר</th><th>סעיף</th><th>כמות</th><th>מחיר</th><th>קודם</th><th>מצטבר</th><th>לחשבון זה</th></tr>{rows}</table><h2>סיכום</h2><table class='kv' style='width:50%'>{tot}</table></body></html>"
    out=os.path.join(_pdir(pid),f'bill{n}.pdf'); RP.to_pdf(html,out); return FileResponse(out,media_type='application/pdf',filename=f'bill-{n}.pdf')
@app.post('/api/projects/{pid}/variations')
def add_variation(pid:str,body:dict):
    pr=_load(pid); vs=pr['variations']; i=max([v['id'] for v in vs],default=0)+1
    v=dict(id=i,desc=(body.get('desc') or '').strip()[:120],unit=body.get('unit') or "יח'",q=float(body.get('q') or 0),price=float(body.get('price') or 0),note=body.get('note',''),status='ממתין',date=str(datetime.date.today()))
    if not v['desc'] or v['q']<=0: raise HTTPException(400,'חסר תיאור או כמות')
    vs.append(v); _save(pr); return v
@app.post('/api/projects/{pid}/variations/{vid}')
def set_variation(pid:str,vid:int,body:dict):
    pr=_load(pid); v=next((x for x in pr['variations'] if x['id']==vid),None)
    if not v: raise HTTPException(404,'לא נמצא')
    if body.get('delete'):
        if any(('V'+str(vid)) in b['pct'] for b in pr['bills']): raise HTTPException(400,'התוספת כבר נכללת בחשבון שהוגש')
        pr['variations']=[x for x in pr['variations'] if x['id']!=vid]
    else:
        if body.get('status') in ('ממתין','מאושר','נדחה'): v['status']=body['status']
    _save(pr); return dict(ok=True)

def _ostatus(o):
    it=o['items']; d=sum(min(float(i.get('delivered') or 0),i['qty']) for i in it)
    if o.get('status')=='בוטלה': return 'בוטלה'
    if d<=0: return o.get('status') if o.get('status') in ('טיוטה','נשלחה','אושרה') else 'נשלחה'
    return 'סופקה' if all(float(i.get('delivered') or 0)>=i['qty']-1e-9 for i in it) else 'סופקה חלקית'

def _sprice(pr,material,supplier):
    q=next((x for x in pr.get('sq',{}).get(material,[]) if x['supplier']==supplier),None)
    return q['price'] if q else pr['mprices'].get(material)

@app.post('/api/projects/{pid}/orders')
def new_order(pid:str,body:dict):
    """one order for one supplier and one project stage; items may carry delivered (for orders already placed outside the system)"""
    pr=_load(pid); sup=(body.get('supplier') or 'ספק לא צוין').strip()
    items=[]
    for i in body.get('items',[]):
        q=float(i.get('qty') or 0)
        if q<=0: continue
        items.append(dict(material=i['material'],unit=i['unit'],qty=q,delivered=min(float(i.get('delivered') or 0),q),price=_sprice(pr,i['material'],sup)))
    if not items: raise HTTPException(400,'לא נבחרו חומרים')
    n=max([x['n'] for x in pr['orders']] or [0])+1
    o=dict(n=n,supplier=sup,stage=(body.get('stage') or '').strip(),needed=body.get('needed',''),note=body.get('note',''),date=body.get('date') or str(datetime.date.today()),status=body.get('status') or 'טיוטה',items=items,existing=bool(body.get('existing')),src=body.get('src'))
    if body.get('existing'): o['status']=_ostatus(o)
    pr['orders'].append(o); _ev(pr,f'הזמנה #{n} · {sup}'); _save(pr); return o

@app.post('/api/projects/{pid}/orders/{n}')
def order_status(pid:str,n:int,body:dict):
    pr=_load(pid); o=next((x for x in pr['orders'] if x['n']==n),None)
    if not o: raise HTTPException(404,'הזמנה לא נמצאה')
    if body.get('status') in ('טיוטה','נשלחה','אושרה','סופקה חלקית','סופקה','בוטלה'): o['status']=body['status']
    if body.get('status')=='סופקה':
        for i in o['items']: i['delivered']=i['qty']
    if isinstance(body.get('delivered'),dict):
        for i in o['items']:
            if i['material'] in body['delivered']: i['delivered']=max(0.0,min(float(body['delivered'][i['material']] or 0),i['qty']))
        o['status']=_ostatus(o) if o['status']!='בוטלה' else o['status']
    if 'stage' in body: o['stage']=str(body['stage'])[:80]
    _save(pr); return o

@app.post('/api/projects/{pid}/suppliers')
def supplier_quote(pid:str,body:dict):
    """supplier price quotes per material; pick=true makes it the preferred supplier and the material price"""
    pr=_load(pid); m=body.get('material'); sup=(body.get('supplier') or '').strip()
    if not m or not sup: raise HTTPException(400,'חסר חומר או ספק')
    price=float(body['price']) if body.get('price') not in ('',None) else None
    L=pr.setdefault('sq',{}).setdefault(m,[]); q=next((x for x in L if x['supplier']==sup),None)
    if price is not None:
        if q: q.update(price=price,date=str(datetime.date.today()))
        else: L.append(dict(supplier=sup,price=price,days=body.get('days',''),date=str(datetime.date.today())))
    if body.get('pick'):
        pr.setdefault('pref',{})[m]=sup
        if price is not None: pr['mprices'][m]=price
    _save(pr); return dict(sq=pr['sq'],pref=pr['pref'],mprices=pr['mprices'])

# ---------- reference BOQ (training) + agent ----------
MEMF=AU.LP('agent_memory.json')
def _jmem():
    try: return json.load(open(MEMF,encoding='utf-8'))
    except Exception: return []
def _smem(m):
    os.makedirs(os.path.dirname(str(MEMF)),exist_ok=True); json.dump(m,open(MEMF,'w',encoding='utf-8'),ensure_ascii=False)
def _compare_rows(pr):
    ref=pr.get('reference')
    if not ref: return None
    refl=[(x['desc'],x.get('unit'),x['q']) for x in ref['items']]
    ol=[(r['desc'],r['unit'],r['q']) for r in (pr.get('boq') or []) if r['kind']=='item']
    return CMP.compare(refl,ol)
@app.post('/api/projects/{pid}/reference')
async def upload_reference(pid:str,files:list[UploadFile]=File(...)):
    pr=_load(pid); f=files[0]; tmp=os.path.join(_pdir(pid),'reference.pdf'); open(tmp,'wb').write(await f.read())
    try: items=RB.parse(tmp)
    except Exception as e: raise HTTPException(400,'כתב הייחוס לא נקרא: '+str(e)[:80])
    if not items: raise HTTPException(400,'לא נמצאו סעיפים בכתב הייחוס')
    pr['reference']=dict(file=f.filename,items=items,total=round(sum(x['total'] for x in items))); _ev(pr,f'נטען כתב ייחוס: {len(items)} סעיפים'); _save(pr)
    return dict(items=len(items),total=pr['reference']['total'])
@app.get('/api/projects/{pid}/compare')
def compare_ref(pid:str):
    pr=_load(pid); rows=_compare_rows(pr)
    if rows is None: raise HTTPException(404,'לא נטען כתב ייחוס')
    both=[r for r in rows if r['ref'] and r['ours']]
    return dict(rows=rows,ref_items=len(pr['reference']['items']),ref_total=pr['reference']['total'],matched=len(both),close=sum(1 for r in both if r['status']!='סטייה'),missing=sum(1 for r in rows if r['status']=='חסר אצלנו'))
@app.get('/api/agent/memory')
def agent_memory(): return _jmem()
@app.delete('/api/agent/memory')
def agent_memory_clear(): _smem([]); return dict(ok=True)
@app.post('/api/projects/{pid}/agent')
def agent_chat(pid:str,body:dict):
    key=os.environ.get('ANTHROPIC_API_KEY','')
    if not key: raise HTTPException(503,'הסוכן עוד לא הופעל: צריך להגדיר מפתח שירות (ANTHROPIC_API_KEY) בשרת')
    pr=_load(pid); path=lambda s:os.path.join(_pdir(pid),'files',s['sid']+'.pdf')
    ctx=dict(pr=pr,path=path,compare=_compare_rows(pr),memory_load=_jmem,memory_save=_smem)
    msgs=[dict(role=m['role'],content=m['content']) for m in body.get('messages',[]) if m.get('role') in('user','assistant') and isinstance(m.get('content'),str)][-12:]
    try: reply,_=AG.chat(msgs,ctx,key)
    except Exception as e: raise HTTPException(502,str(e)[:150])
    return dict(reply=reply)

# ---------- Word-style quote ----------
from fastapi import Response
from fastapi.responses import HTMLResponse
from . import quote_pdf as QP, quote_xlsx as QX, quote_editor as QE
COMPANY=AU.LP('company_quote.json')
def _qopts(pr):
    try: co=json.load(open(COMPANY,encoding='utf-8'))
    except Exception: co={}
    o=dict(co); o.update(pr.get('quote_opts') or {}); return o
def _qbuild(pr,parts=True):
    o=_qopts(pr)
    return QP.build_html(pr,[r for r in pr['boq'] if r['kind'] in('ch','sub','note','item') and not r.get('hidden')],pr.get('prices',{}),company=dict(name=o.get('name') or 'שם החברה שלך',logo=o.get('logo')),opts=dict(discount=o.get('discount',0),vat=o.get('vat',18),valid_days=o.get('valid_days',30)),parts=parts)
@app.get('/quote-editor/{pid}')
def quote_editor(pid:str):
    _load(pid); return HTMLResponse(QE.page(pid))
@app.get('/api/projects/{pid}/quote_doc')
def quote_doc_get(pid:str,refresh:int=0):
    pr=_load(pid)
    if not pr.get('boq'): raise HTTPException(400,'עוד לא חושב כתב')
    o=_qopts(pr); css,body=_qbuild(pr); f=os.path.join(_pdir(pid),'quote_doc.html')
    if not refresh and os.path.exists(f): body=open(f,encoding='utf-8').read()
    else: open(f,'w',encoding='utf-8').write(body)
    return dict(css=css,body=body,opts=dict(name=o.get('name',''),discount=o.get('discount',0),vat=o.get('vat',18),valid_days=o.get('valid_days',30)))
@app.put('/api/projects/{pid}/quote_doc')
def quote_doc_put(pid:str,body:dict):
    _pdir(pid); open(os.path.join(_pdir(pid),'quote_doc.html'),'w',encoding='utf-8').write(str(body.get('body',''))[:8_000_000]); return dict(ok=True)
@app.put('/api/projects/{pid}/quote_opts')
def quote_opts_put(pid:str,body:dict):
    pr=_load(pid); keep=('name','discount','vat','valid_days')
    o={k:body[k] for k in keep if k in body}
    if body.get('logo'): o['logo']=body['logo'] if str(body['logo']).startswith('data:image/') and len(body['logo'])<1_500_000 else None
    try: co=json.load(open(COMPANY,encoding='utf-8'))
    except Exception: co={}
    for k in ('name','logo','vat','valid_days'):
        if o.get(k): co[k]=o[k]
    os.makedirs(os.path.dirname(str(COMPANY)),exist_ok=True); json.dump(co,open(COMPANY,'w',encoding='utf-8'),ensure_ascii=False)
    pr['quote_opts']=dict(discount=o.get('discount',0)); _save(pr); return dict(ok=True)
def _qfull(pid,body):
    pr=_load(pid); css,_=_qbuild(pr); return QP.wrap(css,str(body.get('body','')))
@app.post('/api/projects/{pid}/quote_doc.pdf')
def quote_doc_pdf(pid:str,body:dict):
    h=_qfull(pid,body); out=os.path.join(_pdir(pid),'quote_out.pdf'); QP.render_pdf(h.replace('contenteditable="true"',''),out); return FileResponse(out,filename='quote.pdf',media_type='application/pdf')
@app.post('/api/projects/{pid}/quote_doc.docx')
def quote_doc_docx(pid:str,body:dict):
    import subprocess
    from . import quote_docx as QD
    _pdir(pid); d=os.path.join(_pdir(pid),'qdocx'); shutil.rmtree(d,ignore_errors=True); os.makedirs(d)
    out=os.path.join(d,'quote.docx')
    try: QD.html_to_docx(str(body.get('body','')),out,d)
    except Exception as e: raise HTTPException(500,'המרה ל-Word נכשלה')
    return FileResponse(out,filename='quote.docx')
@app.get('/api/projects/{pid}/quote_pro.xlsx')
def quote_pro(pid:str):
    pr=_load(pid); o=_qopts(pr); out=os.path.join(_pdir(pid),'quote_pro.xlsx')
    QX.to_xlsx(pr,pr['boq'],pr.get('prices',{}),out,company=dict(name=o.get('name') or 'שם החברה'),opts=dict(discount=o.get('discount',0),vat=o.get('vat',18),valid_days=o.get('valid_days',30))); return FileResponse(out,filename='quote.xlsx')

@app.get('/api/projects/{pid}/quote.xlsx')
def quote(pid:str,ch:str='',only:str='',missing:str='show',hide:str=''):
    pr=_load(pid)
    if not pr.get('boq'): raise HTTPException(400,'עוד לא חושב כתב')
    rows=_filter_rows([dict(r) for r in pr['boq']],ch,only,missing)
    import copy
    out=os.path.join(_pdir(pid),'quote.xlsx'); B.to_xlsx(rows,pr['name'],out,pr['needs'],prices=pr['prices'],hide=hide.split(','),meta=dict(client=pr.get('client',''),version='v%s'%pr.get('version',1),measurer=pr.get('measurer',''),reviewer=pr.get('reviewer',''),status=pr.get('status',''))); return FileResponse(out,filename='kamuyot_quote.xlsx')

@app.get('/api/projects/{pid}/orders/{n}.xlsx')
def order_xlsx(pid:str,n:int):
    import openpyxl
    from openpyxl.styles import Font
    pr=_load(pid); o=next((x for x in pr['orders'] if x['n']==n),None)
    if not o: raise HTTPException(404,'הזמנה לא נמצאה')
    wb=openpyxl.Workbook(); ws=wb.active; ws.sheet_view.rightToLeft=True; ws.title='הזמנה'
    ws.append([f"הזמנת רכש {n} - {pr['name']}"]); ws['A1'].font=Font(bold=True,size=16); ws.append(['ספק',o['supplier']]); ws.append(['תאריך אספקה נדרש',o['needed']]); ws.append(['הערה',o['note']]); ws.append([])
    ws.append(['חומר',"יח'",'כמות','מחיר','סה"כ'])
    for c in ws[6]: c.font=Font(bold=True)
    for i in o['items']:
        r=ws.max_row+1; ws.append([i['material'],i['unit'],i['qty'],i['price'] or 0,f'=C{r}*D{r}'])
    ws.append(['','','','סה"כ',f'=SUM(E7:E{ws.max_row})'])
    for col,w in zip('ABCDE',[40,10,12,12,14]): ws.column_dimensions[col].width=w
    out=os.path.join(_pdir(pid),f'order{n}.xlsx'); wb.save(out); return FileResponse(out,filename=f'order{n}.xlsx')

STATIC=os.path.join(os.path.dirname(os.path.abspath(__file__)),'static')
if os.path.isdir(STATIC): app.mount('/',StaticFiles(directory=STATIC,html=True),name='ui')
