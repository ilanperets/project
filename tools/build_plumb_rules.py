"""Derives per-patient-room plumbing quantity ratios from a real plumbing BOQ kept in data/training/plumbing (never committed).
Output app/knowledge/plumb_rules.json: only wording, unit and ratio (quantity / number of rooms). No names, prices, codes."""
import json,os,re,sys
ROOT=os.path.join(os.path.dirname(os.path.abspath(__file__)),'..'); sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from parse_skn import parse
import build_bank as BB
PU={'01':"יח'",'02':'מ"א','09':"נק'",'18':"קומפ'"}
SUB={'01':'נקודות וכלים סניטריים','02':'אספקת כלים סניטריים','03':'אספקת מים לצריכה','04':'שופכין, דלוחין וניקוז','05':'ניקוז מי גשם','06':'כיבוי אש (עמדות כ"א)','07':'מאגרים ומשאבות','08':'ספרינקלרים'}
def main():
    d=os.path.join(ROOT,'data','training','plumbing'); f=[x for x in os.listdir(d) if x.endswith('.skn')][0]
    it=[x for x in parse(os.path.join(d,f)) if x['code'].startswith('01') and x['u'].strip() not in('','00') and x['q']>0]
    N=next(x['q'] for x in it if x['code']=='0107010010')    # number of patient rooms = first sanitary point (WC)
    out=[]; base=''
    for x in it:
        t=BB.clean(x['d']); t=re.sub(r'מק"ט\s*[\w\-]+','',t); t=re.sub(r'מ?תוצרת\s*"[^"]{1,40}"( או ש"ע)?',' או ש"ע',t); t=re.sub(r'\s+',' ',t).strip(' ,.;')
        t=re.sub(r'(דגם|מדגם)\s*"[^"]{1,30}"','',t); t=re.sub(r'\s+,',',',t); t=re.sub(r'\s+',' ',t)
        m=re.search(r'כנ"ל\s*,?\s*אך\s*(.*)$',t)
        if m and base: t=re.sub(r'\s*בקוטר.*$','',base)+' '+m.group(1)
        elif len(t)>40: base=t
        sub=x['code'][4:6] if False else x['code'][4:6]
        out.append(dict(sub=SUB.get(x['code'][4:6],''),d=t,u=PU.get(x['u'],''),r=round(x['q']/N,4),room_based=x['code'][4:6] in('01','03','04')))
    json.dump(dict(basis='ratio per patient room, from one hospital inpatient-floors BOQ',rows=out),open(os.path.join(ROOT,'app','knowledge','plumb_rules.json'),'w'),ensure_ascii=False,indent=0)
    print(N,len(out))
if __name__=='__main__': main()
