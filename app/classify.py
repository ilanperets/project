"""Sheet classification from vector content (layers, size, geometry). No file names are used.
Learned rules (data/rules.json) are checked first; every user correction is stored there."""
import collections, hashlib, json, os, pymupdf as fitz

TYPES={
 'foundation_piles':'תוכנית יסודות וכלונסאות','structure_plan':'תוכנית קונסטרוקציה (תקרה, קורות, גג)','structure_other':'קונסטרוקציה: פרטים ומדרגות',
 'floor_plan':'תוכנית קומה','elevation':'חזיתות','section':'חתכים','site':'תוכנית פיתוח','details':'פרטי בנייה','openings_details':'פרטי דלתות וחלונות',
 'electrical':'תוכנית חשמל','plumbing':'תוכנית אינסטלציה','unknown':'לא זוהה'}

def file_hash(path):
    return hashlib.sha1(open(path,'rb').read()).hexdigest()

def features(path):
    d=fitz.open(path); pg=d[0]; L=collections.Counter(); n=0
    for dr in pg.get_drawings():
        L[dr.get('layer') or '']+=1; n+=1
    mb=pg.mediabox
    return dict(pages=len(d),w_mm=round(mb.width*25.4/72),h_mm=round(mb.height*25.4/72),layers=dict(L),n_draw=n,chars=len(pg.get_text()))

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
