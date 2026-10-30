"""Wet-room engine: reads tile-layout sheets (a plan plus four internal elevations A-D per room) from the vector drawing.
Every quantity comes with a calculation trace: the formula, each element with its dimensions, the source, and sanity checks.
Nothing here is priced. Geometry only. Rotation-aware (sheets are often saved rotated by 90 or 270 degrees)."""
import math, pymupdf as fitz

PT_CM=2.54/72   # one PDF point in cm on paper; multiplied by the drawing scale to get cm in reality
LAYER_TILE='ker'

def _view(pg):
    M=pg.rotation_matrix
    for dr in pg.get_drawings(): yield dr, dr['rect']*M

def _elevations(pg,K):
    """single-stroke rectangles on the tile layer that look like a wall elevation: 2.0-4.0 m high, at least 1 m wide"""
    out=[]
    for dr,r in _view(pg):
        if dr.get('layer')!=LAYER_TILE or len(dr['items'])!=1: continue
        w,h=r.width*K,r.height*K
        if 100<=w<=2000 and 200<=h<=400: out.append((r,w,h))
    out.sort(key=lambda t:(round(t[0].y0/60),t[0].x0))
    return out

def _openings(pg,R,K,K2):
    ops=[]
    for dr,r in _view(pg):
        if dr.get('layer')!='SANO' or not(R.contains(r)): continue
        w,h=r.width*K,r.height*K
        if w<45 or h<45 or w>=R.width*K*0.95: continue
        sill=(R.y1-r.y1)*K
        kind='דלת' if (sill<8 and h>=190) else 'חלון'
        ops.append(dict(kind=kind,w=round(w),h=round(h),sill=round(sill)))
    ops.sort(key=lambda o:(o['kind'],-o['w']))
    return ops

def _floor(A,B,C,D):
    """floor area from the four wall lengths. Rectangle: A~B and C~D. Right trapezoid: one wall slanted, A^2 ~ B^2 + (C-D)^2."""
    rect=abs(A-B)<=0.02*max(A,B) and abs(C-D)<=0.02*max(C,D)
    if rect: return A*(C+D)/2,'מלבן',dict(base=A)
    for base,slant,nm in ((B,A,'A'),(A,B,'B')):
        if abs(math.hypot(base,C-D)-slant)<=0.015*slant: return base*(C+D)/2,'טרפז ישר זווית',dict(base=base,slanted=nm)
    return None,'צורה לא פתורה',{}

