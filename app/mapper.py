"""Generic layer mapper: any layered CAD PDF can be measured by mapping a layer to a BOQ item.
Modes: length (m of strokes), area (m2 of closed boxes/quads, union), count (symbols, by proximity), circles (round symbols)."""
import collections, math, pymupdf as fitz
from shapely.geometry import box, Polygon
from shapely.ops import unary_union
PT=25.4/72
def _page(p): return fitz.open(p)[0]
def _len(dr):
    t=0
    for i in dr['items']:
        if i[0]=='l': t+=i[1].distance_to(i[2])
        elif i[0] in('re',): r=i[1]; t+=2*(r.width+r.height)
        elif i[0]=='qu': q=i[1]; t+=q.ul.distance_to(q.ur)+q.ur.distance_to(q.lr)+q.lr.distance_to(q.ll)+q.ll.distance_to(q.ul)
        elif i[0]=='c': t+=i[1].distance_to(i[4])
    return t
def _polys(dr):
    out=[]
    for i in dr['items']:
        if i[0]=='re' and i[1].width>0.5 and i[1].height>0.5: out.append(box(i[1].x0,i[1].y0,i[1].x1,i[1].y1))
        elif i[0]=='qu':
            q=i[1]; p=Polygon([(q.ul.x,q.ul.y),(q.ur.x,q.ur.y),(q.lr.x,q.lr.y),(q.ll.x,q.ll.y)])
            if p.is_valid and p.area>0.5: out.append(p)
    return out
def _cluster_count(rects,gap=8):
    n=len(rects); par=list(range(n))
    def f(i):
        while par[i]!=i: par[i]=par[par[i]]; i=par[i]
        return i
    for i in range(n):
        for j in range(i+1,n):
            a,b=rects[i],rects[j]
            if a.x0-gap<=b.x1 and b.x0-gap<=a.x1 and a.y0-gap<=b.y1 and b.y0-gap<=a.y1: par[f(i)]=f(j)
    return len({f(i) for i in range(n)})
def stats(path,scale):
    pg=_page(path); L=collections.defaultdict(lambda:dict(n=0,len=0.0,polys=[],circ=0,rects=[]))
    for dr in pg.get_drawings():
        e=L[dr.get('layer') or '(ללא שכבה)']; e['n']+=1; e['len']+=_len(dr); e['polys']+=_polys(dr); e['rects'].append(dr['rect'])
        r=dr['rect']
        if len(dr['items']) in(4,8,16) and r.width>2 and 0.85<=r.width/max(r.height,.01)<=1.15: e['circ']+=1
    k=PT*scale/1000; out=[]
    for name,e in L.items():
        if e['n']<2: continue
        area=unary_union(e['polys']).area*k*k if e['polys'] else 0
        sm=[r for r in e['rects'] if r.width<60 and r.height<60]
        out.append(dict(layer=name,n=e['n'],length_m=round(e['len']*k,1),area_m2=round(area,1),circles=e['circ'],symbols=_cluster_count(sm[:3000]) if sm else 0,x=e['rects'][0].x0,y=e['rects'][0].y0))
    return sorted(out,key=lambda x:-x['n'])
def measure(path,scale,layer,mode):
    pg=_page(path); k=PT*scale/1000; ln=0; polys=[]; circ=0; rects=[]
    for dr in pg.get_drawings():
        if (dr.get('layer') or '(ללא שכבה)')!=layer: continue
        ln+=_len(dr); polys+=_polys(dr); rects.append(dr['rect']); r=dr['rect']
        if len(dr['items']) in(4,8,16) and r.width>2 and 0.85<=r.width/max(r.height,.01)<=1.15: circ+=1
    if mode=='length': return round(ln*k,1)
    if mode=='area': return round(unary_union(polys).area*k*k,1) if polys else 0
    if mode=='circles': return circ
    return _cluster_count([r for r in rects if r.width<60 and r.height<60])
