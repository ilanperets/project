import sys, json, numpy as np, cv2, pymupdf as fitz
from skimage.morphology import skeletonize
pdf,out=sys.argv[1:3]; fx0,fy0,fx1,fy1=map(float,sys.argv[3:7]); scale=50
WLL=['WL']; CL=['fl00h']
pg=fitz.open(pdf)[0]; R=pg.rect
clip=fitz.Rect(R.width*fx0,R.height*fy0,R.width*fx1,R.height*fy1)
px=1.0; s=(25.4/72*scale/10)/px
W=int(clip.width*s)+1; H=int(clip.height*s)+1
T=lambda p:(int((p.x-clip.x0)*s),int((p.y-clip.y0)*s))
def raster(layers):
    m=np.zeros((H,W),np.uint8)
    for dr in pg.get_drawings():
        if dr.get('layer') not in layers: continue
        for it in dr['items']:
            if it[0]=='l': pts=[it[1],it[2]]
            elif it[0]=='re': r=it[1]; pts=[r.tl,r.tr,r.br,r.bl,r.tl]
            elif it[0]=='qu': q=it[1]; pts=[q.ul,q.ur,q.lr,q.ll,q.ul]
            else: continue
            if all(clip.contains(p) for p in pts): cv2.polylines(m,[np.array([T(p) for p in pts],np.int32)],False,1,1)
    return m
def body(m,maxhalf):
    m=cv2.dilate(m,np.ones((3,3),np.uint8))
    inv=(m==0).astype(np.uint8)
    n,lab,st,_=cv2.connectedComponentsWithStats(inv,connectivity=4)
    dist=cv2.distanceTransform(inv,cv2.DIST_L2,5)
    out=m.copy()
    for i in range(1,n):
        x,y,w,h=st[i,:4]
        if x==0 or y==0 or x+w>=W or y+h>=H: continue
        comp=lab==i
        if dist[comp].max()<=maxhalf: out[comp]=1
    return out
wl=body(raster(WLL),16); cc=body(raster(CL),22)
cc_only=cc.copy(); wl_only=(wl==1)&(cc==0)
dist=cv2.distanceTransform(wl_only.astype(np.uint8),cv2.DIST_L2,5); sk=skeletonize(wl_only)
t=2*dist[sk]*px
bins={'<=12':0,'12-17':0,'17-23':0,'>23':0}
for ti in t:
    if ti<6: continue
    k='<=12' if ti<12 else '12-17' if ti<17 else '17-23' if ti<23 else '>23'
    bins[k]+=px
n,lab,st,_=cv2.connectedComponentsWithStats(cc_only)
comps=[]
for i in range(1,n):
    a=st[i,cv2.CC_STAT_AREA]*px*px/1e4
    if a<0.03: continue
    comps.append((round(a,2),round(st[i,2]*px/100,2),round(st[i,3]*px/100,2)))
res=dict(wall_body_m2=round(wl_only.sum()*px*px/1e4,2),wall_len_m={k:round(v/100,1) for k,v in bins.items()},conc_m2=round(cc_only.sum()*px*px/1e4,2),n_conc=len(comps),conc_comps=sorted(comps,reverse=True)[:40])
vis=np.full((H,W,3),255,np.uint8); vis[wl_only]=(60,60,200); vis[cc_only==1]=(60,160,60)
cv2.imwrite(out,vis); print(json.dumps(res,ensure_ascii=False)); json.dump(res,open(out+'.json','w'),ensure_ascii=False)
