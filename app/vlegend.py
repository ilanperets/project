"""Vector legend matching: every legend row's swatch (the drawing paths inside its cell) is searched in the plan as the same set of
paths in the same relative positions (4 rotations). Exact, fast, layer-name independent."""
import collections, math, pymupdf
from . import legend as LG
def _sz(d): r=d['rect']; return max(r.width,r.height) or 0.0
def _sig(d):
    """scale-invariant signature: lengths relative to the path's own size"""
    r=d['rect']; z=_sz(d) or 1.0; parts=[]
    for it in d['items']:
        if it[0]=='l': parts.append(('l',round(it[1].distance_to(it[2])/z,1)))
        elif it[0]=='c': parts.append(('c',round(it[1].distance_to(it[4])/z,1)))
        elif it[0]=='re': parts.append(('r',)+tuple(sorted((round(it[1].width/z,1),round(it[1].height/z,1)))))
        elif it[0]=='qu': parts.append(('q',)+tuple(sorted((round(it[1].rect.width/z,1),round(it[1].rect.height/z,1)))))
    w,h=sorted((round(r.width/z,1),round(r.height/z,1)))
    return ('f' if d.get('fill') is not None else 's',tuple(sorted(parts)),w,h)
def _ctr(d): r=d['rect']; return ((r.x0+r.x1)/2,(r.y0+r.y1)/2)
def analyse(path):
    pg=pymupdf.open(path)[0]; rows=LG._rows(path)
    if not rows: return []
    ds=[d for d in pg.get_drawings() if max(d['rect'].width,d['rect'].height)<=45]
    M=pg.rotation_matrix
    for d in ds: d['rect']=d['rect']*M if pg.rotation else d['rect']
    xs=[_ctr(d) for d in ds]
    ex=pymupdf.Rect(min(l['x'] for l in rows)-40,min(l['y'] for l in rows)-40,max(l['x']+l['w'] for l in rows)+80,max(l['y']+l['h'] for l in rows)+60)
    by=collections.defaultdict(list); G=collections.defaultdict(list)
    for i,d in enumerate(ds):
        c=xs[i]
        if ex.x0<=c[0]<=ex.x1 and ex.y0<=c[1]<=ex.y1: continue
        sg=_sig(d); by[sg].append(i); G[(sg,int(c[0]//24),int(c[1]//24))].append(i)
    # table rows: horizontal separator lines spanning the legend; each row = all OCR lines between two separators
    M2=pg.rotation_matrix; lx0=min(l['x'] for l in rows)-120; lx1=max(l['x']+l['w'] for l in rows)+90
    ly0=min(l['y'] for l in rows)-30; ly1=max(l['y']+l['h'] for l in rows)+30
    seps=set()
    for d in pg.get_drawings():
        for it in d['items']:
            if it[0]=='l':
                p1=it[1]*M2 if pg.rotation else it[1]; p2=it[2]*M2 if pg.rotation else it[2]
                if abs(p1.y-p2.y)<0.3 and abs(p1.x-p2.x)>=(lx1-lx0)*0.45 and ly0<=p1.y<=ly1: seps.add(round(p1.y,1))
    seps=sorted(seps)
    xr_all=sorted(l['x']+l['w'] for l in rows)[len(rows)//2]
    groups=[]
    if len(seps)>=4:
        for a_,b_ in zip(seps,seps[1:]):
            ls=[l for l in rows if a_<=l['y']+l['h']/2<=b_]
            if ls: groups.append(dict(text=' | '.join(l['text'] for l in sorted(ls,key=lambda l:l['y'])),y0=a_,y1=b_,xr=max(l['x']+l['w'] for l in ls)))
    if not groups: groups=[dict(text=l['text'],y0=l['y']+l['h']/2-13,y1=l['y']+l['h']/2+13,xr=l['x']+l['w']) for l in rows]
    out=[]
    for l in groups:
        xr=l['xr']; cell=pymupdf.Rect(xr+3,l['y0']+1,xr+70,l['y1']-1)
        sw=[i for i,d in enumerate(ds) if not any(t in (d.get('layer') or '').lower() for t in ('text','ktav','tex','note','dim','tit')) and cell.x0<=xs[i][0]<=cell.x1 and cell.y0<=xs[i][1]<=cell.y1 and max(ds[i]['rect'].width,ds[i]['rect'].height)<=30]
        if not sw or len(sw)>14: out.append(dict(text=l['text'],n=None,why='לא נגזר סמל')); continue
        cx=sum(xs[i][0] for i in sw)/len(sw); cy=sum(xs[i][1] for i in sw)/len(sw)
        sigs=[(_sig(ds[i]),xs[i][0]-cx,xs[i][1]-cy,_sz(ds[i])) for i in sw]
        anchor=max((s_ for s_ in sigs if 0<len(by.get(s_[0],[]))<=300),key=lambda s_:s_[3],default=None)
        if anchor is None: out.append(dict(text=l['text'],n=0)); continue
        cand=by.get(anchor[0],[])
        if not cand: out.append(dict(text=l['text'],n=0)); continue
        found=[]; asz=anchor[3]
        for ci in cand:
            ax,ay=xs[ci]; k=_sz(ds[ci])/asz if asz else 1.0
            if not (0.5<=k<=3.0): continue
            for rot in range(4):
                def tr(dx,dy):
                    for _ in range(rot): dx,dy=-dy,dx
                    return dx*k,dy*k
                ox,oy=tr(anchor[1],anchor[2]); bx,by_=ax-ox,ay-oy
                ok=0
                for s_,dx,dy,sz_ in sigs:
                    px,py=tr(dx,dy); tx,ty=bx+px,by_+py; tol=max(1.2,sz_*k*0.25)
                    gx,gy=int(tx//24),int(ty//24)
                    if any(abs(_sz(ds[j])-sz_*k)<=tol and math.hypot(xs[j][0]-tx,xs[j][1]-ty)<=tol for ax_ in (-1,0,1) for ay_ in (-1,0,1) for j in G.get((s_,gx+ax_,gy+ay_),())): ok+=1
                if ok>=(len(sigs) if len(sigs)<4 else max(len(sigs)-1,int(0.75*len(sigs)+0.99))): found.append((round(bx),round(by_),round(k,2))); break
        # dedupe
        uniq=[]
        for f in found:
            if all(math.hypot(f[0]-u[0],f[1]-u[1])>3 for u in uniq): uniq.append(f)
        out.append(dict(text=l['text'],n=len(uniq),parts=len(sigs)))
    return out

CATS=[
 (r'שקעי? חשמל|בית תקע|תקע',('נקודות תקע',"נק'")),
 (r'תקשורת|טלפו|טלוויזיה',('נקודות תקשורת וטלוויזיה',"נק'")),
 (r'מפסק',('מפסקים',"נק'")),
 (r'גוף תאורה|נקודת מאור|גופי תאורה',('נקודות מאור',"נק'")),
]
def lines(path):
    """-> (BOQ lines, info) for one electrical sheet, from its own legend. Composite symbols add their per-symbol multipliers."""
    import re
    rows=analyse(path); tot=collections.Counter(); seen=[]; unread=0
    for r in rows:
        n=r.get('n')
        if n is None: unread+=1; continue
        if not n: continue
        t=r['text']; seen.append((t[:40],n))
        parts=t.split(' | ') if ' | ' in t else [t]
        counted=False
        for p in parts:
            m=re.match(r'\s*(\d+)\s*(.*)',p); mult=int(m.group(1)) if m and ' | ' in t or (m and re.search(r'שקעי? (חשמל|תקשורת)',p)) else 1; txt=m.group(2) if (m and mult!=1 or m and re.search(r'שקעי? (חשמל|תקשורת)',p)) else p
            if re.search(r'הרכב|לחצן|שעון',p): continue
            for rx,(desc,u) in CATS:
                if re.search(rx,txt): tot[(desc,u)]+=n*mult; counted=True; break
    L=[dict(ch=8,sub=1,desc=d,unit=u,q=q,st='חלקי',src='ספירת סמלים לפי המקרא של התוכנית (התאמת צורה בכל סיבוב)',need='לאמת מול התוכנית, סמלים שלא הופיעו במקרא לא נספרו',cover=[d]) for (d,u),q in tot.items() if q]
    return L,dict(found=seen,legend_rows=len(rows),unread=unread)
