"""Project-level quantities that do not come from one drawing: site organisation, fencing, excavation, fill, waste, safety,
low voltage, development. Each is a stated rule applied to measures the other engines already produced, so it is always
marked partial, names its assumption, and says what to check and what to do to make it exact."""
import math

def _ln(ch,sub,desc,unit,q,formula,rows,src,need,P,keys,cover=None):
    return dict(ch=ch,sub=sub,desc=desc,unit=unit,q=round(q,2),st='חלקי',src=src,need=need,cover=cover or [desc],
        trace=dict(formula=formula,rows=rows,checks=[dict(ok=False,t=need)],params={k:P[k] for k in keys if k in P}))

def site_lines(M,P):
    fp=M.get('footprint'); per=M.get('perimeter'); fl=max(1,M.get('floors') or 1); tot=M.get('total_slab') or 0; rooms=M.get('rooms') or 0
    out=[]
    out.append(_ln(0,2,'ארגון אתר, מבנים זמניים ומחסנים',"קומפ'",1,'סכום גלובלי אחד לפרויקט',[dict(el='ארגון אתר',dims='סכום גלובלי',val=1,src='כלל קבוע',note='',locs=[])],'כלל: סעיף קבוע בכל פרויקט','המחיר נקבע לפי גודל האתר ומשך הביצוע. לבדוק: האם יש מקום לארגון בתוך המגרש. לעשות: להגדיר מחיר גלובלי',P,()))
    out.append(_ln(0,2,'חיבורי חשמל ומים זמניים לאתר',"קומפ'",1,'סכום גלובלי אחד לפרויקט',[dict(el='חיבורים זמניים',dims='סכום גלובלי',val=1,src='כלל קבוע',note='',locs=[])],'כלל: סעיף קבוע בכל פרויקט','לבדוק: מרחק נקודות החיבור של חברת החשמל והמים. לעשות: לתאם עם הרשויות ולהגדיר מחיר',P,()))
    out.append(_ln(0,2,'שילוט אתר','יח\'',1,'שלט אתר אחד לפי היתר הבנייה',[dict(el='שלט אתר',dims='1',val=1,src='כלל קבוע',note='',locs=[])],'כלל: שלט אחד','לבדוק: דרישות השילוט בהיתר ובחוזה. לעשות: להתאים את מספר השלטים',P,()))
    if fp:
        m=P.get('fence_margin',5); gp=per+8*m
        out.append(_ln(0,2,'גידור וחסימת אתר, כולל שער','מ"א',gp,'היקף הבניין + 4 צלעות × 2 × מרווח',[dict(el='היקף הבניין',dims=f'{per:.1f}',val=round(per,1),src='היקף קומה',note='',locs=[]),dict(el='תוספת מרווח',dims=f'8 × {m}',val=round(8*m,1),src='פרמטר fence_margin',note='',locs=[])],'חלקי: היקף קומה + מרווח','אין תוכנית מגרש: ההיקף משוער. לבדוק: גבולות המגרש בפועל. לעשות: להעלות תוכנית מגרש או להזין אורך גדר',P,('fence_margin',)))
        d=P.get('excavation_depth',1.2); ex=(fp+2*m*math.sqrt(fp)*0+4*2*math.sqrt(fp)+4)*d
        ex=(math.sqrt(fp)+2)**2*d
        out.append(_ln(1,1,'חפירה כללית ויישור שטח','מ"ק',ex,'(צלע שטח הבניין + 2 מ\') בריבוע × עומק החפירה',[dict(el='שטח חפירה',dims=f'({math.sqrt(fp):.1f} + 2)²',val=round((math.sqrt(fp)+2)**2,1),src='שטח קומה + מרווח עבודה',note='',locs=[]),dict(el='עומק',dims=f'{d}',val=d,src='פרמטר excavation_depth',note='',locs=[])],'חלקי: שטח הקומה × עומק שהונח','אין חתך קרקע: העומק והמפלסים משוערים. לבדוק: מפלס קרקע קיים מול מפלס חפירה. לעשות: להעלות חתך או להזין עומק',P,('excavation_depth',)))
        ft=P.get('fill_thickness',.3); out.append(_ln(1,1,'מילוי מובא, מהודק בשכבות','מ"ק',fp*ft,'שטח קומה תחתונה × עובי מילוי',[dict(el='מילוי מתחת לרצפה',dims=f'{fp:.1f} × {ft}',val=round(fp*ft,1),src='שטח קומה, פרמטר fill_thickness',note='',locs=[])],'חלקי: עובי מילוי שהונח','לבדוק: מפרט הרצפה בחתך. לעשות: להזין עובי אמיתי',P,('fill_thickness',)))
        out.append(_ln(1,1,'פינוי עודפי עפר','מ"ק',max(ex-fp*ft,0),'חפירה פחות מילוי חוזר',[dict(el='עודפי עפר',dims=f'{ex:.1f} − {fp*ft:.1f}',val=round(max(ex-fp*ft,0),1),src='חפירה פחות מילוי',note='',locs=[])],'חלקי: בלי מקדם ניפוח','בעפר יש מקדם ניפוח. לבדוק: האם משתמשים בעפר באתר. לעשות: להזין כמות סופית',P,('excavation_depth','fill_thickness')))
        wp=P.get('waste_m3_m2',.04); out.append(_ln(0,2,'פינוי פסולת בנייה לאתר מורשה','מ"ק',(tot or fp)*wp,'שטח בנוי × נפח פסולת למ"ר',[dict(el='פסולת בנייה',dims=f'{(tot or fp):.0f} × {wp}',val=round((tot or fp)*wp,1),src='פרמטר waste_m3_m2',note='',locs=[])],'חלקי: אומדן לפי מ"ר בנוי','לבדוק: דרישות פינוי ואגרות. לעשות: להתאים לניסיון החברה',P,('waste_m3_m2',)))
        if tot: out.append(_ln(0,2,'ניקוי סופי של הבניין','מ"ר',tot,'סכום שטחי התקרות שנקראו',[dict(el='שטח בנוי',dims=f'{tot:.1f}',val=round(tot,1),src='תקרות שנקראו',note='',locs=[])],'חלקי: לפי תקרות שנקראו','לבדוק: שטחי מרפסות וגגות. לעשות: לאמת מול טבלת שטחים',P,()))
        h=P.get('wall_height',2.8)
        out.append(_ln(97,1,'רשת בטיחות והגנות בהיקף הבניין בעבודה בגובה','מ"ר',per*h*fl,'היקף × גובה קומה × מספר קומות',[dict(el='היקף',dims=f'{per:.1f}',val=round(per,1),src='היקף קומה',note='',locs=[]),dict(el='גובה × קומות',dims=f'{h} × {fl}',val=round(h*fl,1),src='פרמטר wall_height',note='',locs=[])],'חלקי','לבדוק: דרישות רשות הבטיחות בעבודה בגובה. לעשות: לאמת מול תוכנית בטיחות',P,('wall_height',)))
        out.append(_ln(97,1,'מעקות בטיחות זמניים בקצוות תקרות ופתחים','מ"א',per*fl,'היקף × מספר קומות',[dict(el='היקף תקרות',dims=f'{per:.1f} × {fl}',val=round(per*fl,1),src='היקף קומה',note='',locs=[])],'חלקי','לבדוק: פתחי מדרגות ופירים. לעשות: להוסיף אורך פתחים פנימיים',P,()))
        ra=P.get('roof_drain_area',100); nd=max(2,math.ceil(fp/ra)); hh=h*fl
        out.append(_ln(7,5,'ניקוז גג: מרזבים וצנרת יורדת','מ"א',nd*hh,'מספר צינורות (שטח גג ÷ שטח למרזב) × גובה הבניין',[dict(el='צינורות יורדים',dims=f'{nd}',val=nd,src='שטח גג חלקי פרמטר roof_drain_area, לפחות 2',note='',locs=[]),dict(el='גובה',dims=f'{hh:.1f}',val=round(hh,1),src='גובה קומה × קומות',note='',locs=[])],'חלקי: אומדן','אין תוכנית ניקוז. לבדוק: מיקום יציאות הניקוז והשיפועים בגג. לעשות: להעלות תוכנית גג עם ניקוז',P,('roof_drain_area','wall_height')))
        pa=P.get('plot_area') or 0
        if pa>fp:
            out.append(_ln(40,1,'שטח פיתוח חוץ (מגרש בניכוי שטח הבניין)','מ"ר',pa-fp,'שטח מגרש פחות שטח קומה תחתונה',[dict(el='שטח מגרש',dims=f'{pa}',val=pa,src='הוזן',note='',locs=[]),dict(el='שטח בניין',dims=f'{fp:.1f}',val=round(fp,1),src='קומה תחתונה',note='',locs=[])],'חלקי','לבדוק: חלוקה לגינון, ריצוף וחניה. לעשות: להעלות תוכנית פיתוח',P,('plot_area',)))
            out.append(_ln(40,1,'גדר בהיקף המגרש','מ"א',4*math.sqrt(pa),'4 × שורש שטח המגרש (מגרש ריבועי משוער)',[dict(el='היקף מגרש',dims=f'4 × √{pa}',val=round(4*math.sqrt(pa),1),src='שטח המגרש',note='',locs=[])],'חלקי: מגרש ריבועי משוער','לבדוק: צורת המגרש וגבולותיו. לעשות: להעלות תוכנית מגרש',P,('plot_area',)))
    if rooms:
        n=P.get('data_pts_room',1)
        out.append(_ln(18,1,'נקודת תקשורת (מחשב/טלפון), כולל צנרת וכבילה',"נק'",rooms*n,'מספר חללים × נקודות לחדר',[dict(el='חללים שזוהו',dims=f'{rooms} × {n}',val=rooms*n,src='חללים בתוכנית חשמל',note='',locs=[])],'חלקי: כלל לפי חדרים','אין תוכנית מתח נמוך. לבדוק: נקודות בפועל לפי הלקוח. לעשות: להעלות תוכנית תקשורת',P,('data_pts_room',)))
        out.append(_ln(18,1,'נקודת טלוויזיה/כבלים/לוויין',"נק'",min(rooms,max(2,rooms//3)),'שליש מהחללים, לפחות 2',[dict(el='נקודות טלוויזיה',dims=f'{rooms} חללים',val=min(rooms,max(2,rooms//3)),src='כלל',note='',locs=[])],'חלקי: כלל גס','לבדוק: מיקום טלוויזיות בתוכנית. לעשות: להעלות תוכנית מתח נמוך',P,()))
        out.append(_ln(18,1,'ארון תקשורת, כולל לוח הסתעפות',"יח'",1,'ארון אחד לבניין',[dict(el='ארון תקשורת',dims='1',val=1,src='כלל קבוע',note='',locs=[])],'חלקי','לבדוק: דרישות החברה המספקת. לעשות: לאשר מיקום',P,()))
    if P.get('lift_stops'):
        out.append(_ln(17,1,'מעלית, כולל התקנה ובדיקות',"יח'",P['lift_stops'],'לפי פרמטר lift_stops',[dict(el='מעלית',dims=str(P['lift_stops']),val=P['lift_stops'],src='הוזן',note='',locs=[])],'הוזן בפרמטרים','לבדוק: מספר תחנות. לעשות: להעלות מפרט היצרן',P,('lift_stops',)))
    return out