def tile_layout(path,P,room_label,sheet_file=''):
    """returns (lines, info). P needs: deduct_limit (m2), wp_upturn (m), room_scale (denominator, e.g. 50)"""
    pg=fitz.open(path)[0]; sc=P.get('room_scale',50); K=PT_CM*sc
    ev=_elevations(pg,K)
    if len(ev)<3: return [],dict(note='לא נמצאו חזיתות פנים בשכבת האריחים')
    names='ABCD'; E=[]
    for i,(R,w,h) in enumerate(ev[:4]):
        E.append(dict(name=names[i],w=round(w),h=round(h),ops=_openings(pg,R,K,K)))
    W={e['name']:e['w'] for e in E}; Hh=[e['h'] for e in E]
    lim=P.get('deduct_limit',0.5); up=P.get('wp_upturn',0.2)
    checks=[]
    hmin,hmax=min(Hh),max(Hh)
    checks.append(dict(ok=210<=hmin and hmax<=380,t=f'גובה החדר {hmin/100:.2f} מ\' בקנה מידה 1:{sc}: {"סביר לגובה קומה" if 210<=hmin and hmax<=380 else "חריג, בדוק קנה מידה"}'))
    # --- floor
    fl,shape,fi=(None,'',{})
    if len(E)==4:
        fl,shape,fi=_floor(W['A'],W['B'],W['C'],W['D']); fl=None if fl is None else fl/1e4
    perim=sum(e['w'] for e in E)/100
    rows_floor=[]
    if fl is not None:
        if shape=='מלבן': dims=f"{W['A']/100:.2f} × {(W['C']+W['D'])/200:.2f}"; nt='מלבן: אורך חזית A × רוחב חזית C'
        else: dims=f"{fi['base']/100:.2f} × ({W['C']/100:.2f} + {W['D']/100:.2f}) ÷ 2"; nt=f'טרפז ישר זווית: בסיס × ממוצע שני הצלעות הניצבות. אימות: הצלע המשופעת ({W[fi["slanted"]]/100:.2f}) = √(בסיס² + הפרש²)'
        rows_floor.append(dict(el=room_label,dims=dims,val=round(fl,2),src=f'חזיתות A-D, {sheet_file}',note=nt))
        checks.append(dict(ok=True,t=f'צורת הרצפה זוהתה כ{shape} ואומתה מול אורך הצלע המשופעת'))
    else: checks.append(dict(ok=False,t='צורת הרצפה לא נפתרה מארבע החזיתות. נדרשת מדידה מהתוכנית'))
    # --- walls
    rows_wall=[]; gross=0; ded=0; kept=[]
    for e in E:
        g=e['w']*e['h']/1e4; gross+=g
        rows_wall.append(dict(el=f'{room_label}, חזית {e["name"]}',dims=f'{e["w"]/100:.2f} × {e["h"]/100:.2f}',val=round(g,2),src=f'שכבת האריחים, {sheet_file}',note=''))
        for o in e['ops']:
            a=o['w']*o['h']/1e4; take=a>lim
            rows_wall.append(dict(el=f'   {o["kind"]} בחזית {e["name"]} ({o["w"]/100:.2f} × {o["h"]/100:.2f}, מעמד {o["sill"]/100:.2f})',dims=f'−{o["w"]/100:.2f} × {o["h"]/100:.2f}' if take else f'{o["w"]/100:.2f} × {o["h"]/100:.2f}',val=round(-a,2) if take else 0.0,src='שכבת הפתחים',note='מנוכה' if take else f'לא מנוכה: {a:.2f} מ"ר, מתחת לסף {lim:g}'))
            if take: ded+=a
    net=gross-ded
    nop=sum(len(e['ops']) for e in E)
    checks.append(dict(ok=True,t=f'{nop} פתחים נמצאו בחזיתות; ניכוי רק לפתח גדול מ-{lim:g} מ"ר (הסף הוא פרמטר, לאימות מול הספר)'))
    lines=[]
    if fl is not None:
        lines.append(dict(ch=10,sub=1,desc='ריצוף אריחים',unit='מ"ר',q=round(fl,2),st='נמדד',src=f'חזיתות פנים ({room_label})',need='',cover=['ריצוף אריחים'],
            trace=dict(formula='שטח נטו של החדר לפי הפנים בין הקירות',rows=rows_floor,checks=checks,params={})))
        lines.append(dict(ch=5,sub=1,desc='איטום חדרים רטובים כולל עלייה של 20 ס"מ על הקירות',unit='מ"ר',q=round(fl+perim*up,2),st='נמדד',src=f'חזיתות פנים ({room_label})',need=f'גובה העלייה על הקירות {up*100:.0f} ס"מ לפי הסעיף',
            trace=dict(formula='שטח הרצפה + (היקף החדר × גובה העלייה)',rows=rows_floor+[dict(el=f'{room_label}, עלייה על הקירות',dims=f'{perim:.2f} × {up:.2f}',val=round(perim*up,2),src='היקף = סכום ארבע החזיתות',note='')],checks=checks,params=dict(wp_upturn=up))))
    lines.append(dict(ch=10,sub=2,desc='חיפוי קירות בחדרים רטובים',unit='מ"ר',q=round(net,2),st='נמדד',src=f'חזיתות פנים ({room_label})',need='',
        trace=dict(formula='סכום שטחי החזיתות (רוחב × גובה) פחות פתחים גדולים מהסף',rows=rows_wall,checks=checks,params=dict(deduct_limit=lim),gross=round(gross,2),deducted=round(ded,2))))
    lines.append(dict(ch=0,sub=1,desc='פירוק אריחים מקירות וריצוף, כולל סיתות טיט',unit='מ"ר',q=round(gross+(fl or 0),2),st='חלקי',src=f'חזיתות פנים ({room_label})',need='הפירוק נמדד ברוטו. הנחה שהחיפוי הקיים כיסה את כל החזיתות ואת הרצפה',
        trace=dict(formula='פירוק נמדד ללא ניכוי פתחים: שטח חזיתות ברוטו + רצפה',rows=rows_wall[:0]+[dict(el='חזיתות ברוטו',dims='',val=round(gross,2),src='',note=''),dict(el='רצפה',dims='',val=round(fl or 0,2),src='',note='')],checks=checks,params={})))
    return lines,dict(room=room_label,floor_m2=round(fl,2) if fl is not None else None,wall_net_m2=round(net,2),wall_gross_m2=round(gross,2),shape=shape,openings=nop)


def _quad_dims(it):
    q=it[1]; a=math.dist(q.ul,q.ur); b=math.dist(q.ul,q.ll); return a,b

