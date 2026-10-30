"""Derived quantities: what follows from measured ones plus stated assumptions (always marked 'חלקי' with the assumption named)."""
import math

def derive(lines,slab_areas,P):
    out=[]
    # --- concrete in walls thicker than 23 cm (assumed 25 cm) and pile concrete
    wall_conc_m3=0;wall_form_m2=0
    for l in lines:
        if l['ch']==4 and l['desc'].startswith('קירות בעובי מעל 23') and l['unit']=='מטר':
            A=l['q']*P['wall_height']; wall_conc_m3+=A*0.25; wall_form_m2+=A*2
    pile_m3=0;pile_len=0
    import re
    for l in lines:
        if l['ch']==23 and 'קוטר' in l['desc'] and l['unit']=="יח'":
            d=int(re.search(r'קוטר\s*(\d+)',l['desc']).group(1))/100; pile_m3+=math.pi*(d/2)**2*P['pile_length']*l['q']; pile_len+=l['q']*P['pile_length']
    slab_m2=sum(slab_areas); slab_m3=slab_m2*P['slab_thickness']
    if pile_len: out.append(dict(ch=23,sub=1,desc='כלונסאות: אורך כולל',unit='מטר',q=round(pile_len,1),st='חלקי',src='מספר כלונסאות × אורך ממוצע שהונח',need='אורך אמיתי לכל כלונס מטבלת המפלסים',cover=['כלונסאות קדוחים ויצוקים באתר']))
    if wall_conc_m3: out.append(dict(ch=2,sub=1,desc='בטון מזוין בקירות',unit='מ"ק',q=round(wall_conc_m3,1),st='חלקי',src='אורך קירות בעובי מעל 23 ס"מ × גובה × 25 ס"מ',need='עובי וגובה מדויקים מהחתכים'))
    if slab_m3: out.append(dict(ch=2,sub=1,desc='בטון מזוין בתקרות ובלטות',unit='מ"ק',q=round(slab_m3,1),st='חלקי',src=f'שטח תקרות {slab_m2:.0f} מ"ר × עובי {P["slab_thickness"]*100:.0f} ס"מ שהונח',need='עובי התקרה מתוכנית הקונסטרוקציה'))
    if pile_m3: out.append(dict(ch=2,sub=1,desc='בטון מזוין ביסודות, קורות ועמודים',unit='מ"ק',q=round(pile_m3*(1+P['waste_concrete']),1),st='חלקי',src='נפח כלונסאות לפי אורך ממוצע שהונח',need='אורך כלונסאות, וקורות יסוד מתוכנית היסודות'))
    form=wall_form_m2+slab_m2
    if form: out.append(dict(ch=2,sub=2,desc='תבניות לבטון',unit='מ"ר',q=round(form,1),st='חלקי',src='שני צדי קירות בטון + תחתית תקרות',need='פירוט תבניות לפי גמר'))
    vol=wall_conc_m3+slab_m3+pile_m3
    if vol: out.append(dict(ch=2,sub=2,desc='זיון: מוטות פלדה ורשתות',unit='טון',q=round(vol*P['rebar_kg_m3']/1000,2),st='חלקי',src=f'נפח בטון כולל × {P["rebar_kg_m3"]:.0f} ק"ג למ"ק',need='טבלאות הזיון בתוכניות הקונסטרוקציה (OCR)'))
    # --- plaster / paint from wall length
    wall_m=sum(l['q'] for l in lines if l['ch']==4 and l['unit']=='מטר'); op_m2=sum(l['q'] for l in lines if l['ch']==6 and l['unit']=='מ"ר')
    if wall_m:
        A=max(wall_m*P['wall_height']*2-op_m2,0)
        out.append(dict(ch=9,sub=1,desc='טיח פנים',unit='מ"ר',q=round(A,1),st='חלקי',src='אורך קירות × גובה × 2 צדדים פחות פתחים',need='היקף חדרים מדויק; חלק מהקירות חיצוניים'))
        out.append(dict(ch=11,sub=1,desc='צבע פנים בקירות ובתקרות',unit='מ"ר',q=round(A+slab_m2,1),st='חלקי',src='שטח הטיח + תקרות',need='כמו בטיח'))
    for o in out:
        if not o.get('trace'):
            o['trace']=dict(formula=o['src'],rows=[dict(el=o['desc'],dims='לפי הנוסחה',val=o['q'],src=o['src'],note='כמות נגזרת מכמויות שנמדדו בסעיפים אחרים ומהנחות',locs=[])],
                checks=[dict(ok=False,t='כמות נגזרת, לא נמדדה ישירות: '+o.get('need','')[:120])],params={k:P[k] for k in ('wall_height','slab_thickness','rebar_kg_m3','pile_length','waste_concrete') if k in P})
    return out


def exterior(floors,openings_m2,P):
    """exterior plaster and paint: footprint perimeter x floor height x number of floors, less the openings read from the elevations.
    floors: list of (floor key, perimeter m, area m2). A perimeter is trusted only if perimeter^2/area <= 40 and area >= 20 m2;
    an untrusted floor borrows the roof outline and the trace says so. An estimate: parapets, setbacks and balconies are ignored."""
    ok=lambda p,a: a>=20 and p*p/a<=40
    roof=next(((p,a) for f,p,a in floors if f=='roof' and ok(p,a)),None)
    levels=[(f,p,a) for f,p,a in floors if f!='roof']
    if not levels or not roof and not any(ok(p,a) for _,p,a in levels): return []
    h=P['wall_height']; rows=[]; gross=0; borrowed=0
    names={'ground':'קומת קרקע','first':'קומה א׳','second':'קומה ב׳'}
    for f,p,a in levels:
        if ok(p,a): use=p; note=''
        elif roof: use=roof[0]; note='הקו החיצוני של הקומה לא נסגר. נלקח היקף הגג'; borrowed+=1
        else: continue
        gross+=use*h; rows.append(dict(el=f'היקף {names.get(f,f)}',dims=f'{use:.1f} × {h:.2f}',val=round(use*h,1),src='קו חיצוני של תוכנית הקומה',note=note))
    if not rows: return []
    net=max(gross-openings_m2,0)
    rows.append(dict(el='פתחים לפי חזיתות',dims='',val=-round(openings_m2,1),src='שכבת הפתחים בחזיתות',note='ייתכן שחזיתות נוספות לא נקראו'))
    chk=[dict(ok=False,t='אומדן: אין התחשבות במעקות גג, נסיגות ומרפסות'),dict(ok=True,t=f'גובה קומה {h:.2f} מ\' הוא פרמטר של הפרויקט (לא נקרא מחתכים)')]
    if borrowed: chk.append(dict(ok=False,t=f'{borrowed} קומות נמדדו לפי היקף הגג כי הקו החיצוני שלהן לא נסגר'))
    tr=dict(formula='סכום (היקף קומה × גובה קומה) פחות שטח הפתחים',rows=rows,checks=chk,params=dict(wall_height=h))
    need='אומדן לפי היקף וגובה קומה. נדרשת חזית לדיוק'
    return [dict(ch=9,sub=1,desc='טיח חוץ',unit='מ"ר',q=round(net,1),st='חלקי',src='היקף תוכנית קומה × גובה × קומות',need=need,trace=tr),
            dict(ch=11,sub=1,desc='צבע חוץ',unit='מ"ר',q=round(net,1),st='חלקי',src='כמו הטיח החיצוני',need=need,trace=tr)]
