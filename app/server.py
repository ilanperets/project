import json, os, re, shutil, time, uuid
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from . import classify as C, engines as E, boq as B, brain as BR
import datetime

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
    pr=json.load(open(p,encoding='utf-8'))
    for k,v in (('materials',[]),('prices',{}),('mprices',{}),('params',{}),('bills',[]),('orders',[]),('quotes',[]),('needs',[]),('log',[])): pr.setdefault(k,v)
    return pr
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
    pr=dict(id=pid,name=(body.get('name') or 'פרויקט חדש').strip()[:80],scale=None,sheets=[],boq=None,needs=[],log=[],materials=[],prices={},mprices={},params={},bills=[],orders=[],quotes=[]); _save(pr); return pr

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
    P=BR.params(pr)
    wall_m=sum(l['q'] for l in lines if l['ch']==4 and l['unit']=='מטר'); op_m2=sum(l['q'] for l in lines if l['ch']==6 and l['unit']=='מ"ר')
    if wall_m:
        A=max(wall_m*P['wall_height']*2-op_m2,0)
        for ch,d in ((9,'טיח פנים וחוץ, הערכה: אורך קירות × גובה × 2 צדדים פחות פתחים'),(11,'צבע, הערכה: כמו שטח הטיח')):
            lines.append(dict(ch=ch,sub=1,desc=d,unit='מ"ר',q=round(A,1),st='חלקי',src='נגזר מאורך הקירות',need='גובה קירות מוגדר כהנחה; חסר היקף חדרים מדויק'))
    pr['lines']=lines; pr['asm']=assumptions; pr['log']=log
    rebuild(pr); _save(pr)
    return pr

def rebuild(pr):
    """BOQ = engine lines + manual items, with quantity overrides and hidden items; then materials and needs"""
    P=BR.params(pr); sheets=pr['sheets']; lines=list(pr.get('lines',[]))
    for m in pr.get('manual',[]): lines.append(dict(ch=m['ch'],sub=m.get('sub',1),desc=m['desc'],unit=m['unit'],q=m['q'],st='ידני',src='הוזן ידנית',need=''))
    present={s['type'] for s in sheets}; needed={e[4] for e in B.EXPECTED}
    missing=sorted(t for t in needed if t not in present)
    unbuilt=sorted(t for t in present if t not in B.BUILT and t in needed or t=='unknown' and t in present)
    rows=B.build(pr['name'],lines,present,pr.get('ov'),set(pr.get('hidden',[])),pr.get('chnames'))
    mats,used=BR.explode(rows,P); asm=list(pr.get('asm',[]))
    for k in used: asm.append(dict(t=f"הנחה: {BR.DEFAULT_PARAMS[k]['label']} = {P[k]}",why=BR.DEFAULT_PARAMS[k]['why'],gives='פירוק לחומרים',how='עדכן בהגדרות הפרויקט'))
    pr['boq']=rows; pr['materials']=mats; pr['needs']=B.needs(sheets,missing,unbuilt,asm)

@app.post('/api/projects/{pid}/builder')
def builder(pid:str,body:dict):
    """add / quantity override / hide / restore / rename chapter, without re-running the engines"""
    pr=_load(pid); a=body.get('action')
    if 'lines' not in pr: pr['lines']=[]
    if a=='add':
        if not body.get('desc') or not body.get('unit'): raise HTTPException(400,'חסר תיאור או יחידה')
        pr.setdefault('manual',[]).append(dict(ch=int(body.get('ch') or 99),sub=int(body.get('sub') or 1),desc=body['desc'].strip(),unit=body['unit'].strip(),q=float(body['q']) if body.get('q') not in ('',None) else None))
        if body.get('chname'): pr.setdefault('chnames',{})[str(int(body['ch']))]=body['chname']
    elif a=='qty':
        pr.setdefault('ov',{})[body['desc']]=float(body['q']) if body.get('q') not in ('',None) else None
    elif a=='hide': pr.setdefault('hidden',[]).append(body['desc'])
    elif a=='unhide': pr['hidden']=[d for d in pr.get('hidden',[]) if d!=body['desc']]
    elif a=='rm_manual': pr['manual']=[m for m in pr.get('manual',[]) if m['desc']!=body['desc']]
    else: raise HTTPException(400,'פעולה לא מוכרת')
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

