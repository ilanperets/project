"""Reads a priced reference BOQ PDF (code, description, unit, quantity, price, total per row) so the engine can be tested against it."""
import pymupdf,re,json,sys
c=lambda t:re.sub(r'[‎‏‪-‮]','',t)
def ref_items(path):
    d=pymupdf.open(path); out=[]; cur=None; chap=''; sub=''
    for pn,pg in enumerate(d):
        rows={}
        for w in pg.get_text('words'): rows.setdefault(round(w[1]/3),[]).append((w[0],c(w[4])))
        for y in sorted(rows):
            r=sorted(rows[y],reverse=True)   # right-to-left reading
            toks=[t for x,t in r]
            line=' '.join(toks)
            m4=[t for t in toks if re.fullmatch(r'\d\d\.\d\d\.\d{3}\.\d{4}',t)]
            nums=[t for t in toks if re.fullmatch(r'[\d,]+\.\d\d',t)]
            if m4 and len(nums)>=3:
                u=[t for t in toks if t in('מ"ר','מ"א','מ"ק','יח\'','קומפ','טון','ק"ג','יח')]
                # desc tokens: between code(first) and unit; rtl order -> tokens after code up to the unit
                i=toks.index(m4[0]); rest=toks[i+1:]
                desc=[]
                for t in rest:
                    if t in('יח\'','קומפ','מ','"','ר','א','ק','ח','יחי') and False: break
                    desc.append(t)
                qty,price,tot=[float(x.replace(',','')) for x in nums[:3]]
                cur=dict(code=m4[0],q=qty,price=price,total=tot,desc=' '.join(toks[i+1:toks.index(nums[0])]) if nums[0] in toks[i+1:] else ' '.join(toks[i+1:]),chap=chap,page=pn+1,unit=None)
                # unit: token set between qty and desc in rtl order: tokens after code are unit then desc
                out.append(cur)
            elif cur and not nums and not re.match(r'^(עמוד|\d\d\.\d)',line) and 'כ"' not in line and len(toks)>1 and not any(re.fullmatch(r'\d\d(\.\d+){1,2}',t) for t in toks):
                cur['desc']+=' '+line
            elif nums and 'סה' in line: cur=None
            elif re.search(r'^\d\d(\.\d+)?$',toks[-1] if toks else ''): pass
    return out

UNITS=[('מ " ר','מ"ר'),('מ " ק','מ"ק'),("יח '","יח'"),('קומפ',"קומפ'"),("מ '",'מ"א'),('טון','טון'),('מ " א','מ"א')]
def unit_of(desc):
    import re
    m=re.search('|'.join(re.escape(a) for a,_ in UNITS),desc)
    return dict(UNITS).get(m.group(0)) if m else None
def parse(path):
    items=ref_items(path)
    for x in items: x['unit']=unit_of(x['desc'])
    return items
