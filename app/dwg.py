"""DWG input. A DWG is read with libredwg (a separate Node process, see tools/dwg2json.mjs), its model space is expanded
(block inserts, arrays, bulge arcs) and redrawn as a vector PDF at project scale 1:50 with one optional-content layer per CAD
layer. After that every engine, the classifier and the viewer treat it exactly like a PDF sheet, with exact geometry and real layers.
Units are inferred from the drawing extents (the unit flag inside files is unreliable)."""
import json, math, os, subprocess, tempfile, collections, shutil
import pymupdf as fitz

TOOLS=os.path.join(os.path.dirname(__file__),'tools')
PT_PER_M=2834.646/50          # at 1:50
FONT='/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'

def read_json(src,timeout=300):
    out=tempfile.NamedTemporaryFile(suffix='.json',delete=False).name
    try:
        r=subprocess.run(['node',os.path.join(TOOLS,'dwg2json.mjs'),src,out],capture_output=True,text=True,timeout=timeout,cwd=TOOLS)
        if r.returncode!=0: raise RuntimeError('DWG לא נקרא: '+(r.stderr or r.stdout)[-160:])
        return json.load(open(out,encoding='utf-8'))
    finally:
        try: os.remove(out)
        except OSError: pass

def _mat(tx,ty,sx,sy,rot):
    c,s=math.cos(rot),math.sin(rot); return (c*sx,-s*sy,s*sx,c*sy,tx,ty)   # x'=a x + c y + e ; y'=b x + d y + f with a=c*sx,b=s*sx,c_=-s*sy,d=c*sy
def _mul(m,n):
    a,b,c,d,e,f=m; A,B,C,D,E,F=n
    return (a*A+c*B,b*A+d*B,a*C+c*D,b*C+d*D,a*E+c*F+e,b*E+d*F+f)
def _ap(m,x,y): return (m[0]*x+m[2]*y+m[4],m[1]*x+m[3]*y+m[5])
def _arc_pts(p,q,bulge,step=0.12):
    if abs(bulge)<1e-9: return [q]
    dx,dy=q[0]-p[0],q[1]-p[1]; d=math.hypot(dx,dy)
    if d<1e-12: return [q]
    th=4*math.atan(bulge); r=d/(2*math.sin(th/2)); mx,my=(p[0]+q[0])/2,(p[1]+q[1])/2
    h=r*math.cos(th/2); nx,ny=-dy/d,dx/d; cx,cy=mx+nx*h*(1 if bulge>0 else -1)*-1,my+ny*h*(1 if bulge>0 else -1)*-1
    a0=math.atan2(p[1]-cy,p[0]-cx); n=max(2,int(abs(th)/step)); out=[]
    for i in range(1,n+1):
        a=a0+th*i/n; out.append((cx+abs(r)*math.cos(a),cy+abs(r)*math.sin(a)))
    out[-1]=q; return out

def expand(J,limit=900000):
    """-> {layer:{'poly':[(pts,closed,hatch)],'text':[(x,y,h,rot,txt)]}} in drawing units"""
    blocks=J['blocks']; hidden={l['n'] for l in J['layers'] if l['off'] or l['fr']}
    out=collections.defaultdict(lambda:dict(poly=[],text=[])); cnt=[0]
    def put(layer,kind,item):
        if layer in hidden or cnt[0]>limit: return
        cnt[0]+=1; out[layer][kind].append(item)
    def walk(ents,m,depth,lay0):
        for e in ents:
            t=e['t']; L=e['l'] if e['l']!='0' or not lay0 else lay0
            if t=='L': put(L,'poly',([_ap(m,*e['a']),_ap(m,*e['b'])],False,False))
            elif t=='P':
                v=e['v']; pts=[_ap(m,v[0][0],v[0][1])] if v else []
                for i in range(1,len(v)+ (1 if e['c'] else 0)):
                    a=v[i-1]; b=v[i%len(v)]
                    for q in _arc_pts((a[0],a[1]),(b[0],b[1]),a[2]): pts.append(_ap(m,*q))
                if len(pts)>1: put(L,'poly',(pts,bool(e['c']),bool(e.get('h'))))
            elif t=='C':
                cx,cy=e['c']; r=e['r']; pts=[_ap(m,cx+r*math.cos(a*math.pi/18),cy+r*math.sin(a*math.pi/18)) for a in range(37)]; put(L,'poly',(pts,True,False))
            elif t=='A':
                cx,cy=e['c']; r=e['r']; a0,a1=e['s'],e['e']
                if a1<=a0: a1+=2*math.pi
                n=max(3,int((a1-a0)/0.15)); pts=[_ap(m,cx+r*math.cos(a0+(a1-a0)*i/n),cy+r*math.sin(a0+(a1-a0)*i/n)) for i in range(n+1)]; put(L,'poly',(pts,False,False))
            elif t=='E':
                cx,cy=e['c']; mx,my=e['m']; q=e['q']; a0,a1=e['s'],e['e']
                if a1<=a0: a1+=2*math.pi
                n=max(8,int((a1-a0)/0.2)); pts=[]
                for i in range(n+1):
                    a=a0+(a1-a0)*i/n; pts.append(_ap(m,cx+mx*math.cos(a)-my*q*math.sin(a),cy+my*math.cos(a)+mx*q*math.sin(a)))
                put(L,'poly',(pts,False,False))
            elif t=='S':
                v=e['v']; 
                if len(v)==4: v=[v[0],v[1],v[3],v[2]]
                put(L,'poly',([_ap(m,*q) for q in v],True,True))
            elif t=='T':
                x,y=_ap(m,*e['p']); sc=math.hypot(m[0],m[1]); put(L,'text',(x,y,(e['h'] or 0)*sc,e['r']+math.atan2(m[1],m[0]),e['x']))
            elif t=='I' and depth<6 and e['n'] in blocks:
                bl=blocks[e['n']]; bx,by=bl['base']
                for i in range(max(1,e['nr'])):
                    for j in range(max(1,e['nc'])):
                        mm=_mul(m,_mul(_mat(e['p'][0]+j*e['dc'],e['p'][1]+i*e['dr'],e['sx'],e['sy'],e['r']),(1,0,0,1,-bx,-by)))
                        walk(bl['ents'],mm,depth+1,L if L!='0' else lay0)
    walk(J['model'],(1,0,0,1,0,0),0,None); return out

