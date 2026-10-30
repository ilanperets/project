"""Quantity engines. Each takes a PDF path + scale and returns a list of lines:
{kind, ch, sub, desc, unit, q, st: נמדד|חלקי, src, need}. They only report what is measured from the drawing."""
import collections, math, os, numpy as np, cv2, pymupdf as fitz
from skimage.morphology import skeletonize
from shapely.geometry import box
from shapely.ops import unary_union

PT_MM=25.4/72
def _loc(path,x0,y0,x1,y1,label=''):
    return dict(sid=os.path.basename(path)[:-4],r=[round(x0,1),round(y0,1),round(x1,1),round(y1,1)],label=label)
def _page(path): return fitz.open(path)[0]

# ---------------- scale calibration from pile diameters ----------------
PILE_D=[30,35,40,45,50,60,70,80,90,100,120]
def _pile_circles(pg):
    out=[]
    for dr in pg.get_drawings():
        L=dr.get('layer') or ''
        if not L.startswith('fl00') or L=='fl00h': continue
        its=dr['items']; r=dr['rect']
        if len(its) not in (4,8,16) or r.width<4 or r.height<4: continue
        if not (0.85<=r.width/r.height<=1.15): continue
        out.append((L,(r.x0+r.x1)/2,(r.y0+r.y1)/2,(r.width+r.height)/2))
    seen=[];res=[]
    for c in out:
        if any(abs(c[1]-s[1])<2 and abs(c[2]-s[2])<2 for s in seen): continue
        seen.append(c); res.append(c)
    return res
def calibrate_scale(path):
    pg=_page(path); cs=_pile_circles(pg); best=(0,None)
    for sc in (20,25,50,75,100):
        ok=sum(1 for c in cs if any(abs(c[3]*PT_MM*sc/10-d)<=d*0.08 for d in PILE_D) and c[3]*PT_MM*sc/10>=25)
        if ok>best[0]: best=(ok,sc)
    return best[1],best[0],len(cs)

def piles(path,scale):
    pg=_page(path); cs=_pile_circles(pg); cnt=collections.Counter(); boxes=collections.defaultdict(list)
    for c in cs:
        d=c[3]*PT_MM*scale/10
        near=min(PILE_D,key=lambda x:abs(x-d))
        if abs(d-near)<=near*0.08 and d>=25: cnt[near]+=1; h=c[3]/2+2; boxes[near].append(_loc(path,c[1]-h,c[2]-h,c[1]+h,c[2]+h,f'Ø{near}'))
    lines=[]
    for d,n in sorted(cnt.items()):
        lines.append(dict(ch=23,sub=1,desc=f'כלונסאות קדוחים ויצוקים באתר בקוטר {d} ס"מ, לפי תוכנית יסודות',unit="יח'",q=n,st='נמדד',src='תוכנית יסודות: ספירת עיגולים בשכבות כלונסאות',need='אורך כל כלונס כתוב בטבלת מפלסים (דורש OCR או הזנה)',
            trace=dict(formula='ספירת עיגולים בשכבות הכלונסאות שקוטרם (לפי קנה המידה) תואם קוטר תקני, בסטייה עד 8%',rows=[dict(el=f'כלונסאות Ø{d}',dims=f'קוטר מדוד לפי 1:{scale}',val=n,src='שכבות fl00 בתוכנית היסודות',note='',locs=boxes[d])],checks=[dict(ok=True,t=f'קנה המידה 1:{scale} אומת מול קטרים תקניים של הכלונסאות'),dict(ok=False,t='אורך הכלונסאות לא נקרא (כתוב בטבלת מפלסים)')],params={})))
    return lines,dict(circles=len(cs),by_diameter=dict(cnt))