def wetroom_plan(path,P,room_label,sheet_file=''):
    """counts shower trays and measures sink counters from the architectural view (the top view on the sheet).
    The same fixtures are drawn again in the plumbing and electrical views, so only the top-most view is read."""
    pg=fitz.open(path)[0]; sc=P.get('room_scale',50); K=PT_CM*sc; M=pg.rotation_matrix
    trays=[];ctr=[]
    for dr in pg.get_drawings():
        if dr.get('layer')!='SANO' or len(dr['items'])!=1 or dr['items'][0][0]!='qu': continue
        r=dr['rect']*M; a,b=_quad_dims(dr['items'][0]); w,h=sorted((a*K,b*K))
        if 70<=w<=100 and 70<=h<=170: trays.append((r.y0,w,h))
        elif 45<=w<=90 and 150<=h<=400: ctr.append((r.y0,w,h))
    if not trays and not ctr: return [],dict(note='לא נמצאו אגני מקלחת או משטחים')
    ys=sorted({round(t[0]) for t in trays+ctr}); top=ys[0]
    inview=lambda dy: dy<=450/K          # same view: within about 4.5 m (paper points) of the first element
    trays=[t for t in trays if inview(t[0]-top)]; ctr=[c for c in ctr if inview(c[0]-top)]
    lines=[]
    chk=[dict(ok=True,t='הספירה נעשתה בתוכנית האדריכלות (האזור העליון בגיליון). אותם כלים מופיעים שוב בתוכניות האינסטלציה והחשמל ולא נספרו פעמיים')]
    if trays:
        rows=[dict(el=f'{room_label}, אגן מקלחת {i}',dims=f'{w/100:.2f} × {h/100:.2f}',val=1,src=f'שכבת הכלים הסניטריים, {sheet_file}',note='נגיש (גדול)' if h>=140 else '') for i,(y,w,h) in enumerate(sorted(trays,key=lambda t:t[0]),1)]
        lines.append(dict(ch=7,sub=1,desc='תאי מקלחת (אגן, ניקוז ומערבל)',unit="יח'",q=len(trays),st='נמדד',src=f'תוכנית אדריכלות ({room_label})',need='סוג האגן והמערבל מהמפרט',trace=dict(formula='ספירת אגני מקלחת בתוכנית',rows=rows,checks=chk,params={})))
    if ctr:
        rows=[dict(el=f'{room_label}, משטח כיורים',dims=f'{h/100:.2f} × {w/100:.2f}',val=round(w*h/1e4,2),src=f'שכבת הכלים הסניטריים, {sheet_file}',note='אורך × עומק') for y,w,h in ctr]
        a=sum(r['val'] for r in rows)
        lines.append(dict(ch=10,sub=3,desc='משטחי שיש/גרניט, בעובי 2 ס"מ',unit='מ"ר',q=round(a,2),st='חלקי',src=f'תוכנית אדריכלות ({room_label})',need='ללא סינר, מגן התזה וחזית. נדרש לאשר מול הפרט',trace=dict(formula='אורך × עומק של המשטח, לפי הצלעות האמיתיות (גם במשטח משופע)',rows=rows,checks=chk,params={})))
    return lines,dict(room=room_label,trays=len(trays),counters=len(ctr))


# ---------- fixture symbols (sanitary + electrical) ----------
SAN_LAYERS={'SANO','SANIT'}; ELEC_LAYERS={'HASHMAL','graff-elc','graff-elc--HUT'}
SAN_LABELS={'toilet':('אסלות',"יח'"),'toilet_acc':('אסלות',"יח'"),'sink':('כיורי רחצה',"יח'"),'sink_acc':('כיורי רחצה',"יח'")}
SAN_NAMES={'toilet':'אסלה','toilet_acc':'אסלה נגישה','sink':'כיור','sink_acc':'כיור נגיש'}

