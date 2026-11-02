"""Ceiling areas from the tile-grid layer of a ceiling plan (acoustic modular tiles). Grid lines are rasterised, closed to solid areas, wall fills subtracted."""
import numpy as np, pymupdf, statistics
from PIL import Image, ImageDraw
from scipy import ndimage as ndi
PT_M=lambda scale: 25.4/72*scale/1000.0           # metres per PDF point at 1:scale
def tiles(path,scale=50,layers=('CL-tile',),wall_layers=('CL-WALL','AA-WALL')):
    pg=pymupdf.open(path)[0]; W,H=int(pg.rect.width),int(pg.rect.height)
    ds=pg.get_drawings(); g=[d for d in ds if (d.get('layer') or '') in layers]
    if len(g)<20: return None
    S=1                                              # raster px per PDF pt
    im=Image.new('L',(W*S+2,H*S+2),0); dr=ImageDraw.Draw(im)
    pit=[]; ys=sorted({round(d['rect'].y0,0) for d in g if d['rect'].height<1}); 
    for a,b in zip(ys,ys[1:]):
        if 10<b-a<80: pit.append(b-a)
    pitch=statistics.median(pit) if pit else 34.0
    for d in g:
        r=d['rect']; dr.line([r.x0*S,r.y0*S,r.x1*S,r.y1*S],fill=255,width=2)
    m=np.array(im)>0
    k=int(pitch*1.3)|1
    fill=ndi.binary_closing(m,structure=np.ones((k,k),bool))
    fill=ndi.binary_fill_holes(fill)
    wl=Image.new('L',im.size,0); wd=ImageDraw.Draw(wl)
    for d in ds:
        if (d.get('layer') or '') in wall_layers and d.get('fill') is not None:
            r=d['rect']; wd.rectangle([r.x0*S,r.y0*S,r.x1*S,r.y1*S],fill=255)
    fill&=~(np.array(wl)>0)
    lab,n=ndi.label(fill); sizes=ndi.sum(fill,lab,range(1,n+1))
    keep=[i+1 for i,s in enumerate(sizes) if s>=(pitch*3)**2]
    area_pt=float(sum(sizes[i-1] for i in keep))
    return dict(area_m2=round(area_pt*PT_M(scale)**2,1),areas=len(keep),pitch_cm=round(pitch*PT_M(scale)*100))
