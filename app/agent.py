"""In-system quantity-surveyor agent. Uses the Claude API (key from ANTHROPIC_API_KEY or the company settings).
It can read the project (sheets, texts, BOQ, comparison with a reference BOQ), explain how a quantity was derived,
and store reusable lessons ('memory') that are shown to it in every later project of the same company."""
import json, os, re, requests, pymupdf

API='https://api.anthropic.com/v1/messages'
SYSTEM='''אתה סוכן כמויות בכיר בתוך מערכת מדידת כמויות לקבלנים בישראל. אתה עונה בעברית, קצר וענייני.
העיקרון: כל פרויקט שונה, לכן אתה לומד שיטה ולא "תוכנית". לפני שאתה קובע כמות: קרא את הגיליון (טקסט, טבלאות, מקרא), בדוק אם הכמות כתובה, ואם לא - הסבר איך למדוד אותה.
כשמצאת שיטה כללית שחוזרת בין פרויקטים (למשל "טבלת ריצוף בתוכנית אדריכלות נותנת מ\\"ר לפי תיוג FL"), שמור אותה עם הכלי remember.
אל תמציא כמויות. אם לא ידוע - אמור מה חסר. מחירים קובע רק המשתמש.'''
TOOLS=[
 dict(name='list_sheets',description='רשימת הגיליונות בפרויקט עם סוג וזיהוי',input_schema=dict(type='object',properties={})),
 dict(name='read_sheet_text',description='הטקסט שכתוב בגיליון (שורות, טבלאות, מקרא, הערות)',input_schema=dict(type='object',properties=dict(sid=dict(type='string'),limit=dict(type='integer')),required=['sid'])),
 dict(name='get_boq',description='סעיפי כתב הכמויות הנוכחי, אפשר לסנן לפי מילה בתיאור',input_schema=dict(type='object',properties=dict(contains=dict(type='string')))),
 dict(name='get_comparison',description='השוואה לכתב ייחוס שנטען לפרויקט (אם קיים), לפי קטגוריות',input_schema=dict(type='object',properties={})),
 dict(name='remember',description='שמירת לקח או שיטה כללית לשימוש בפרויקטים הבאים',input_schema=dict(type='object',properties=dict(lesson=dict(type='string')),required=['lesson'])),
]
def _txt(path,limit=6000):
    pg=pymupdf.open(path)[0]; out=[]
    for b in pg.get_text('blocks'):
        t=' '.join(re.sub(r'[‎‏‪-‮]','',b[4]).split())
        if t: out.append(t)
    return '\n'.join(out)[:limit]
def run_tool(name,args,ctx):
    pr=ctx['pr']; path=ctx['path']
    if name=='list_sheets': return json.dumps([dict(sid=s['sid'],file=s['file'],type=s['type']) for s in pr['sheets']],ensure_ascii=False)
    if name=='read_sheet_text':
        s=next((x for x in pr['sheets'] if x['sid']==args.get('sid')),None)
        return _txt(path(s),int(args.get('limit') or 6000)) if s else 'גיליון לא נמצא'
    if name=='get_boq':
        k=args.get('contains') or ''
        rows=[dict(code=r['code'],desc=(r.get('full') or r['desc'])[:90],unit=r.get('unit'),q=r.get('q'),st=r.get('st'),src=(r.get('src') or '')[:100]) for r in (pr.get('boq') or []) if r['kind']=='item' and k in r['desc']]
        return json.dumps(rows[:60],ensure_ascii=False)
    if name=='get_comparison': return json.dumps(ctx.get('compare') or 'לא נטען כתב ייחוס',ensure_ascii=False)
    if name=='remember':
        mem=ctx['memory_load'](); mem.append(args['lesson'][:400]); ctx['memory_save'](mem[-60:]); return 'נשמר'
    return 'כלי לא מוכר'
def chat(messages,ctx,key,model=None,max_steps=6):
    model=model or os.environ.get('AGENT_MODEL','claude-sonnet-4-5')
    mem=ctx['memory_load'](); system=SYSTEM+('\n\nלקחים שנלמדו בעבר:\n- '+'\n- '.join(mem) if mem else '')
    msgs=list(messages)
    for _ in range(max_steps):
        r=requests.post(API,headers={'x-api-key':key,'anthropic-version':'2023-06-01','content-type':'application/json'},json=dict(model=model,max_tokens=1500,system=system,tools=TOOLS,messages=msgs),timeout=90)
        if r.status_code!=200: raise RuntimeError(f'שגיאת שירות הסוכן ({r.status_code})')
        d=r.json(); msgs.append(dict(role='assistant',content=d['content']))
        uses=[c for c in d['content'] if c['type']=='tool_use']
        if not uses or d.get('stop_reason')!='tool_use':
            return ''.join(c.get('text','') for c in d['content'] if c['type']=='text'),msgs
        msgs.append(dict(role='user',content=[dict(type='tool_result',tool_use_id=u['id'],content=run_tool(u['name'],u['input'],ctx)) for u in uses]))
    return 'הסוכן הגיע למגבלת הצעדים',msgs
