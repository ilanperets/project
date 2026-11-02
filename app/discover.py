"""Name-independent discovery of drawing layers by SHAPE: tile grids (regular parallel lines) and partition walls (parallel line pairs ~10 cm apart).
Works for any office's layer naming."""
import collections, math, pymupdf
def _segs(pg):
    L=collections.defaultdict(list)
    for d in pg.get_drawings():
        if d['type']!='s' or d.get('fill') is not None: continue
        ly=d.get('layer') or ''
        for it in d['items']:
            if it[0]=='l':
                a,b=it[1],it[2]
                if abs(a.x-b.x)<0.5: L[ly].append(('v',a.x,min(a.y,b.y),max(a.y,b.y)))
                elif abs(a.y-b.y)<0.5: L[ly].append(('h',a.y,min(a.x,b.x),max(a.x,b.x)))
            elif it[0]=='re':
                r=it[1]
                L[ly]+= [('h',r.y0,r.x0,r.x1),('h',r.y1,r.x0,r.x1),('v',r.x0,r.y0,r.y1),('v',r.x1,r.y0,r.y1)]
    return L
def tile_layers(pg,scale=50,pitches=(0.3,0.45,0.6,0.8,0.9)):
    k=25.4/72*scale/1000.0; out=[]
    for ly,S in _segs(pg).items():
        if not ly or any(x in ly.lower() for x in ('hatch','htch','strip','beton','xr-')): continue      # unlayered / generic fills are not a tile grid
        S=[s for s in S if s[3]-s[2]>=40]
        if len(S)<20: continue
        ok=0;tot=0
        for kind in 'hv':
            pos=sorted({round(s[1]) for s in S if s[0]==kind}); ps=set(pos)
            for a in pos:
                tot+=1
                if any(any(abs(a+sg*d-q)<=1 for q in ps) for p in pitches for sg in (1,-1) for d in (p/k,)): ok+=1
        if tot>=10 and ok/tot>=0.6: out.append(ly)
    return out
def partition_layers(pg,scale=50):
    k=25.4/72*scale/1000.0; out=[]
    for ly,S in _segs(pg).items():
        if ly.startswith('xr-'): continue
        if 'dim' in ly.lower() or 'text' in ly.lower(): continue
        S=[s for s in S if (s[3]-s[2])*k>=0.5]
        if len(S)<10: continue
        paired=0
        for i,s in enumerate(S):
            for t in S:
                if t is s or t[0]!=s[0]: continue
                dd=abs(t[1]-s[1])*k
                if 0.06<=dd<=0.22 and min(s[3],t[3])-max(s[2],t[2])>=0.5/k*0.5: paired+=1; break
        if paired/len(S)>=0.6: out.append(ly)
    return out
