import os,sys,tempfile,shutil
d=tempfile.mkdtemp(); os.environ['KAMUYOT_DATA']=d; os.environ['MIDA_ADMIN_EMAIL']='root@x.com'; os.environ['MIDA_ADMIN_PASSWORD']='RootPass123'
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fastapi.testclient import TestClient
from app.server import app
ok=0;bad=0
def chk(n,c):
    global ok,bad
    if c: ok+=1
    else: bad+=1; print('FAIL',n)
with TestClient(app) as root:
    chk('unauth projects 401',root.get('/api/projects').status_code==401)
    chk('unauth admin 401',root.get('/api/admin/overview').status_code==401)
    chk('health open',root.get('/api/health').status_code==200)
    chk('bad login',root.post('/api/auth/login',json=dict(email='root@x.com',password='nope')).status_code==401)
    r=root.post('/api/auth/login',json=dict(email='root@x.com',password='RootPass123')); chk('root login',r.status_code==200 and r.json()['user']['role']=='platform')
    chk('platform w/o support 403',root.get('/api/projects').status_code==403)
    a=root.post('/api/admin/orgs',json=dict(name='חברה א',admin_email='a@a.com',password='PassA12345',plan='business',trial=False)).json()
    b=root.post('/api/admin/orgs',json=dict(name='חברה ב',admin_email='b@b.com',password='PassB12345',plan='basic')).json()
    chk('orgs created',a.get('ok') and b.get('ok'))
    chk('dup email',root.post('/api/admin/orgs',json=dict(name='x',admin_email='a@a.com',password='PassA12345')).status_code==400)
    chk('short pw',root.post('/api/admin/orgs',json=dict(name='x',admin_email='z@z.com',password='123')).status_code==400)
    A=TestClient(app); B=TestClient(app)
    chk('A login',A.post('/api/auth/login',json=dict(email='a@a.com',password='PassA12345')).status_code==200)
    chk('B login',B.post('/api/auth/login',json=dict(email='b@b.com',password='PassB12345')).status_code==200)
    pa=A.post('/api/projects',json=dict(name='פרויקט של א')).json(); pid=pa['id']
    chk('A sees own',[p['id'] for p in A.get('/api/projects').json()]==[pid])
    chk('B sees none',B.get('/api/projects').json()==[])
    chk('B cannot get A project',B.get('/api/projects/'+pid).status_code==404)
    chk('B cannot delete A project',B.delete('/api/projects/'+pid).status_code in (200,404) and A.get('/api/projects/'+pid).status_code==200)
    chk('B cannot export A',B.get(f'/api/projects/{pid}/export.xlsx').status_code in (404,400,500))
    chk('B cannot post meta A',B.post(f'/api/projects/{pid}/meta',json=dict(name='hack')).status_code==404)
    chk('traversal',B.get('/api/projects/..%2f..%2faccounts.json').status_code in (404,422))
    chk('A cannot admin',A.get('/api/admin/overview').status_code==403)
    chk('A cannot create org',A.post('/api/admin/orgs',json=dict(name='x',admin_email='q@q.com',password='12345678')).status_code==403)
    # company users
    chk('A add member',A.post('/api/org/users',json=dict(email='m@a.com',password='MemberPass1',name='מודד')).status_code==200)
    M=TestClient(app); chk('member login',M.post('/api/auth/login',json=dict(email='m@a.com',password='MemberPass1')).status_code==200)
    chk('member sees A projects',len(M.get('/api/projects').json())==1)
    chk('member cannot manage users',M.get('/api/org/users').status_code==403)
    # plan limits (B is basic: 3 users, no dwg)
    chk('B add u2',B.post('/api/org/users',json=dict(email='b2@b.com',password='Password12')).status_code==200)
    chk('B add u3',B.post('/api/org/users',json=dict(email='b3@b.com',password='Password12')).status_code==200)
    chk('B add u4 blocked',B.post('/api/org/users',json=dict(email='b4@b.com',password='Password12')).status_code==403)
    pb=B.post('/api/projects',json=dict(name='ב')).json()
    r=B.post(f'/api/projects/{pb["id"]}/upload',files=[('files',('x.dwg',b'abc','application/octet-stream'))]).json()
    chk('B dwg refused',r['added'][0].get('error','').startswith('קריאת DWG'))
    # support
    chk('support enter',root.post('/api/admin/support/'+a['id']).status_code==200)
    chk('support sees A',[p['id'] for p in root.get('/api/projects').json()]==[pid])
    me=root.get('/api/auth/me').json(); chk('support flag',me['support'] and me['org']['name']=='חברה א')
    chk('support exit',root.post('/api/admin/support_exit').status_code==200 and root.get('/api/projects').status_code==403)
    # block
    chk('block A',root.post('/api/admin/orgs/'+a['id'],json=dict(status='blocked',reason='חוב')).status_code==200)
    r=A.get('/api/projects'); chk('A blocked 403',r.status_code==403 and r.json().get('blocked'))
    chk('A me shows blocked',A.get('/api/auth/me').json()['org']['status']=='blocked')
    chk('unblock',root.post('/api/admin/orgs/'+a['id'],json=dict(status='active')).status_code==200 and A.get('/api/projects').status_code==200)
    # trial expiry
    chk('trial expired',root.post('/api/admin/orgs/'+b['id'],json=dict(trial_until='2020-01-01')).status_code==200 and B.get('/api/projects').status_code==403)
    # deactivate user
    uid=[u for u in A.get('/api/org/users').json()['users'] if u['email']=='m@a.com'][0]['id']
    A.post('/api/org/users/'+uid,json=dict(active=False)); chk('deactivated user kicked',M.get('/api/projects').status_code==401)
    # logout
    chk('logout',A.post('/api/auth/logout').status_code==200 and A.get('/api/projects').status_code==401)
    # throttle
    T=TestClient(app); codes=[T.post('/api/auth/login',json=dict(email='a@a.com',password='x')).status_code for _ in range(7)]
    chk('throttle',429 in codes)
    chk('audit',len(root.get('/api/admin/audit').json())>5)
    ov=root.get('/api/admin/overview').json(); chk('overview',len(ov['orgs'])==2)
    # data folders separate
    chk('folders',os.path.isdir(f'{d}/orgs/{a["id"]}/projects') and os.path.isdir(f'{d}/orgs/{b["id"]}/projects'))
    chk('pw not plaintext','PassA12345' not in open(f'{d}/accounts.json').read())
print('passed',ok,'failed',bad); shutil.rmtree(d,ignore_errors=True)
