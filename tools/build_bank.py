"""Builds app/knowledge/boq_bank.json from real BOQs kept in data/training (never committed): chapter -> item descriptions + units only.
No prices, quantities, codes, client / place / person names. Identical descriptions from several BOQs are merged (n = how many BOQs used it)."""
import json, re, os, collections, sys
ROOT=os.path.join(os.path.dirname(os.path.abspath(__file__)),'..')
TR=os.path.join(ROOT,'data','training')
OUT=os.path.join(ROOT,'app','knowledge','boq_bank.json')
CHAP={'01':'עבודות עפר','02':'עבודות בטון','04':'עבודות בנייה','05':'עבודות איטום','06':'נגרות אומן ומסגרות פלדה','07':'מתקני תברואה וכיבוי','08':'מתקני חשמל','09':'עבודות טיח','10':'עבודות ריצוף וחיפוי','11':'עבודות צביעה','12':'עבודות אלומיניום','15':'מתקני מיזוג אוויר','19':'מסגרות חרש','22':'אלמנטים מתועשים בבניין (מחיצות ותקרות)','24':'עבודות הריסה ופירוק','30':'מקבעים','31':'מטבחים','34':'מערכת גילוי אש','35':'מערכת בקרת מבנה','79':"עבודות ברג'י ושונות"}
NAMES=[r'הופק ע["״ ]*י.*$',r'דקל',r'חיפה',r'איחוד דוורים ושליחים',r'דואר ישראל',r'כפר סבא',r'רמת גן',r'בי["״]ח\s*\S*',r'לוינשטיי?ן',r'מאיר גרינברג',r'בנארית',r'ארדן\s*קונטרול\S*(\s*בע["״]מ)?',r'משרד הביטחון',r'Schneider\s*Electric',r'MAESTRO\s*CONTROL',r'www\.\S+',r'\b0\d{1,2}-\d{6,7}\b',r'המרכז הרפואי',r'משרד טכני לבנין']
def clean(t,unit='',pdf=False):
    t=re.sub(r'\s+',' ',t).strip()
    if pdf:      # PDF extraction drops the unit column into the description: remove the first spaced unit artefact, re-join split abbreviations
        t=re.sub(r'\s(מ\s+"\s*ר|מ\s+"\s*ק|מ\s+"\s*א|יח\s+\'|נק\s+\'|קומפ\s+\'|מ\s+\')(?=\s)',' ',t,count=1)
        t=re.sub(r'([א-ת]{1,3})\s+"\s*([א-ת]{1,2})(?![א-ת])',r'\1"\2',t)
        t=re.sub(r'\s+/\s+','/',t)
    for rx in NAMES: t=re.sub(rx,'',t,flags=re.I)
    t=re.sub(r'(?<![א-ת])([א-ת])\s*"\s*([א-ת])(?![א-ת])',r'\1"\2',t)    # abbreviations split by PDF extraction: ס " מ -> ס"מ
    t=re.sub(r'(?<![א-ת])([א-ת])\s*\'(?=\s|$|[,.])',r"\1'",t)
    t=re.sub(r'\)\s*([^()]{1,60}?)\s*\(',r'(\1)',t)             # reversed brackets from RTL extraction
    t=re.sub(r'"(?=[א-ת])',' "',t) if False else t
    u={'מ"ר':r'מ"\s*ר','מ"ק':r'מ"\s*ק','מ"א':r'מ"\s*א',"יח'":r"יח\s*'",'מטר':r"מ\s*'","קומפ'":r"קומפ\s*'"}.get(unit)
    t=re.sub(r'(מחיר\s*(יסוד|ליחידה)?\s*[\d,\.]+\s*ש"?ח\s*(/\s*(מ"ר|מ"א|יח\'|מטר))?|\(?מחיר יסוד[^,;.)]*\)?)','',t)
    t=re.sub(r'\s+',' ',t).strip(' ,.;')
    return t
def ok(t):
    h=len(re.findall(r'[א-ת]',t)); return len(t)>=18 and h/max(1,len(t))>=0.45
def main():
    bank=collections.OrderedDict(); seen={}
    def add(ch,desc,unit,src):
        if not ok(desc): return
        key=re.sub(r'[^א-תa-zA-Z0-9]','',desc)[:90]
        if key in seen: seen[key]['n']+=1; return
        e=dict(d=desc,u=unit or '',n=1); seen[key]=e
        bank.setdefault(ch,[]).append(e)
    # 1) kitchen .skn (clean text, own chapter names)
    sk=os.path.join(TR,'kitchen','boq_parsed.json')
    if os.path.exists(sk):
        d=json.load(open(sk)); U={'01':"יח'",'02':'מטר','03':'מ"ר','04':'מ"ק','05':'טון','06':"נק'",'08':'שעה','09':"קומפ'",'11':'ק"ג'}
        for it in d['items']:
            if not it['u'].strip(): continue
            add(CHAP.get(it['code'][2:4],'שונות'),clean(it['d']),U.get(it['u'],''),'k')
    # 2) other reference BOQs (PDF extraction: noisier, only added if not a duplicate)
    for fn in sorted(os.listdir(os.path.join(TR,'refs'))) if os.path.isdir(os.path.join(TR,'refs')) else []:
        for it in json.load(open(os.path.join(TR,'refs',fn))):
            ch=CHAP.get(it['code'].split('.')[1] if '.' in it['code'] else '', 'שונות')
            add(ch,clean(it['desc'],it.get('unit') or '',True),it.get('unit') or '','r')
    out=dict(chapters=[dict(name=k,items=v) for k,v in bank.items()])
    os.makedirs(os.path.dirname(OUT),exist_ok=True); json.dump(out,open(OUT,'w'),ensure_ascii=False,indent=0)
    print(sum(len(v) for v in bank.values()),'items',len(bank),'chapters')
if __name__=='__main__': main()