# ---------------- clusters ----------------
def _cluster_layer(pg,layer,gap=40):
    items=[(dr['rect'],sum(((i[1].x-i[2].x)**2+(i[1].y-i[2].y)**2)**.5 for i in dr['items'] if i[0]=='l')) for dr in pg.get_drawings() if dr.get('layer')==layer]
    n=len(items); par=list(range(n))
    def f(i):
        while par[i]!=i: par[i]=par[par[i]]; i=par[i]
        return i
    order=sorted(range(n),key=lambda i:items[i][0].x0)
    for a in range(n):
        ia=order[a]; ra=items[ia][0]
        for b in range(a+1,n):
            ib=order[b]; rb=items[ib][0]
            if rb.x0>ra.x1+gap and rb.x0>max(items[order[k]][0].x1 for k in range(a,b)) +gap: break
            if ra.x0-gap<=rb.x1 and rb.x0-gap<=ra.x1 and ra.y0-gap<=rb.y1 and rb.y0-gap<=ra.y1: par[f(ia)]=f(ib)
    cl=collections.defaultdict(lambda:[fitz.Rect(1e9,1e9,-1e9,-1e9),0.0])
    for i in range(n): c=cl[f(i)]; c[0]|=items[i][0]; c[1]+=items[i][1]
    return sorted(cl.values(),key=lambda c:-c[1])

def _raster(pg,layers,clip,px_cm,scale):
    s=(PT_MM*scale/10)/px_cm; W=int(clip.width*s)+1; H=int(clip.height*s)+1; m=np.zeros((H,W),np.uint8)
    T=lambda p:(int((p.x-clip.x0)*s),int((p.y-clip.y0)*s))
    for dr in pg.get_drawings():
        if dr.get('layer') not in layers: continue
        for it in dr['items']:
            if it[0]=='l': pts=[it[1],it[2]]
            elif it[0]=='re': r=it[1]; pts=[r.tl,r.tr,r.br,r.bl,r.tl]
            elif it[0]=='qu': q=it[1]; pts=[q.ul,q.ur,q.lr,q.ll,q.ul]
            else: continue
            if all(clip.contains(p) for p in pts): cv2.polylines(m,[np.array([T(p) for p in pts],np.int32)],False,1,1)
    return m
def _body(m,maxhalf):
    H,W=m.shape; m=cv2.dilate(m,np.ones((3,3),np.uint8)); inv=(m==0).astype(np.uint8)
    n,lab,st,_=cv2.connectedComponentsWithStats(inv,connectivity=4); dist=cv2.distanceTransform(inv,cv2.DIST_L2,5); out=m.copy()
    for i in range(1,n):
        x,y,w,h=st[i,:4]
        if x==0 or y==0 or x+w>=W or y+h>=H: continue
        comp=lab==i
        if dist[comp].max()<=maxhalf: out[comp]=1
    return out

def walls(path,scale,floor_label):
    pg=_page(path); cl=_cluster_layer(pg,'WL')
    if not cl: return [],dict(note='אין שכבת WL')
    reg=cl[0][0]; reg=fitz.Rect(reg.x0-20,reg.y0-20,reg.x1+20,reg.y1+20)
    extra=len(cl)>1 and cl[1][1]>=0.6*cl[0][1]
    m=_raster(pg,['WL'],reg,1.0,scale); body=_body(m,16)
    dist=cv2.distanceTransform(body,cv2.DIST_L2,5); sk=skeletonize(body>0); t=2*dist[sk]
    bins={'עד 12':0,'12-17':0,'17-23':0,'מעל 23':0}
    for ti in t:
        if ti<6: continue
        bins['עד 12' if ti<12 else '12-17' if ti<17 else '17-23' if ti<23 else 'מעל 23']+=1
    lines=[]; sp=(PT_MM*scale/10)
    for k,v in bins.items():
        if v>=50:
            lines.append(dict(ch=4,sub=1,desc=f'קירות בעובי {k} ס"מ, {floor_label}',unit='מטר',q=round(v/100,1),st='חלקי',src='שכבת WL בתוכנית הקומה',need='גיליון מהנדס עם קירות נושאים בלבד: מחיצות פנים עשויות לא להופיע',
                trace=dict(formula='אורך הקירות = אורך שלד (skeleton) של גוף הקיר בשכבת WL, מסווג לפי עובי מקומי',rows=[dict(el=f'קירות בעובי {k} ס"מ',dims=f'סך אורך {v/100:.1f} מ\'',val=round(v/100,1),src='שכבת WL: גוף הקיר ממולא ומדולל לשלד',note='מסומן אזור התוכנית שנסרק',locs=[_loc(path,reg.x0,reg.y0,reg.x1,reg.y1,'אזור שנסרק')])],checks=[dict(ok=not extra,t='נמצאה תוכנית נוספת בגיליון' if extra else 'תוכנית אחת בגיליון'),dict(ok=False,t='מחיצות פנים עשויות לא להופיע בגיליון מהנדס')],params={})))
    return lines,dict(extra_plan=bool(extra),wall_body_m2=round(float((body>0).sum())/1e4,2))

