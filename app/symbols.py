"""Electrical symbol library. Strokes of the same colour that touch are clustered into one symbol; symbols are grouped
by a rotation-independent signature. The user labels a signature once (light / socket / switch ...) and the system
counts that signature on every electrical sheet from then on."""
import collections, pymupdf as fitz
LAYERS={'elect','ELEC'}
LABELS={'light':('נקודות מאור',"נק'"),'socket':('נקודות תקע',"נק'"),'switch':('מפסקים',"נק'"),'comm':('נקודות תקשורת וטלוויזיה',"נק'"),
        'power':('נקודות כוח (מזגן, תנור, דוד)',"נק'"),'panel':('לוחות חשמל',"יח'"),'ignore':None}
LABEL_NAMES={'toilet':'אסלה','toilet_acc':'אסלה נגישה','sink':'כיור','sink_acc':'כיור נגיש','light':'גוף תאורה','socket':'שקע','switch':'מפסק','comm':'תקשורת / טלוויזיה','power':'נקודת כוח','panel':'לוח חשמל','ignore':'התעלם'}

def _page(p): return fitz.open(p)[0]
def clusters(path,gap=1.2):
    pg=_page(path); items=[]
    for dr in pg.get_drawings():
        if dr.get('layer') not in LAYERS: continue
        r=dr['rect']
        if r.width>60 or r.height>60: continue
        col=tuple(round(x,1) for x in dr['color']) if dr.get('color') else (tuple(round(x,1) for x in dr['fill']) if dr.get('fill') else None)
        items.append((r,dr['items'],col))
    n=len(items); par=list(range(n))
    def f(i):
        while par[i]!=i: par[i]=par[par[i]]; i=par[i]
        return i
    grid=collections.defaultdict(list)
    for i,(r,_,_) in enumerate(items):
        for gx in range(int((r.x0-gap)//12),int((r.x1+gap)//12)+1):
            for gy in range(int((r.y0-gap)//12),int((r.y1+gap)//12)+1): grid[(gx,gy)].append(i)
    for ids in grid.values():
        for a in range(len(ids)):
            for b in range(a+1,len(ids)):
                i,j=ids[a],ids[b]
                if f(i)==f(j) or items[i][2]!=items[j][2]: continue
                ri,rj=items[i][0],items[j][0]
                if ri.x0-gap<=rj.x1 and rj.x0-gap<=ri.x1 and ri.y0-gap<=rj.y1 and rj.y0-gap<=ri.y1: par[f(i)]=f(j)
    comp=collections.defaultdict(list)
    for i in range(n): comp[f(i)].append(i)
    out=[]
    for ids in comp.values():
        R=fitz.Rect(1e9,1e9,-1e9,-1e9); parts=[]
        for i in ids:
            R|=items[i][0]
            for it in items[i][1]:
                if it[0]=='l': parts.append(('l',round(it[1].distance_to(it[2]))))
                elif it[0]=='c': parts.append(('c',round(it[1].distance_to(it[4]))))
                elif it[0]=='re': parts.append(('r',round(it[1].width)))
        if R.width>45 or R.height>45 or max(R.width,R.height)<2.5: continue
        sig=repr((tuple(sorted(parts)),tuple(sorted((round(R.width/1.5),round(R.height/1.5))))))
        out.append(dict(sig=sig,x=R.x0,y=R.y0,w=R.width,h=R.height,col=items[ids[0]][2]))
    return out,pg

def _plan_region(pg):
    wl=[dr['rect'] for dr in pg.get_drawings() if dr.get('layer')=='WL']
    if wl:
        R=fitz.Rect(1e9,1e9,-1e9,-1e9)
        for r in wl: R|=r
        return R
    return fitz.Rect(0,0,pg.mediabox.width*0.72,pg.mediabox.height)

def groups(path):
    cl,pg=clusters(path); reg=_plan_region(pg); reg=fitz.Rect(reg.x0-40,reg.y0-40,reg.x1+40,reg.y1+40)
    g=collections.OrderedDict()
    for c in cl:
        if not (reg.x0<=c['x'] and c['x']+c['w']<=reg.x1 and reg.y0<=c['y'] and c['y']+c['h']<=reg.y1): continue
        e=g.setdefault(c['sig'],dict(sig=c['sig'],n=0,x=c['x'],y=c['y'],w=c['w'],h=c['h']))
        e['n']+=1
    return sorted(g.values(),key=lambda e:-e['n'])

def count(path,labels):
    """labels: {sig: label key}. returns engine lines"""
    tot=collections.Counter(); allg=groups(path); un=0
    for g in allg:
        k=labels.get(g['sig'])
        if k and LABELS.get(k): tot[k]+=g['n']
        elif not k and g['n']>=2: un+=g['n']
    need=f'עוד {un} סמלים בגיליון לא סווגו. ספירה זו מכסה רק צורות שסימנת' if un else ''
    return [dict(ch=8,sub=1,desc=LABELS[k][0],unit=LABELS[k][1],q=n,st='חלקי' if un else 'נמדד',src='ספירת סמלים שסווגו על ידך',need=need) for k,n in tot.items()],dict(counted=dict(tot),unlabelled=un)

def crop_png(path,x,y,w,h,out,px=140):
    pg=_page(path); pad=max(w,h)*0.6+3; r=fitz.Rect(x-pad,y-pad,x+w+pad,y+h+pad)
    if pg.rotation: r=r*pg.rotation_matrix
    z=px/max(r.width,r.height); pg.get_pixmap(matrix=fitz.Matrix(z,z),clip=r,alpha=False).save(out)