def _clusters(pg,layers,K,gap=0.4):
    M=pg.rotation_matrix; D=pg.derotation_matrix; items=[]
    for dr in pg.get_drawings():
        if dr.get('layer') not in layers: continue
        r=dr['rect']*M
        if r.width*K>150 or r.height*K>150: continue
        items.append((r,len(dr['items'])))
    n=len(items); par=list(range(n))
    def f(i):
        while par[i]!=i: par[i]=par[par[i]]; i=par[i]
        return i
    import collections
    grid=collections.defaultdict(list)
    for i,(r,_) in enumerate(items):
        for gx in range(int((r.x0-gap)//20),int((r.x1+gap)//20)+1):
            for gy in range(int((r.y0-gap)//20),int((r.y1+gap)//20)+1): grid[(gx,gy)].append(i)
    for ids in grid.values():
        for a in range(len(ids)):
            for b in range(a+1,len(ids)):
                i,j=ids[a],ids[b]
                if f(i)==f(j): continue
                p,q=items[i][0],items[j][0]
                if p.x0-gap<=q.x1 and q.x0-gap<=p.x1 and p.y0-gap<=q.y1 and q.y0-gap<=p.y1: par[f(i)]=f(j)
    comp=collections.defaultdict(list)
    for i in range(n): comp[f(i)].append(i)
    out=[]
    for ids in comp.values():
        R=fitz.Rect(1e9,1e9,-1e9,-1e9); nit=0
        for i in ids: R|=items[i][0]; nit+=items[i][1]
        w,h=sorted((round(R.width*K/5)*5,round(R.height*K/5)*5))
        if w<20 or h<20: continue
        U=R*D
        out.append(dict(sig=repr((w,h,nit)),vy=R.y0,x=U.x0,y=U.y0,w=U.width,h=U.height))
    return out

def fixture_groups(path,P=None):
    """symbol groups by rotation-independent signature. The same fixture is drawn in several views on the sheet (architecture,
    plumbing, electrical), so each signature is counted per view and the largest per-view count is used, never the sum."""
    pg=fitz.open(path)[0]; K=PT_CM*((P or {}).get('room_scale',50))
    cl=_clusters(pg,SAN_LAYERS|ELEC_LAYERS,K)
    ys=sorted({round(c['vy']) for c in cl}); bands=[]; 
    for y in ys:
        if not bands or y-bands[-1][-1]>450/K: bands.append([y])
        else: bands[-1].append(y)
    def band(y):
        for i,b in enumerate(bands):
            if b[0]<=round(y)<=b[-1]: return i
        return 0
    g={}
    for c in cl:
        e=g.setdefault(c['sig'],dict(sig=c['sig'],per={},x=c['x'],y=c['y'],w=c['w'],h=c['h']))
        e['per'][band(c['vy'])]=e['per'].get(band(c['vy']),0)+1
    out=[dict(sig=e['sig'],n=max(e['per'].values()),per=e['per'],x=e['x'],y=e['y'],w=e['w'],h=e['h']) for e in g.values()]
    return sorted(out,key=lambda e:-e['n'])

def fixtures(path,P,labels,room_label,sheet_file=''):
    import collections
    groups=fixture_groups(path,P); lines=[]; tot=collections.defaultdict(list); un=0
    for g in groups:
        k=labels.get(g['sig'])
        if k in SAN_LABELS: tot[SAN_LABELS[k]].append((k,g))
        elif k in ('light','socket','switch','comm','power'): tot[('E',k)].append((k,g))
        elif not k and g['n']>=2: un+=g['n']
    chk=[dict(ok=True,t='כל כלי נספר פעם אחת: אותו סמל מופיע בכמה תצוגות (אדריכלות, אינסטלציה, חשמל), ונלקחת התצוגה עם המספר הגבוה ביותר')]
    if un: chk.append(dict(ok=False,t=f'{un} סמלים בגיליון עוד לא סווגו. הספירה כוללת רק צורות שסומנו'))
    from .symbols import LABELS,LABEL_NAMES
    for key,items in tot.items():
        if key[0]=='E':
            k=key[1]; desc,unit=LABELS[k]; ch,sub=8,1
        else: desc,unit=key; ch,sub=7,1
        # count per view over every label of this kind, then take the view with the highest total
        bands=set()
        for _,g in items: bands|=set(g['per'])
        best=max(bands,key=lambda b:sum(g['per'].get(b,0) for _,g in items))
        rows=[dict(el=f'{room_label}, {SAN_NAMES.get(k) or LABEL_NAMES.get(k,k)}',dims='',val=g['per'][best],src=f'סמל שסווג על ידך, {sheet_file}',note='') for k,g in items if g['per'].get(best)]
        q=sum(r['val'] for r in rows)
        lines.append(dict(ch=ch,sub=sub,desc=desc,unit=unit,q=q,st='חלקי' if un else 'נמדד',src=f'ספירת סמלים ({room_label})',need=chk[-1]['t'] if un else '',trace=dict(formula='ספירת סמלים שסווגו, בתצוגה שבה יש הכי הרבה מהסוג',rows=rows,checks=chk,params={})))
    return lines,dict(room=room_label,groups=len(groups),counted={f'{k[1] if k[0]=="E" else k[0]}':sum(g['n'] for _,g in v) for k,v in tot.items()},unlabelled=un)
