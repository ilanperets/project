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
    return out
