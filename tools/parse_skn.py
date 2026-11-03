"""Parse a Banarit .skn BOQ export (cp1255, fixed width: code10 unit2 qty9 price12 text). Returns items [{code,u,q,p,d}] and headings {code:title}."""
import re, sys, json
def parse(path):
    txt=open(path,'rb').read().decode('cp1255',errors='replace')
    heads={}; items=[]; cur=None
    for l in txt.split('\r\n'):
        if not l.strip(): continue
        code=l[:10]
        if re.fullmatch(r'\d{10}',code) and re.match(r'.{2}[\d.]{9}',l[10:21]) and len(l)>33 and re.match(r'-?\d+\.\d\d',l[21:33].strip() or 'x') :
            u=l[10:12].strip(); q=float(l[12:21] or 0); p=float(l[21:33] or 0); t=l[33:].strip()
            cur=dict(code=code,u=u,q=q,p=p,d=t)
            if u=='' and q==0 and p==0 and code.rstrip('0') and not t.startswith('מחיר') and len(t)<70 and not code.endswith('00')==False: pass
            items.append(cur)
        elif cur is not None and l.startswith(' '*20):
            cur['d']+=' '+l.strip()
        elif cur is not None and re.match(r'\d{10} ',l):
            cur['d']+=' '+l[13:].strip()
    return items
if __name__=='__main__':
    it=parse(sys.argv[1]); print(len(it))
    for x in it[:12]: print(x['code'],x['u'],x['q'],x['p'],x['d'][:90])
