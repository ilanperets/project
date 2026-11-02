"""Autonomous symbol counting from the sheet's own legend: legend rows are read (Hebrew OCR), each row's swatch is cut out and
template-matched on the plan (4 rotations). No labelling by the user and no dependence on layer names."""
import re, numpy as np, cv2, pymupdf
from . import ocr
ZL=4; ZP=2
VOCAB=re.compile(r'שקע|תקע|מפסק|נקודת|לחצן|גוף|תאורה|מזגן|מפזר|מפוח|גלאי|ספרינקלר|מצלמ|לוח|ארון|שעון|פנס|תעלה|ברז|כיור|אסלה')
def _rows(path):
    L=ocr.lines(path,zoom=1.5)
    R=[l for l in L if VOCAB.search(l['text']) and len(l['text'])>=6]
    if len(R)<4: return []
    # legend rows share a right edge: take the biggest group of lines whose right edges are within 45pt
    xs=sorted(R,key=lambda l:l['x']+l['w']); best=[]
    for a in xs:
        g=[l for l in xs if abs((l['x']+l['w'])-(a['x']+a['w']))<=45]
        if len(g)>len(best): best=g
    return sorted(best,key=lambda l:l['y']) if len(best)>=4 else []
def _clean(im):
    a=np.array(im)<140; h,w=a.shape
    a8=a.astype(np.uint8)*255
    hk=cv2.morphologyEx(a8,cv2.MORPH_OPEN,cv2.getStructuringElement(cv2.MORPH_RECT,(int(w*0.6),1)))
    vk=cv2.morphologyEx(a8,cv2.MORPH_OPEN,cv2.getStructuringElement(cv2.MORPH_RECT,(1,int(h*0.6))))
    a8=cv2.subtract(a8,cv2.dilate(cv2.bitwise_or(hk,vk),np.ones((3,3),np.uint8)))
    ys,xs=np.where(a8>0)
    if len(xs)<40: return None
    return a8[ys.min():ys.max()+1,xs.min():xs.max()+1]
def swatches(path):
    pg=pymupdf.open(path)[0]; out=[]
    for l in _rows(path):
        xr=l['x']+l['w']; yc=l['y']+l['h']/2
        clip=pymupdf.Rect(xr+3,yc-13,xr+62,yc+13)
        t=_clean(ocr._img(pg,ZL,clip))
        if t is None or max(t.shape)>ZL*50 or max(t.shape)<ZL*3: continue
        out.append(dict(text=l['text'],tpl=t,x=l['x'],y=l['y'],xr=xr,yc=yc))
    return out
def count(path,thr=0.8,dbg=None):
    pg=pymupdf.open(path)[0]; sw=swatches(path)
    if not sw: return []
    pm=pg.get_pixmap(matrix=pymupdf.Matrix(ZP,ZP),colorspace=pymupdf.csGRAY)
    img=np.frombuffer(pm.samples,np.uint8).reshape(pm.height,pm.width)
    ink=((img<205).astype(np.uint8))*255
    ex0=min(s['x'] for s in sw)-40; ex1=max(s['xr'] for s in sw)+80; ey0=min(s['y'] for s in sw)-40; ey1=max(s['y'] for s in sw)+60
    ink[int(ey0*ZP):int(ey1*ZP),int(ex0*ZP):int(ex1*ZP)]=0        # legend table itself
    res=[]
    for s in sw:
        t=cv2.resize(255-s['tpl'] if False else s['tpl'],None,fx=ZP/ZL,fy=ZP/ZL,interpolation=cv2.INTER_AREA)
        if min(t.shape)<4: continue
        pts=[]
        for k in range(4):
            tk=np.rot90(t,k).copy()
            m=cv2.matchTemplate(ink,tk,cv2.TM_CCOEFF_NORMED)
            ys,xs=np.where(m>=thr)
            if dbg is not None and m.size: dbg.append((s['text'][:25],k,round(float(m.max()),2)))
            for y,x in zip(ys,xs): pts.append((m[y,x],x,y,tk.shape[1],tk.shape[0]))
        pts.sort(reverse=True); keep=[]
        for sc,x,y,w,h in pts:
            if all(abs(x-a)>max(w,aw)*0.7 or abs(y-b)>max(h,ah)*0.7 for _,a,b,aw,ah in keep): keep.append((sc,x,y,w,h))
        res.append(dict(text=s['text'],n=len(keep)))
    return res