def roof(path,scale):
    pg=_page(path); cl=_cluster_layer(pg,'WL')
    if not cl: return [],{}
    reg=cl[0][0]; reg=fitz.Rect(reg.x0-20,reg.y0-20,reg.x1+20,reg.y1+20)
    m=_raster(pg,['WL'],reg,2.0,scale); c=cv2.morphologyEx(m,cv2.MORPH_CLOSE,np.ones((21,21),np.uint8))
    cn,_=cv2.findContours(c,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    if not cn: return [],{}
    big=max(cn,key=cv2.contourArea); a=cv2.contourArea(big)*4/1e4; per=cv2.arcLength(big,True)*0.02
    bx,by,bw,bh=cv2.boundingRect(big); sp=(PT_MM*scale/10)/2.0
    return [dict(ch=5,sub=1,desc='איטום גג, מדידה לפי קו חיצוני של המעקה',unit='מ"ר',q=round(a,1),st='חלקי',src='תוכנית גג: שטח סגור בשכבת WL',need='כולל עובי המעקה. לא כולל גגות נמוכים ומרפסות',
        trace=dict(formula='שטח הצורה הסגורה שמגדירה שכבת הקירות WL (קו חיצוני של הגג)',rows=[dict(el='גג',dims=f'היקף {per:.1f} מ\'',val=round(a,1),src='שכבת WL, מילוי הצורה החיצונית',note='',locs=[_loc(path,reg.x0+bx/sp,reg.y0+by/sp,reg.x0+(bx+bw)/sp,reg.y0+(by+bh)/sp,'גג')])],
        checks=[dict(ok=(a>=20 and per*per/a<=40),t=f'בדיקת סבירות: היקף² ÷ שטח = {per*per/a:.0f} (עד 40 סביר)')],params={}))],dict(area_m2=round(a,1),perimeter_m=round(per,1))

def openings(path,scale):
    pg=_page(path); K=PT_MM*scale/1000; boxes=[]
    for dr in pg.get_drawings():
        if dr.get('layer')=='hazit 1-0.05':
            r=dr['rect']; boxes.append(box(r.x0-.5,r.y0-.5,r.x1+.5,r.y1+.5))
    if not boxes: return [],{}
    u=unary_union(boxes); gs=list(u.geoms) if hasattr(u,'geoms') else [u]; n=0;a=0.0; orows=[]
    for g in gs:
        x0,y0,x1,y1=g.bounds; w=(x1-x0)*K;h=(y1-y0)*K
        if w>=0.3 and h>=0.3: n+=1;a+=w*h; orows.append(dict(el=f'פתח {n}',dims=f'{w:.2f} × {h:.2f}',val=round(w*h,2),src='מסגרות בשכבת הפתחים',note='',locs=[_loc(path,x0,y0,x1,y1,f'פתח {n}')]))
    if not n: return [],{}
    return [dict(ch=6,sub=1,desc='פתחים (חלונות ודלתות) לפי חזיתות',unit="יח'",q=n,st='חלקי',src='חזיתות: מסגרות בשכבת הפתחים',need=f'סה"כ שטח פתחים {a:.1f} מ"ר. יתכן שחזיתות נוספות לא נקראו',
        trace=dict(formula='כל קבוצת מסגרות מחוברת בשכבת הפתחים נספרת כפתח אחד. שטח = רוחב × גובה לפי קנה המידה',rows=orows,checks=[dict(ok=False,t='נקראה חזית אחת בלבד. חזיתות נוספות בגיליון עלולות להכפיל או להשלים את המספר')],params={}))],dict(n=n,area_m2=round(a,1))

def rooms(path,scale):
    pg=_page(path); cl=_cluster_layer(pg,'WL')
    if not cl: return [],{}
    reg=cl[0][0]; reg=fitz.Rect(reg.x0-30,reg.y0-30,reg.x1+30,reg.y1+30)
    px=2.0; m=_raster(pg,['WL','A-240','WIN','DOOR','DR'],reg,px,scale)
    solid=cv2.morphologyEx(m,cv2.MORPH_CLOSE,np.ones((7,7),np.uint8)); k=int(120/px)|1
    barrier=cv2.morphologyEx(solid,cv2.MORPH_CLOSE,cv2.getStructuringElement(cv2.MORPH_RECT,(k,k)))
    free=(barrier==0).astype(np.uint8); n,lab,st,_=cv2.connectedComponentsWithStats(free)
    ext=set(np.unique(np.concatenate([lab[0],lab[-1],lab[:,0],lab[:,-1]]))); tot=0;cnt=0; rr=[]; sp=(PT_MM*scale/10)/px
    for i in range(1,n):
        a=st[i,cv2.CC_STAT_AREA]*px*px/1e4
        if i in ext or a<1.5 or a>80: continue
        tot+=a;cnt+=1; x,y,w,h=st[i,:4]; rr.append(dict(el=f'חלל {cnt}',dims=f'{w*px/100:.2f} × {h*px/100:.2f} (תיבה חוסמת)',val=round(a,2),src='חלל סגור שזוהה בין קירות, דלתות וחלונות',note='',locs=[_loc(path,reg.x0+x/sp,reg.y0+y/sp,reg.x0+(x+w)/sp,reg.y0+(y+h)/sp,f'חלל {cnt}')]))
    if not cnt: return [],{}
    return [dict(ch=10,sub=1,desc='ריצוף, שטח נטו של חללים סגורים',unit='מ"ר',q=round(tot,1),st='חלקי',src='בסיס אדריכלי בגיליון החשמל: זיהוי חללים סגורים',need='חללים פתוחים (סלון, מטבח, אוכל) נספרים כחלל אחד. נדרש אימות מול השטחים בתוכנית',
        trace=dict(formula='שטח כל חלל סגור = מספר הפיקסלים הפנויים בין קירות/דלתות/חלונות × גודל פיקסל. חללים עד 1.5 מ"ר או מעל 80 מ"ר, וחללים פתוחים לחוץ, לא נספרים',rows=rr,checks=[dict(ok=False,t='חללים פתוחים נספרים כחלל אחד; השוו לטבלת השטחים בתוכנית'),dict(ok=True,t=f'{cnt} חללים נספרו')],params={}))],dict(rooms=cnt,total_m2=round(tot,1))


OPEN_LAYERS={'lite','WIN31','hazit 1-0.05'}
def _views(pg,C=20,k=3):
    """separate drawings on a facade sheet into views by occupancy gaps (>~60pt). returns rects sorted top-to-bottom, left-to-right"""
    m=np.zeros((int(pg.rect.height/C)+2,int(pg.rect.width/C)+2),np.uint8)
    for d in pg.get_drawings():
        if d.get('layer') in ('hazit 1','WL','lite','hazit 1-0.05','WIN31','TAVIT','0'):
            r=d['rect']
            if r.width>1500 or r.height>1500 or (r.height<4 and r.width>250): continue
            m[int(r.y0/C):int(r.y1/C)+1,int(r.x0/C):int(r.x1/C)+1]=1
    m=cv2.dilate(m,np.ones((k,k),np.uint8)); n,lab,st,_=cv2.connectedComponentsWithStats(m)
    vs=[fitz.Rect(st[i][0]*C,st[i][1]*C,(st[i][0]+st[i][2])*C,(st[i][1]+st[i][3])*C) for i in range(1,n) if st[i][4]>100]
    vs.sort(key=lambda r:(round(r.y0/400),r.x0)); return vs

def facades(path,scale):
    """windows/doors per facade: union of frame/glass rectangles on window layers, grouped under the facade title below them"""
    pg=_page(path); K=PT_MM*scale/1000; views=_views(pg)
    boxes=[]
    for dr in pg.get_drawings():
        if dr.get('layer') in OPEN_LAYERS:
            r=dr['rect']
            if r.width*K>=0.15 and r.height*K>=0.15 and r.width*K<=4 and r.height*K<=3.3: boxes.append(box(r.x0-.6,r.y0-.6,r.x1+.6,r.y1+.6))
    if not boxes: return [],{}
    u=unary_union(boxes); gs=list(u.geoms) if hasattr(u,'geoms') else [u]; rows=[]; seen=[]
    per=collections.defaultdict(list)
    for g in gs:
        x0,y0,x1,y1=g.bounds; w=(x1-x0)*K; h=(y1-y0)*K
        if w<0.35 or h<0.35 or w>4 or h>3.3: continue
        cx,cy=(x0+x1)/2,(y0+y1)/2
        vi=[i for i,v in enumerate(views) if v.contains(fitz.Point(cx,cy))]
        if not vi: continue
        if y1>=views[vi[0]].y1-80: continue  # detail boxes hanging below the ground line
        per[f'חזית {vi[0]+1}'].append((x0,y0,x1,y1,w,h))
    if not per: return [],{}
    win=[];door=[];orows=[];n=0;total=0.0
    for name,els in sorted(per.items()):
        for (x0,y0,x1,y1,w,h) in sorted(els,key=lambda e:(e[0],e[1])):
            n+=1; a=w*h; total+=a; is_door=h>=2.0
            (door if is_door else win).append(a)
            orows.append(dict(el=f'{"דלת" if is_door else "חלון"} {n} · {name}',dims=f'{w:.2f} × {h:.2f}',val=round(a,2),src='מסגרות זכוכית/חלון בחזית',note='דלת אם הגובה 2.0 מ\' ומעלה',locs=[_loc(path,x0,y0,x1,y1,str(n))]))
    chk=[dict(ok=True,t=f'נמצאו {len(views)} מבטים בגיליון, פתחים נקראו ב-{len(per)}'),dict(ok=False,t='מידות לפי קווי המסגרת בחזית; יש לאמת מול טבלת פתחים')]
    tr=lambda rs,f_:dict(formula=f_,rows=rs,checks=chk,params={})
    lines=[]
    if win: lines.append(dict(ch=12,sub=1,desc='חלונות אלומיניום',unit="יח'",q=len(win),st='חלקי',src='חזיתות: מסגרות זכוכית בכל החזיתות',need='ספירה לפי חזיתות; סוגי פתיחה ופרטים לפי תוכנית פתחים',trace=tr([r for r in orows if r['el'].startswith('חלון')],'כל קבוצת מסגרות מחוברת = חלון אחד')))
    if door: lines.append(dict(ch=12,sub=1,desc='דלתות ותריסי אלומיניום',unit="יח'",q=len(door),st='חלקי',src='חזיתות: פתחים בגובה 2.0 מ\' ומעלה',need='הפרדה בין דלת לתריס לפי תוכנית פתחים',trace=tr([r for r in orows if r['el'].startswith('דלת')],'פתח בגובה 2.0 מ\' ומעלה = דלת')))
    lines.append(dict(ch=6,sub=1,desc='פתחים (חלונות ודלתות) לפי חזיתות',unit="יח'",q=n,st='חלקי',src='חזיתות: מסגרות בשכבות החלונות, כל החזיתות',need=f'סה"כ שטח פתחים {total:.1f} מ"ר',trace=tr(orows,'כל קבוצת מסגרות מחוברת נספרת כפתח. שטח = רוחב × גובה לפי קנה המידה')))
    return lines,dict(n=n,area_m2=round(total,2),facades=len(per))
