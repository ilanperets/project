"""Plumbing measurement from colour-coded Revit-style plans (pipes are drawn as coloured raster lines, legend = colour swatch + system name).
Pipe length per system = skeleton length of that legend colour inside the plan area, converted with the sheet scale."""
import re, numpy as np, pymupdf, cv2
from skimage.morphology import skeletonize
PT_M=0.000352778   # 1 pt on paper in metres

def _rot(pg): return pg.rotation_matrix

def scale_of(pg):
    t=pg.get_text()
    c=[int(x) for x in re.findall(r'1\s*:\s*(\d{2,3})\b',t)]
    return max(set(c),key=c.count) if c else None

def legend(pg):
    """[(name,(r,g,b) 0-255,rect)] from filled swatches with a label to the right."""
    M=_rot(pg); sw=[]
    for x in pg.get_drawings():
        f=x.get('fill')
        if not f or x.get('type')!='f': continue
        q=pymupdf.Rect(x['rect'])*M
        if 55<=q.width<=80 and 9<=q.height<=18 and f!=(1.0,1.0,1.0) and not (f[0]==f[1]==f[2]):
            sw.append((q,f))
    words=[(pymupdf.Rect(w[:4])*M,w[4]) for w in pg.get_text('words')]
    out=[]
    for q,f in sorted(sw,key=lambda a:(a[0].x0,a[0].y0)):
        my=(q.y0+q.y1)/2
        ws=[(r.x0,t) for r,t in words if r.x0>q.x1-2 and r.x0<q.x1+170 and abs((r.y0+r.y1)/2-my)<9]
        if not ws: continue
        name=' '.join(t for _,t in sorted(ws,reverse=True))
        out.append((name,tuple(int(round(v*255)) for v in f),q))
    return out

def length_by_system(path,zoom=1.5,tol=34):
    pg=pymupdf.open(path)[0]; M=_rot(pg)
    sc=scale_of(pg); lg=legend(pg)
    if not lg or not sc: return None
    W=pg.rect.height if pg.rotation in(90,270) else pg.rect.width
    xmax=min(q.x0 for _,_,q in lg)-330        # plan area ends where the title block starts
    zoom=min(zoom,(1.6e7/(pg.rect.width*pg.rect.height))**0.5)
    pix=pg.get_pixmap(matrix=pymupdf.Matrix(zoom,zoom),colorspace=pymupdf.csRGB)
    img=np.frombuffer(pix.samples,np.uint8).reshape(pix.h,pix.w,3).astype(np.int16)
    if pg.rotation: img=np.rot90(img,-pg.rotation//90) if False else img
    # pixmap is already in page (unrotated) space; rotate to the visual orientation
    k={90:3,180:2,270:1,0:0}[pg.rotation]; img=np.rot90(img,k)
    H,Wd=img.shape[:2]; res={}
    for name,rgb,q in lg:
        d=np.abs(img-np.array(rgb,dtype=np.int16)).sum(2)
        ch=img.max(2)-img.min(2); lch=max(rgb)-min(rgb)
        m=(d<tol*2.2)&(abs(ch-lch)<45)
        if lch<45: res[name]=None; continue
        m[:, int(xmax*zoom):]=False
        m=m.astype(np.uint8)
        if m.sum()<30: res[name]=0.0; continue
        ys,xs=np.nonzero(m); y0,y1,x0,x1=ys.min(),ys.max()+1,xs.min(),xs.max()+1
        m=m[y0:y1,x0:x1]
        m=cv2.morphologyEx(m,cv2.MORPH_CLOSE,np.ones((3,3),np.uint8))
        n,lab,st,_=cv2.connectedComponentsWithStats(m,connectivity=8)
        big=np.zeros(n,bool); big[1:]=st[1:,cv2.CC_STAT_AREA]>=25
        keep=big[lab].astype(np.uint8)
        sk=skeletonize(keep>0)
        a=sk[:, :-1]&sk[:, 1:]; b=sk[:-1,:]&sk[1:,:]; c=sk[:-1,:-1]&sk[1:,1:]; e=sk[:-1,1:]&sk[1:,:-1]
        px=a.sum()+b.sum()+np.sqrt(2)*(c.sum()+e.sum())
        res[name]=float(px/zoom*PT_M*sc)
    # identical legend colours cannot be told apart in the raster: merge names
    byc={}
    for name,rgb,q in lg: byc.setdefault(rgb,[]).append(name)
    merged={}
    for rgb,names in byc.items():
        v=max([res.get(n) or 0 for n in names]); merged[' / '.join(names)]=v
    return dict(scale=sc,systems=merged)
if __name__=='__main__':
    import sys,json
    for p in sys.argv[1:]: print(p,json.dumps(length_by_system(p),ensure_ascii=False,indent=1))

def tags(pg):
    """Diameter tags written on the plan: [(system text, diameter mm)] from lines like 'Ø160 mm ביוב'."""
    out=[]
    for b in pg.get_text('dict')['blocks']:
        for l in b.get('lines',[]):
            t=' '.join(s['text'] for s in l['spans']).strip()
            m=re.search(r'Ø\s*(\d{1,3}(?:\.\d+)?)\s*(?:mm|מ"מ)?\s*(.*)',t)
            if m: out.append((re.sub(r'\s+',' ',m.group(2)).strip(' -'),round(float(m.group(1)),2)))
    return out
