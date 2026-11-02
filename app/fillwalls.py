"""Walls from filled shapes, for plans without layer names. Principle: walls/partitions are drawn as thin filled strips
(5-30 cm after scale); each fill colour is one wall type. We measure strip length (skeleton of the colour mask) and thickness,
take the wall height from notes written on the plan ("עד גובה 380"), and flag the colour->type mapping for confirmation."""
import re, collections, numpy as np, cv2, pymupdf
from skimage.morphology import skeletonize
_c=lambda t:re.sub(r'[‎‏‪-‮]','',t)

def _polys(pg):
    P=collections.defaultdict(list)
    for dr in pg.get_drawings():
        f=dr.get('fill')
        if not f or tuple(f)==(1.0,1.0,1.0) : continue
        r=dr['rect']
        if r.width*r.height>pg.rect.width*pg.rect.height*0.02: continue
        pts=[]
        for it in dr['items']:
            if it[0]=='l': pts+=[(it[1].x,it[1].y),(it[2].x,it[2].y)]
            elif it[0]=='re': q=it[1]; pts+=[(q.x0,q.y0),(q.x1,q.y0),(q.x1,q.y1),(q.x0,q.y1)]
        if len(pts)>=3: P[tuple(round(x,2) for x in f)].append(pts)
    return P

def heights(pg):
    """wall heights written on the plan, in metres (e.g. 'עד גובה 380')"""
    hs=[]
    for b in pg.get_text('blocks'):
        t=' '.join(_c(b[4]).split())
        for m in re.finditer(r'(?:עד )?גובה\s*(\d{3})',t):
            v=int(m.group(1))/100
            if 2<=v<=6: hs.append(v)
    return hs

def measure(path,scale,z=2.0):
    pg=pymupdf.open(path)[0]; H,W=int(pg.rect.height*z)+2,int(pg.rect.width*z)+2
    mm=25.4/72*scale/1000/z; out=[]
    for col,pl in _polys(pg).items():
        if len(pl)<3: continue
        m=np.zeros((H,W),np.uint8)
        for pts in pl: cv2.fillPoly(m,[(np.array(pts)*z).astype(np.int32)],255)
        area=(m>0).sum()*mm*mm
        if area<0.5: continue
        sk=skeletonize(m>0).sum()*mm
        if sk<5: continue
        th=area/sk*100
        if 5<=th<=30: out.append(dict(color=col,count=len(pl),length=round(sk,1),thick=round(th),area=round(area,1)))
    hs=heights(pg)
    return sorted(out,key=lambda x:-x['length']),(sorted(hs)[len(hs)//2] if hs else None)

def lines(path,scale,default_h=3.0):
    walls,h=measure(path,scale)
    L=[]; info=dict(types=len(walls),height=h)
    if not walls: return L,info
    H=h or default_h; hs='לפי הערה בתוכנית' if h else 'הונח (לא נמצא בתוכנית)'
    for i,w in enumerate(walls[:4]):
        if w['thick']<=14:   # thin strip: partition
            q=round(w['length']*H,1)
            L.append(dict(ch=22,sub=1,desc='מחיצות גבס חד קרומיות ודו קרומיות עם קונסטרוקציה',unit='מ"ר',q=q,st='חלקי',src=f"אורך {w['length']} מ' בעובי כ-{w['thick']} ס\"מ (צבע מילוי {i+1}) × גובה {H} מ' ({hs})",need='לאשר שהצבע הוא מחיצת גבס לפי מקרא התוכנית',cover=['מחיצות גבס חד קרומיות ודו קרומיות עם קונסטרוקציה'],
                          trace=dict(formula='אורך × גובה',rows=[dict(el=f'מחיצה (צבע {i+1})',dims=f"{w['length']} × {H}",val=q,src='שרטוט')],checks=[])))
            L.append(dict(ch=11,sub=1,desc='צבע פנים בקירות ובתקרות',unit='מ"ר',q=round(2*q,1),st='חלקי',src='שני צידי מחיצות הגבס שנמדדו',need='להוסיף קירות קיימים וחיפויים',cover=['צבע פנים בקירות ובתקרות']))
            L.append(dict(ch=10,sub=2,desc='שיפולים',unit='מ"א',q=round(2*w['length'],1),st='חלקי',src='שני צידי מחיצות הגבס, בלי ניכוי פתחים',need='ניכוי פתחי דלתות',cover=['שיפולים']))
        else:
            L.append(dict(ch=4,sub=1,desc=f"קירות קיימים או בנויים בעובי {round(w['thick'],-1) if w['thick']>=15 else w['thick']} ס\"מ",unit='מ"א',q=w['length'],st='חלקי',src=f"אורך רצועה ממולאת (צבע {i+1}), עובי כ-{w['thick']} ס\"מ",need='לאשר סוג הקיר לפי מקרא',cover=[]))
    return L,info
