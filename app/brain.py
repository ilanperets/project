"""The brain: assumptions the system makes (and tells you about), explosion of BOQ items into materials,
price memory with fuzzy suggestions, partial-bill maths."""
import math, re

DEFAULT_PARAMS={
 'wall_height':dict(v=2.8,label='גובה קירות (מ\')',why='משמש להמרת מטרים של קיר לשטח בלוקים, טיח וצבע. לא נקרא אוטומטית מהחתכים'),
 'pile_length':dict(v=10.0,label='אורך כלונס ממוצע (מ\')',why='משמש לחישוב נפח בטון וזיון בכלונסאות. הערך האמיתי נמצא בטבלת המפלסים'),
 'waste_block':dict(v=0.05,label='פחת בלוקים',why='פחת ממוצע בביצוע'),
 'waste_tile':dict(v=0.08,label='פחת אריחים',why='פחת חיתוכים ושבר'),
 'waste_concrete':dict(v=0.05,label='פחת בטון',why='פחת שפיכה'),
 'rebar_kg_m3':dict(v=100,label='זיון בבטון (ק"ג למ"ק)',why='הערכה כללית עד שיקראו טבלאות הזיון'),
 'retention':dict(v=0.05,label='עיכבון בחשבון חלקי',why='לפי חוזה'),
 'vat':dict(v=0.18,label='מע"מ',why='שיעור חוקי'),
}
def params(pr): 
    p={k:d['v'] for k,d in DEFAULT_PARAMS.items()}; p.update(pr.get('params') or {}); return p

def _t(desc):
    m=re.search(r'קוטר\s*(\d+)',desc); return int(m.group(1)) if m else None

def recipe(item,P):
    """returns list of (material, unit, qty, used_assumption) for one BOQ item"""
    d,u,q=item['desc'],item['unit'],item['q']
    if not q: return []
    out=[]
    if 'כלונסאות' in d and 'קוטר' in d:
        D=_t(d)/100; vol=math.pi*(D/2)**2*P['pile_length']*q*(1+P['waste_concrete'])
        out+=[('בטון מובא ב-30',"מ\"ק",vol,['pile_length']),('זיון לכלונסאות','ק"ג',vol*P['rebar_kg_m3'],['pile_length','rebar_kg_m3'])]
    elif d.startswith('קירות בעובי'):
        A=q*P['wall_height']
        if 'מעל 23' in d:
            vol=A*0.25*(1+P['waste_concrete']); out+=[('בטון מובא ב-30','מ"ק',vol,['wall_height']),('זיון לקירות','ק"ג',vol*P['rebar_kg_m3'],['wall_height','rebar_kg_m3']),('תבניות קיר','מ"ר',A*2,['wall_height'])]
        else:
            blk='בלוק 10' if 'עד 12' in d else ('בלוק 15' if '12-17' in d else 'בלוק 20')
            out+=[(blk,"יח'",A*12.5*(1+P['waste_block']),['wall_height']),('מלט','ק"ג',A*9,['wall_height']),('חול לבניה','מ"ק',A*0.03,['wall_height'])]
    elif d.startswith('איטום'):
        out+=[('יריעת ביטומן 4 מ"מ',"גליל",q*0.24,[]),('פריימר ביטומני','ליטר',q*0.3,[])]
    elif d.startswith('ריצוף'):
        out+=[('אריחי ריצוף','מ"ר',q*(1+P['waste_tile']),[]),('דבק אריחים','ק"ג',q*5,[]),('רובה','ק"ג',q*0.5,[])]
    elif d.startswith('טיח'):
        out+=[('מלט','ק"ג',q*7,[]),('חול לטיח','מ"ק',q*0.025,[])]
    elif d.startswith('צבע'):
        out+=[('צבע פנים','ליטר',q*0.25,[]),('שפכטל','ק"ג',q*0.4,[])]
    elif d.startswith('פתחים'):
        out+=[('חלונות ודלתות לפי פרט',"יח'",q,[])]
    return out

def explode(rows,P):
    """aggregate materials across all items, keep traceability"""
    agg={}; used=set()
    for r in rows:
        if r['kind']!='item': continue
        for m,u,qty,ass in recipe(r,P):
            a=agg.setdefault((m,u),dict(material=m,unit=u,qty=0,codes=[]))
            a['qty']+=qty; a['codes'].append(r['code']); used.update(ass)
    mats=sorted(agg.values(),key=lambda a:a['material'])
    for a in mats: a['qty']=round(a['qty'],2)
    return mats,sorted(used)

STOP={'של','עם','על','את','לפי','כולל','או','ו','מ','ב','ל','כל','בין','קומה','קומת'}
def toks(s): return {w for w in re.findall(r'[א-תa-zA-Z0-9]+',s) if w not in STOP and len(w)>1}
def suggest(desc,unit,memory):
    """memory: list of {desc,unit,price}. Jaccard>=0.3 same unit"""
    T=toks(desc); best=None
    for m in memory:
        if m['unit'].strip()!=unit.strip(): continue
        M=toks(m['desc']); 
        if not T or not M: continue
        j=len(T&M)/len(T|M)
        if j>=0.3 and (not best or j>best[0]): best=(j,m)
    return dict(price=best[1]['price'],match=round(best[0]*100),from_desc=best[1]['desc']) if best else None

def totals(rows,prices):
    s=0
    for r in rows:
        if r['kind']=='item' and r.get('q') and prices.get(r['code']): s+=r['q']*prices[r['code']]
    return round(s,2)

def bill(rows,prices,cum,prev,P):
    """cum/prev: {code: pct 0..100}. Returns lines + totals"""
    lines=[];this=0;cumv=0
    for r in rows:
        if r['kind']!='item' or not r.get('q'): continue
        pr=prices.get(r['code'],0); full=r['q']*pr; c=cum.get(r['code'],0)/100; p=prev.get(r['code'],0)/100
        lines.append(dict(code=r['code'],desc=r['desc'],unit=r['unit'],q=r['q'],price=pr,cum_pct=c*100,prev_pct=p*100,this=round(full*(c-p),2)))
        this+=full*(c-p); cumv+=full*c
    ret=this*P['retention']; net=this-ret; vat=net*P['vat']
    return dict(lines=lines,this=round(this,2),cum=round(cumv,2),retention=round(ret,2),net=round(net,2),vat=round(vat,2),total=round(net+vat,2))
