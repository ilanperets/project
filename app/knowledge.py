"""The brain's checklist: which chapters a project of a given type is expected to contain, learned from complete BOQs of real projects.
After measuring, every expected chapter that was not covered gets an explicit note ("not identified, needs clarification"), never a silent gap."""
import json, os, re
_D=os.path.join(os.path.dirname(os.path.abspath(__file__)),'knowledge')
# key -> (chapter name, sheet types that feed it, regex over BOQ line descriptions that proves coverage)
CH={
 'demo':('עבודות הריסה ופירוק',('demolition',),r'הריס|פירוק|פינוי'),
 'earth':('עבודות עפר',('site','foundation_piles'),r'חפיר|מילוי|עפר'),
 'concrete':('עבודות בטון ושלד',('structure_plan','foundation_piles'),r'בטון|זיון|פלדה|טפסנות|כלונס'),
 'build':('עבודות בנייה וטיח',('floor_plan',),r'בלוק|בניית קיר|טיח|מחיצ|גבס'),
 'seal':('עבודות איטום',('waterproofing',),r'איטום|איטומ'),
 'carp':('נגרות ומסגרות',('door_schedule','frames_schedule'),r'דלת|נגרות|מסגרת|ארון'),
 'alu':('עבודות אלומיניום',('window_schedule',),r'אלומיניום|חלון|ויטרינה'),
 'floor':('ריצוף וחיפוי',('flooring','tile_layout','floor_plan'),r'ריצוף|חיפוי|אריח|פרקט|פנל'),
 'ceil':('תקרות',('ceiling',),r'תקרה|תקרות'),
 'paint':('עבודות צביעה',('floor_plan',),r'צבע|צביעה|סיד'),
 'plumb':('אינסטלציה וכיבוי אש',('plumbing','wetroom_plan','fire'),r'אינסטלצ|צנרת|כיור|ביוב|ספרינקלר|כיבוי|ברז|שוחה|נקודת מים'),
 'elec':('חשמל',('electrical',),r'חשמל|נקודת|תאורה|גוף תאורה|לוח|שקע'),
 'comm':('תקשורת ומתח נמוך',('comm',),r'תקשורת|מתח נמוך|טלפון|מצלמ'),
 'hvac':('מיזוג אוויר ואוורור',('hvac',),r'מיזוג|תעלה|מפזר|מפוח|מזגן|יחידת|אוורור|קירור'),
 'fire':('גילוי אש',('fire',),r'גילוי אש|גלאי|כריזה'),
 'bms':('בקרת מבנה',('bms',),r'בקרה|בקר ה|BMS|DDC'),
 'kitchen':('ציוד מטבח ומערכות מטבח',('layout',),r'מטבח|מקרר|תנור|קולט אדים|שולחן עבודה|נירוסטה|ציוד'),
 'misc':('עבודות ברג׳י, מקבעים ושונות',(),r'ברג|מקבע|שעות עבודה|פועל|הדרכה'),
}
EXPECT={
 'med_reno':['demo','build','seal','carp','alu','floor','ceil','paint','plumb','elec','comm','hvac','fire','bms','kitchen','misc'],
 'med_new':['earth','concrete','build','seal','carp','alu','floor','ceil','paint','plumb','elec','comm','hvac','fire','bms','kitchen','misc'],
 'comm_reno':['demo','build','carp','floor','ceil','paint','plumb','elec','comm','hvac','fire'],
 'villa':['earth','concrete','build','seal','carp','alu','floor','paint','plumb','elec','comm','hvac'],
 'apt_reno':['demo','build','seal','carp','floor','ceil','paint','plumb','elec','hvac'],
 'tower':['earth','concrete','build','seal','carp','alu','floor','ceil','paint','plumb','elec','comm','hvac','fire'],
 'boutique':['earth','concrete','build','seal','carp','alu','floor','ceil','paint','plumb','elec','comm','hvac','fire'],
}
_cat=None
def catalog():
    global _cat
    if _cat is None:
        try: _cat={c['name']:c['items'] for c in json.load(open(os.path.join(_D,'med_kitchen.json')))['chapters']}
        except Exception: _cat={}
    return _cat
def infer_type(sheets):
    ts={s['type'] for s in sheets}
    if ts&{'demolition','ceiling','existing','layout'}: return 'comm_reno'
    return 'villa'
SCOPE={'הריסה ופירוק':'demo','עפר':'earth','שלד ובטון':'concrete','בנייה וטיח':'build','איטום':'seal','נגרות ומסגרות':'carp','אלומיניום':'alu','ריצוף וחיפוי':'floor','תקרות':'ceil','צבע':'paint','אינסטלציה וכיבוי אש':'plumb','חשמל':'elec','תקשורת':'comm','מיזוג אוויר':'hvac','גילוי אש':'fire','בקרת מבנה':'bms','ציוד מטבח':'kitchen'}
def check(lines,sheets,ptype=None,scope=None):
    """-> list of assumption dicts for every expected chapter that the measurement did not cover."""
    ptype=ptype or infer_type(sheets); have={s['type'] for s in sheets}; out=[]
    keys=EXPECT.get(ptype,[])
    if scope: keys=[k for k in keys if k in {SCOPE.get(x) for x in scope} or k=='misc']+[SCOPE[x] for x in scope if SCOPE.get(x) and SCOPE[x] not in keys]      # the user's scope decides which chapters are expected
    for k in keys:
        name,feeds,rx=CH[k]; r=re.compile(rx)
        hits=[l for l in lines if r.search(l.get('desc',''))]
        if any(l.get('q') for l in hits): continue
        fed=[t for t in feeds if t in have]
        if hits: why='יש סעיף בנושא אבל בלי כמות מחושבת'
        elif fed: why='הועלתה תוכנית בתחום אבל לא נמדד ממנה כלום'
        else: why='לא הועלתה תוכנית בתחום ולא זוהה סעיף בנושא'
        ex=[i['d'] for i in catalog().get(CH[k][0],[])[:3]]
        out.append(dict(t=f'{name}: לא זוהה, נדרש לברר אם בהיקף',why=why+(' · לדוגמה בפרויקטים דומים: '+' | '.join(ex) if ex else ''),gives=name,how='העלה תוכנית או רשימה של התחום, או סמן שאינו בהיקף'))
    return out