def _factor(J,lay):
    xs=[];ys=[]
    for d in lay.values():
        for pts,_,hh in d['poly']:
            if hh: continue
            for x,y in pts[:: max(1,len(pts)//4)]: xs.append(x); ys.append(y)
    if not xs: return 1.0,'m',0
    xs.sort(); ys.sort(); k=len(xs); lo=int(k*.02); hi=max(lo+1,int(k*.98)-1)
    span=max(xs[hi]-xs[lo],ys[hi]-ys[lo]); hdr=J.get('units',0)
    if hdr==1: return 0.0254,'inch',span
    if hdr==2: return 0.3048,'ft',span
    if span<400: return 1.0,'m',span
    if span<4000: return 0.01,'cm',span
    return 0.001,'mm',span

def dwg_to_pdf(src,out,J=None):
    J=J or read_json(src); lay=expand(J); f,u,span=_factor(J,lay)
    xs=[];ys=[]
    for d in lay.values():
        for pts,_,hh in d['poly']:
            for x,y in pts[:: max(1,len(pts)//3)]: xs.append(x*f); ys.append(y*f)
    if not xs: raise RuntimeError('אין גיאומטריה בקובץ')
    xs.sort(); ys.sort(); k=len(xs); lo=int(k*.003); hi=k-1-lo
    x0,x1,y0,y1=xs[lo],xs[hi],ys[lo],ys[hi]; cropped=False
    if (x1-x0)*PT_PER_M>13500 or (y1-y0)*PT_PER_M>13500: cropped=True; x1=min(x1,x0+13400/PT_PER_M); y1=min(y1,y0+13400/PT_PER_M)
    M=30; W=(x1-x0)*PT_PER_M+2*M; H=(y1-y0)*PT_PER_M+2*M
    doc=fitz.open(); pg=doc.new_page(width=W,height=H); has_font=os.path.exists(FONT); fl=False
    P=lambda x,y:(M+(x*f-x0)*PT_PER_M,M+(y1-y*f)*PT_PER_M)
    n=0
    for name,d in sorted(lay.items()):
        oc=doc.add_ocg(name,on=True)
        for pts,closed,hatch in d['poly']:
            pp=[P(x,y) for x,y in pts]
            if all(not(-5<=a<=W+5 and -5<=b<=H+5) for a,b in pp[:: max(1,len(pp)//4)]): continue
            if hatch: pg.draw_polyline(pp,color=None,fill=(0.35,0.35,0.35),closePath=True,oc=oc,fill_opacity=.4)
            else: pg.draw_polyline(pp,color=(0,0,0),width=0.35,closePath=closed,oc=oc)
            n+=1
        for x,y,h,rot,tx in d['text']:
            px,py=P(x,y); fs=max(4.0,min(60.0,(h or 0.25*(1 if f==1 else 1))*f*PT_PER_M)) if h else 7.0
            if not(-5<=px<=W+5 and -5<=py<=H+5): continue
            heb=any('֐'<=c<='׿' for c in tx); ang=int(round(math.degrees(rot)/90))*90%360
            try:
                if heb and has_font:
                    if not fl: pg.insert_font(fontname='dj',fontfile=FONT); fl=True
                    pg.insert_text((px,py),tx[:120].split('\n')[0],fontsize=fs,fontname='dj',rotate=ang,oc=oc)
                else: pg.insert_text((px,py),tx[:120].split('\n')[0],fontsize=fs,rotate=ang,oc=oc)
            except Exception: pass
    doc.save(out,deflate=True,garbage=3); doc.close()
    return dict(units=u,factor=f,span=round(span,1),prims=n,layers=len(lay),width_m=round(x1-x0,1),height_m=round(y1-y0,1),cropped=cropped,hdr_units=J.get('units',0))