@app.get('/api/projects/{pid}/export.xlsx')
def export(pid:str):
    pr=_load(pid)
    if not pr.get('boq'): raise HTTPException(400,'עוד לא חושב כתב')
    out=os.path.join(_pdir(pid),'boq.xlsx'); B.to_xlsx(pr['boq'],pr['name'],out,pr['needs']); return FileResponse(out,filename='kamuyot_boq.xlsx')



# ---------- pricing, memory, bills, orders ----------
MEM=os.path.join(ROOT,'prices_memory.json')
def _mem():
    try: return json.load(open(MEM,encoding='utf-8'))
    except Exception: return []

@app.post('/api/projects/{pid}/params')
def set_params(pid:str,body:dict):
    pr=_load(pid); pr['params']={k:float(v) for k,v in body.items() if k in BR.DEFAULT_PARAMS}; _save(pr); return run(pid) if pr.get('boq') else pr

from .spec import SPEC, CHAPTERS
@app.get('/api/spec')
def spec(): return dict(chapters={str(k):v for k,v in CHAPTERS.items()},items=SPEC)

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
    return dict(name=pr['name'],sheets=len(pr['sheets']),items=len(items),measured=sum(1 for r in items if r.get('q')),priced=sum(1 for r in items if r.get('q') and pr['prices'].get(r['code'])),total=tot,chapters=by,bills=len(pr['bills']),billed=billed,orders=len(pr['orders']),needs=len(pr['needs']))

@app.post('/api/projects/{pid}/bills')
def new_bill(pid:str,body:dict):
    """body: {pct:{code:cumulative_pct}}"""
    pr=_load(pid); P=BR.params(pr); prev=pr['bills'][-1]['pct'] if pr['bills'] else {}
    cum={k:float(v) for k,v in body.get('pct',{}).items()}
    for k,v in prev.items(): cum.setdefault(k,v)
    b=BR.bill(pr['boq'],pr['prices'],cum,prev,P); b.update(n=len(pr['bills'])+1,date=str(datetime.date.today()),pct=cum,total_this=b['this'])
    pr['bills'].append(dict(n=b['n'],date=b['date'],pct=cum,total=b['total'],this=b['this'],retention=b['retention'],vat=b['vat'],net=b['net'])); _save(pr); return b

@app.get('/api/projects/{pid}/bills/{n}')
def get_bill(pid:str,n:int):
    pr=_load(pid); P=BR.params(pr); i=n-1
    if i<0 or i>=len(pr['bills']): raise HTTPException(404,'חשבון לא נמצא')
    prev=pr['bills'][i-1]['pct'] if i else {}; b=BR.bill(pr['boq'],pr['prices'],pr['bills'][i]['pct'],prev,P); b.update(n=n,date=pr['bills'][i]['date']); return b

@app.post('/api/projects/{pid}/orders')
def new_order(pid:str,body:dict):
    pr=_load(pid)
    items=[dict(material=i['material'],unit=i['unit'],qty=float(i['qty']),price=pr['mprices'].get(i['material'])) for i in body.get('items',[]) if float(i.get('qty',0))>0]
    if not items: raise HTTPException(400,'לא נבחרו חומרים')
    o=dict(n=len(pr['orders'])+1,supplier=(body.get('supplier') or 'ספק לא צוין').strip(),needed=body.get('needed',''),note=body.get('note',''),date=str(datetime.date.today()),status='טיוטה',items=items)
    pr['orders'].append(o); _save(pr); return o

@app.post('/api/projects/{pid}/orders/{n}')
def order_status(pid:str,n:int,body:dict):
    pr=_load(pid); o=next((x for x in pr['orders'] if x['n']==n),None)
    if not o: raise HTTPException(404,'הזמנה לא נמצאה')
    if body.get('status') in ('טיוטה','נשלחה','סופקה חלקית','סופקה','בוטלה'): o['status']=body['status']
    _save(pr); return o

@app.get('/api/projects/{pid}/quote.xlsx')
def quote(pid:str):
    pr=_load(pid)
    if not pr.get('boq'): raise HTTPException(400,'עוד לא חושב כתב')
    rows=[dict(r) for r in pr['boq']]
    import copy
    out=os.path.join(_pdir(pid),'quote.xlsx'); B.to_xlsx(rows,pr['name'],out,pr['needs'],prices=pr['prices']); return FileResponse(out,filename='kamuyot_quote.xlsx')

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
