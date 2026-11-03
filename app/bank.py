"""BOQ bank: real-BOQ item wording by chapter (no prices, quantities or names). For every measured line, the closest bank item supplies the
full professional description; when nothing is close enough the system keeps its own wording."""
import json, os, re
_P=os.path.join(os.path.dirname(os.path.abspath(__file__)),'knowledge','boq_bank.json')
_B=None
STOP=set('של עם או על אל כל לרבות כולל כולל כנדרש בכל לפי ללא וכן את הוא היא הכל גם כמו אך עד מן'.split())
def _t(s):
    out=set()
    for w in re.findall(r'[א-תa-zA-Z0-9]+',s):
        w=re.sub(r'^[ובהלמש]{1,2}(?=[א-ת]{3,})','',w) if re.match(r'[א-ת]',w) else w.lower()
        if re.match(r'[א-ת]',w) and len(w)>4: w=re.sub(r'(ות|ים|ית|ה|ת)$','',w)
        if len(w)>=3 and w not in STOP: out.add(w)
    return out
SPECIFIC=re.compile(r'המטבח|חדר האוכל|ברשימת הגמר|כדוגמת הקיים|הקיים במסדרון|בהתאם לרשימה|לפי רשימה|טיפוס מס|ראה פרט|פרט מס|גיליון|תוכנית מס|בשלב הזמני|בשלב הקבוע|המזמין|הנחיות קונס')
REPAIR=re.compile(r'^(תיקונ|השלמ|פירוק|הריס|תוספת|כנ"ל)')
def _load():
    global _B
    if _B is None:
        try:
            d=json.load(open(_P)); _B=[]
            for c in d['chapters']:
                for i in c['items']:
                    if SPECIFIC.search(i['d']): continue
                    ft=re.findall(r'[א-תa-zA-Z0-9]+',i['d']); i['_h']=next(iter(_t(ft[0])),None) if ft else None
                    _B.append((_t(i['d'][:160]),i,c['name']))
        except Exception: _B=[]
    return _B
def text_for(desc,unit='',min_score=0.5):
    """-> full wording from the bank, or ''"""
    T=_t(desc)
    if len(T)<2: return ''
    first=re.findall(r'[א-תa-zA-Z0-9]+',desc)
    head=next(iter(_t(first[0])),None) if first else None
    rep=bool(REPAIR.match(desc.strip()))
    best=None
    for tk,i,ch in _load():
        if not tk or (head and head!=i['_h']): continue
        if not rep and REPAIR.match(i['d']): continue
        base=len(T&tk)/len(T)
        if base<min_score or len(T&tk)<2: continue
        sc=base+(0.1 if i['u'] and unit and i['u']==unit else 0)+min(i.get('n',1),3)*0.01
        if best is None or sc>best[0]: best=(sc,i)
    return best[1]['d'] if best else ''
