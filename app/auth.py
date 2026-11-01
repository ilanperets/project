"""Companies, users, sessions and data isolation.

When auth is enabled (MIDA_AUTH=1 or MIDA_ADMIN_PASSWORD set) every /api call needs a session cookie
and every company works inside its own folder: <data>/orgs/<org_id>/ (projects, prices memory, labels).
When disabled the app behaves as before: one shared data folder, no login.
"""
import os, json, time, hmac, hashlib, secrets, datetime, threading, contextvars, shutil, re
from fastapi import APIRouter, HTTPException, Request, Response

ROOT = os.environ.get('KAMUYOT_DATA', os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data'))
ENABLED = os.environ.get('MIDA_AUTH') == '1' or bool(os.environ.get('MIDA_ADMIN_PASSWORD'))
COOKIE = 'mida'
SESSION_DAYS = 14
TRIAL_DAYS = 14
PLANS = {  # limits are enforced by the server; prices are set by the platform owner, not here
    'basic': dict(name='בסיסי', users=3, projects=20, dwg=False),
    'business': dict(name='עסקי', users=15, projects=None, dwg=True),
    'enterprise': dict(name='ארגוני', users=None, projects=None, dwg=True),
}
_lock = threading.RLock()
CUR = contextvars.ContextVar('mida_cur', default=None)  # {user, org_id, org, support}

ACC = os.path.join(ROOT, 'accounts.json')
SES = os.path.join(ROOT, 'sessions.json')
AUD = os.path.join(ROOT, 'audit.jsonl')


def _now(): return datetime.datetime.now().isoformat(timespec='seconds')
def _today(): return datetime.date.today().isoformat()


def _read(p, d):
    try:
        with open(p, encoding='utf-8') as f: return json.load(f)
    except Exception: return d


def _write(p, v):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f: json.dump(v, f, ensure_ascii=False)
    os.replace(tmp, p)


def _acc(): return _read(ACC, dict(orgs={}, users={}))


def hash_pw(pw, salt=None):
    salt = salt or secrets.token_hex(16)
    h = hashlib.scrypt(pw.encode('utf-8'), salt=bytes.fromhex(salt), n=2 ** 14, r=8, p=1, dklen=32).hex()
    return f's1${salt}${h}'


def check_pw(pw, stored):
    try:
        _, salt, h = stored.split('$')
        return hmac.compare_digest(hash_pw(pw, salt).split('$')[2], h)
    except Exception: return False


def audit(actor, action, org='', detail=''):
    with _lock:
        os.makedirs(ROOT, exist_ok=True)
        with open(AUD, 'a', encoding='utf-8') as f:
            f.write(json.dumps(dict(at=_now(), actor=actor, action=action, org=org, detail=detail), ensure_ascii=False) + '\n')


# ---------- data folder of the current company ----------
class LP(os.PathLike):
    """A path inside the current company's folder, resolved at use time."""
    def __init__(self, *parts): self.parts = parts
    def __fspath__(self): return os.path.join(data_dir(), *self.parts)
    def __str__(self): return self.__fspath__()


def data_dir():
    if not ENABLED:
        os.makedirs(ROOT, exist_ok=True); return ROOT
    c = CUR.get()
    if not c or not c.get('org_id'): raise HTTPException(403, 'לא נבחרה חברה')
    d = os.path.join(ROOT, 'orgs', c['org_id'])
    os.makedirs(d, exist_ok=True); return d


def current(): return CUR.get()


def feature(name):
    if not ENABLED: return True
    c = CUR.get()
    if not c or not c.get('org'): return True
    org = c['org']
    return bool(org.get('features', {}).get(name, PLANS.get(org.get('plan'), {}).get(name, True)))


def limit(name):
    if not ENABLED: return None
    c = CUR.get()
    if not c or not c.get('org'): return None
    return PLANS.get(c['org'].get('plan'), {}).get(name)


# ---------- accounts ----------
def org_state(o):
    """effective status: active / trial / blocked, with a reason"""
    if o.get('status') == 'blocked': return 'blocked', o.get('block_reason') or 'החשבון נעצר'
    t = _today()
    if o.get('status') == 'trial':
        if o.get('trial_until') and o['trial_until'] < t: return 'blocked', 'תקופת הניסיון הסתיימה'
        return 'trial', ''
    if o.get('paid_until') and o['paid_until'] < t: return 'blocked', 'המנוי לא חודש'
    return 'active', ''


def bootstrap():
    if not ENABLED: return
    with _lock:
        a = _acc()
        if any(u.get('role') == 'platform' for u in a['users'].values()): return
        email = (os.environ.get('MIDA_ADMIN_EMAIL') or 'admin@mida.local').lower()
        pw = os.environ.get('MIDA_ADMIN_PASSWORD')
        gen = False
        if not pw: pw = secrets.token_urlsafe(9); gen = True
        uid = secrets.token_hex(4)
        a['users'][uid] = dict(id=uid, email=email, name='מנהל פלטפורמה', pw=hash_pw(pw), org=None, role='platform', active=True, created=_now())
        _write(ACC, a)
        audit('system', 'bootstrap', '', email)
        if gen: print(f'\n*** MIDA: נוצר מנהל פלטפורמה. אימייל: {email}  סיסמה: {pw}  (שמור אותה)\n', flush=True)


_fails = {}
def _throttle(key):
    f = _fails.get(key)
    if f and f[0] >= 5 and time.time() - f[1] < 60: raise HTTPException(429, 'יותר מדי ניסיונות. נסו שוב בעוד דקה')


def _fail(key):
    f = _fails.get(key, [0, 0]); _fails[key] = [f[0] + 1, time.time()]


def new_session(uid):
    with _lock:
        s = _read(SES, {}); now = time.time()
        s = {k: v for k, v in s.items() if v['exp'] > now}
        tok = secrets.token_urlsafe(32)
        s[tok] = dict(uid=uid, exp=now + SESSION_DAYS * 86400, as_org=None)
        _write(SES, s); return tok


def end_session(tok):
    with _lock:
        s = _read(SES, {})
        if tok in s: del s[tok]; _write(SES, s)


def set_support(tok, org_id):
    with _lock:
        s = _read(SES, {})
        if tok in s: s[tok]['as_org'] = org_id; _write(SES, s)


def resolve(tok):
    """cookie token -> context dict, or None"""
    if not tok: return None
    s = _read(SES, {}).get(tok)
    if not s or s['exp'] < time.time(): return None
    a = _acc(); u = a['users'].get(s['uid'])
    if not u or not u.get('active', True): return None
    support = False
    if u['role'] == 'platform':
        oid = s.get('as_org'); support = bool(oid)
    else: oid = u['org']
    org = a['orgs'].get(oid) if oid else None
    st, why = org_state(org) if org else ('active', '')
    return dict(user=u, org_id=oid, org=org, support=support, state=st, why=why, token=tok)


def _pub_user(u): return dict(id=u['id'], email=u['email'], name=u['name'], role=u['role'], org=u.get('org'), active=u.get('active', True), last=u.get('last', ''))


def _count_projects(oid):
    d = os.path.join(ROOT, 'orgs', oid, 'projects')
    try: return len([x for x in os.listdir(d) if os.path.exists(os.path.join(d, x, 'project.json'))])
    except Exception: return 0


def _du(path):
    t = 0
    for r, _, fs in os.walk(path):
        for f in fs:
            try: t += os.path.getsize(os.path.join(r, f))
            except Exception: pass
    return t


def pub_org(o, a=None, deep=False):
    a = a or _acc()
    st, why = org_state(o)
    users = [u for u in a['users'].values() if u.get('org') == o['id']]
    r = dict(id=o['id'], name=o['name'], plan=o.get('plan'), plan_name=PLANS.get(o.get('plan'), {}).get('name', ''), status=st, why=why, raw_status=o.get('status'),
             users=len(users), projects=_count_projects(o['id']), paid_until=o.get('paid_until', ''), trial_until=o.get('trial_until', ''), created=o.get('created', ''),
             last=max([u.get('last', '') for u in users] or ['']), features=o.get('features', {}))
    if deep: r['bytes'] = _du(os.path.join(ROOT, 'orgs', o['id']))
    return r


router = APIRouter()


def need_user():
    c = CUR.get()
    if not c: raise HTTPException(401, 'נדרשת התחברות')
    return c


def need_platform():
    c = need_user()
    if c['user']['role'] != 'platform': raise HTTPException(403, 'אין הרשאה')
    return c


def need_org_admin():
    c = need_user()
    if c['user']['role'] not in ('platform', 'admin'): raise HTTPException(403, 'אין הרשאה')
    if not c.get('org_id'): raise HTTPException(403, 'לא נבחרה חברה')
    return c


EMAIL = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')


def _me(c):
    u = c['user']; o = c.get('org')
    return dict(enabled=True, user=_pub_user(u), org=(dict(id=o['id'], name=o['name'], plan=o.get('plan'), plan_name=PLANS.get(o.get('plan'), {}).get('name', ''), status=c['state'], why=c['why'], trial_until=o.get('trial_until', ''), paid_until=o.get('paid_until', ''),
                dwg=bool(o.get('features', {}).get('dwg', PLANS.get(o.get('plan'), {}).get('dwg', True)))) if o else None), support=c['support'])


@router.get('/api/auth/me')
def me():
    if not ENABLED: return dict(enabled=False, user=dict(name='אילן פרץ', role='platform', email=''), org=None, support=False)
    return _me(need_user())


@router.post('/api/auth/login')
def login(body: dict, request: Request, response: Response):
    if not ENABLED: raise HTTPException(400, 'כניסה לא מופעלת')
    email = (body.get('email') or '').strip().lower(); pw = body.get('password') or ''
    key = email + '|' + (request.client.host if request.client else '')
    _throttle(key)
    with _lock:
        a = _acc(); u = next((x for x in a['users'].values() if x['email'].lower() == email), None)
        ok = bool(u) and u.get('active', True) and check_pw(pw, u['pw'])
        if not ok:
            _fail(key); audit(email or '?', 'login_failed'); raise HTTPException(401, 'אימייל או סיסמה שגויים')
        u['last'] = _now(); _write(ACC, a)
    _fails.pop(key, None)
    tok = new_session(u['id'])
    secure = request.headers.get('x-forwarded-proto', request.url.scheme) == 'https'
    response.set_cookie(COOKIE, tok, max_age=SESSION_DAYS * 86400, httponly=True, samesite='lax', secure=secure, path='/')
    audit(u['email'], 'login', u.get('org') or '')
    return _me(resolve(tok))


@router.post('/api/auth/logout')
def logout(request: Request, response: Response):
    tok = request.cookies.get(COOKIE)
    if tok: end_session(tok)
    response.delete_cookie(COOKIE, path='/'); return dict(ok=True)


@router.post('/api/auth/password')
def change_password(body: dict):
    c = need_user(); u = c['user']
    new = body.get('new') or ''
    if len(new) < 8: raise HTTPException(400, 'הסיסמה צריכה להכיל לפחות 8 תווים')
    with _lock:
        a = _acc(); uu = a['users'][u['id']]
        if not check_pw(body.get('old') or '', uu['pw']): raise HTTPException(400, 'הסיסמה הנוכחית שגויה')
        uu['pw'] = hash_pw(new); _write(ACC, a)
    audit(u['email'], 'password_changed', u.get('org') or ''); return dict(ok=True)


# ---------- company users (company admin) ----------
@router.get('/api/org/users')
def org_users():
    c = need_org_admin(); a = _acc()
    lim = limit('users')
    return dict(users=[_pub_user(u) for u in a['users'].values() if u.get('org') == c['org_id']], limit=lim)


@router.post('/api/org/users')
def org_add_user(body: dict):
    c = need_org_admin(); oid = c['org_id']
    email = (body.get('email') or '').strip().lower(); pw = body.get('password') or ''
    role = body.get('role') if body.get('role') in ('admin', 'member') else 'member'
    if not EMAIL.match(email): raise HTTPException(400, 'אימייל לא תקין')
    if len(pw) < 8: raise HTTPException(400, 'הסיסמה צריכה להכיל לפחות 8 תווים')
    with _lock:
        a = _acc()
        if any(x['email'].lower() == email for x in a['users'].values()): raise HTTPException(400, 'האימייל כבר קיים במערכת')
        lim = limit('users')
        if lim is not None and len([u for u in a['users'].values() if u.get('org') == oid and u.get('active', True)]) >= lim:
            raise HTTPException(403, f'המסלול כולל עד {lim} משתמשים. פנו אלינו לשדרוג')
        uid = secrets.token_hex(4)
        a['users'][uid] = dict(id=uid, email=email, name=(body.get('name') or email.split('@')[0])[:60], pw=hash_pw(pw), org=oid, role=role, active=True, created=_now())
        _write(ACC, a)
    audit(c['user']['email'], 'user_added', oid, email); return dict(ok=True, id=uid)


@router.post('/api/org/users/{uid}')
def org_user_set(uid: str, body: dict):
    c = need_org_admin()
    with _lock:
        a = _acc(); u = a['users'].get(uid)
        if not u or u.get('org') != c['org_id']: raise HTTPException(404, 'משתמש לא נמצא')
        if uid == c['user']['id'] and body.get('active') is False: raise HTTPException(400, 'אי אפשר לעצור את עצמך')
        if 'active' in body: u['active'] = bool(body['active'])
        if body.get('role') in ('admin', 'member'): u['role'] = body['role']
        if body.get('password'):
            if len(body['password']) < 8: raise HTTPException(400, 'הסיסמה צריכה להכיל לפחות 8 תווים')
            u['pw'] = hash_pw(body['password'])
        _write(ACC, a)
    audit(c['user']['email'], 'user_changed', c['org_id'], u['email']); return dict(ok=True)


# ---------- platform admin ----------
@router.get('/api/admin/overview')
def adm_overview():
    need_platform(); a = _acc()
    orgs = [pub_org(o, a, deep=True) for o in a['orgs'].values()]
    return dict(orgs=sorted(orgs, key=lambda o: o['name']),
                kpi=dict(active=len([o for o in orgs if o['status'] in ('active', 'trial')]), users=sum(o['users'] for o in orgs), projects=sum(o['projects'] for o in orgs),
                         blocked=len([o for o in orgs if o['status'] == 'blocked']), trial=len([o for o in orgs if o['status'] == 'trial'])),
                plans={k: v['name'] for k, v in PLANS.items()})


@router.post('/api/admin/orgs')
def adm_create_org(body: dict):
    c = need_platform()
    name = (body.get('name') or '').strip()[:80]
    email = (body.get('admin_email') or '').strip().lower(); pw = body.get('password') or ''
    plan = body.get('plan') if body.get('plan') in PLANS else 'business'
    if not name: raise HTTPException(400, 'חסר שם חברה')
    if not EMAIL.match(email): raise HTTPException(400, 'אימייל מנהל לא תקין')
    if len(pw) < 8: raise HTTPException(400, 'הסיסמה צריכה להכיל לפחות 8 תווים')
    with _lock:
        a = _acc()
        if any(x['email'].lower() == email for x in a['users'].values()): raise HTTPException(400, 'האימייל כבר קיים במערכת')
        oid = secrets.token_hex(4)
        trial = bool(body.get('trial', True))
        a['orgs'][oid] = dict(id=oid, name=name, plan=plan, status='trial' if trial else 'active', created=_now(),
                              trial_until=(datetime.date.today() + datetime.timedelta(days=TRIAL_DAYS)).isoformat() if trial else '', paid_until=(body.get('paid_until') or '')[:10], features={})
        uid = secrets.token_hex(4)
        a['users'][uid] = dict(id=uid, email=email, name=(body.get('admin_name') or 'מנהל')[:60], pw=hash_pw(pw), org=oid, role='admin', active=True, created=_now())
        _write(ACC, a)
    os.makedirs(os.path.join(ROOT, 'orgs', oid, 'projects'), exist_ok=True)
    audit(c['user']['email'], 'org_created', oid, name); return dict(ok=True, id=oid)


@router.post('/api/admin/orgs/{oid}')
def adm_org_set(oid: str, body: dict):
    c = need_platform()
    with _lock:
        a = _acc(); o = a['orgs'].get(oid)
        if not o: raise HTTPException(404, 'חברה לא נמצאה')
        ch = []
        if 'status' in body:
            if body['status'] not in ('active', 'trial', 'blocked'): raise HTTPException(400, 'סטטוס לא מוכר')
            o['status'] = body['status']; o['block_reason'] = (body.get('reason') or '')[:80]; ch.append('status=' + body['status'])
            if body['status'] == 'trial' and not o.get('trial_until'): o['trial_until'] = (datetime.date.today() + datetime.timedelta(days=TRIAL_DAYS)).isoformat()
        if 'plan' in body:
            if body['plan'] not in PLANS: raise HTTPException(400, 'מסלול לא מוכר')
            o['plan'] = body['plan']; ch.append('plan=' + body['plan'])
        for k in ('paid_until', 'trial_until'):
            if k in body: o[k] = (body[k] or '')[:10]; ch.append(f'{k}={o[k]}')
        if isinstance(body.get('features'), dict):
            o['features'] = {k: bool(v) for k, v in body['features'].items() if k in ('dwg',)}; ch.append('features')
        _write(ACC, a)
    audit(c['user']['email'], 'org_changed', oid, ', '.join(ch)); return dict(ok=True)


@router.get('/api/admin/orgs/{oid}/users')
def adm_org_users(oid: str):
    need_platform(); a = _acc()
    if oid not in a['orgs']: raise HTTPException(404, 'חברה לא נמצאה')
    return [_pub_user(u) for u in a['users'].values() if u.get('org') == oid]


@router.post('/api/admin/support/{oid}')
def adm_support(oid: str, request: Request):
    c = need_platform()
    if oid not in _acc()['orgs']: raise HTTPException(404, 'חברה לא נמצאה')
    set_support(request.cookies.get(COOKIE), oid); audit(c['user']['email'], 'support_enter', oid); return dict(ok=True)


@router.post('/api/admin/support_exit')
def adm_support_exit(request: Request):
    c = need_platform()
    set_support(request.cookies.get(COOKIE), None); audit(c['user']['email'], 'support_exit', c.get('org_id') or ''); return dict(ok=True)


@router.get('/api/admin/audit')
def adm_audit(n: int = 100):
    need_platform()
    try:
        with open(AUD, encoding='utf-8') as f: L = f.readlines()[-min(n, 500):]
    except Exception: L = []
    out = []
    for l in reversed(L):
        try: out.append(json.loads(l))
        except Exception: pass
    names = {o['id']: o['name'] for o in _acc()['orgs'].values()}
    for r in out: r['org_name'] = names.get(r.get('org'), '')
    return out
