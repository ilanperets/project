"""Sheet classification from vector content (layers, size, geometry). No file names are used.
Learned rules (data/rules.json) are checked first; every user correction is stored there."""
import collections, hashlib, json, os, pymupdf as fitz

TYPES={
 'foundation_piles':'תוכנית יסודות וכלונסאות','structure_plan':'תוכנית קונסטרוקציה (תקרה, קורות, גג)','structure_other':'קונסטרוקציה: פרטים ומדרגות',
 'floor_plan':'תוכנית קומה','elevation':'חזיתות','section':'חתכים','site':'תוכנית פיתוח','details':'פרטי בנייה','openings_details':'פרטי דלתות וחלונות',
 'waterproofing':'תוכנית איטום','tile_layout':'פריסת אריחים (חדר רחצה)','wetroom_plan':'חדר רחצה: אדריכלות, אינסטלציה וחשמל','electrical':'תוכנית חשמל','plumbing':'תוכנית אינסטלציה','hvac':'תוכנית מיזוג אוויר','unknown':'לא זוהה'}

DISC={'foundation_piles':'construction','structure_plan':'construction','structure_other':'construction','floor_plan':'arch','elevation':'arch','section':'arch','details':'arch','openings_details':'arch','electrical':'elec','plumbing':'plumb','hvac':'hvac','waterproofing':'seal','tile_layout':'arch','wetroom_plan':'plumb','site':'dev','unknown':''}
DISCS=[('construction','קונסטרוקציה'),('arch','אדריכלות'),('elec','חשמל'),('hvac','מיזוג אוויר'),('plumb','אינסטלציה'),('seal','איטום'),('dev','פיתוח')]

def _ink(path,W=220):
    import numpy as np
    pg=fitz.open(path)[0]; z=W/pg.rect.width
    pm=pg.get_pixmap(matrix=fitz.Matrix(z,z),colorspace=fitz.csGRAY,alpha=False)
    return np.frombuffer(pm.samples,np.uint8).reshape(pm.height,pm.width)<200

def _dil(a):
    b=a.copy(); b[1:]|=a[:-1]; b[:-1]|=a[1:]; b[:,1:]|=a[:,:-1]; b[:,:-1]|=a[:,1:]; return b

def ink_similarity(p1,p2):
    """share of overlapping drawn pixels between two sheets (1.0 = identical drawing)"""
    a=_ink(p1); b=_ink(p2); h=min(a.shape[0],b.shape[0]); w=min(a.shape[1],b.shape[1]); a=a[:h,:w]; b=b[:h,:w]
    return float(((a&_dil(b)).sum()+(b&_dil(a)).sum())/max(1,a.sum()+b.sum()))

def revision_of(ft,path,sheets,pdir):
    """an uploaded sheet that looks like a new revision of an existing one: same paper size, same layers, same drawing"""
    best=None
    for e in sheets:
        if abs(e['w_mm']-ft['w_mm'])/max(1,e['w_mm'])>.02 or abs(e['h_mm']-ft['h_mm'])/max(1,e['h_mm'])>.02: continue
        a=set(sig(e['layers'])); b=set(sig(ft['layers']))
        if len(a&b)/max(1,len(a|b))<.8: continue
        ep=os.path.join(pdir,'files',e['sid']+'.pdf')
        if not os.path.exists(ep): continue
        iu=ink_similarity(ep,path)
        if iu>=.8 and (not best or iu>best[1]): best=(e,iu)
    return best

def file_hash(path):
    return hashlib.sha1(open(path,'rb').read()).hexdigest()

def features(path):
    d=fitz.open(path); pg=d[0]; L=collections.Counter(); n=0
    for dr in pg.get_drawings():
        L[dr.get('layer') or '']+=1; n+=1
    mb=pg.mediabox
    try:
        from .wetroom import _elevations,PT_CM
        te=len(_elevations(pg,PT_CM*50))
    except Exception: te=0
    return dict(pages=len(d),w_mm=round(mb.width*25.4/72),h_mm=round(mb.height*25.4/72),layers=dict(L),n_draw=n,chars=len(pg.get_text()),tile_elev=te)

def sig(layers): return sorted(k for k,v in layers.items() if v>=5)

def _learned(layers,rules):
    s=set(sig(layers))
    for r in rules:
        a=set(r['sig']); j=len(s&a)/max(1,len(s|a))
        if j>=0.9: return r['type'],'לפי כלל שנלמד מתיקון קודם'
    return None

def classify(feat,rules=()):
    L=feat['layers']; has=lambda k:L.get(k,0)>0
    got=_learned(L,rules)
    if got: return dict(type=got[0],conf='learned',why=got[1])
    if has('ker') and has('SANO') and has('DOOR') and not has('WL'):
        if feat.get('tile_elev',0)>=3: return dict(type='tile_layout',conf='high',why='חזיתות פנים בשכבת האריחים: פריסת אריחים של חדר רחצה')
        if has('graff-elc') or has('SANIT'): return dict(type='wetroom_plan',conf='med',why='כלים סניטריים ושכבת חשמל בגיליון קטן: תוכנית חדר רחצה')
    if has('ELC') or L.get('elect',0)>=300: return dict(type='electrical',conf='high',why='שכבות חשמל ELC/elect עם מאות אלמנטים')
    if has('fl00d') and not has('WL'): return dict(type='foundation_piles',conf='high',why='שכבות כלונסאות fl00/fl00d ובלי שכבת קירות')
    if (has('fl1zb') or has('0kon')) and (has('WL') or has('fl00d')): return dict(type='structure_plan',conf='med',why='שכבות קונסטרוקציה ו-WL, כנראה תקרה או קורות')
    if (has('fl1zb') or has('0kon')) and feat['w_mm']>=1500: return dict(type='structure_other',conf='low',why='שכבות קונסטרוקציה בגיליון רחב, כנראה פרטים או מדרגות')
    if has('TAVIT') and has('DOOR') and not has('hazit 1'): return dict(type='openings_details',conf='med',why='שכבות TAVIT ו-DOOR: פרטי דלתות וחלונות')
    if has('hazit 1-0.05') and has('kayam'):
        if has('fl2zb'): return dict(type='section',conf='med',why='מסגרות פתחים ואלמנטי בטון, כנראה חתכים')
        if has('A-240'): return dict(type='site',conf='low',why='שכבות קווי בניין ופתחים, כנראה תוכנית פיתוח')
        return dict(type='elevation',conf='med',why='שכבת מסגרות פתחים ושכבת קיים, בלי בטון: חזיתות')
    if has('WL') and has('A-240') and (has('fl00h') or has('hazit 1')): return dict(type='floor_plan',conf='med',why='קירות WL, קווי בניין A-240 ובטון בהטצ׳')
    if has('mabat3') and len([k for k,v in L.items() if v>=50])<=14: return dict(type='details',conf='low',why='מעט שכבות, כנראה פרטים')
    return dict(type='unknown',conf='none',why='אין כלל מתאים')
