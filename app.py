#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Software Library Manager - standalone final version."""
import os,re,json,time,hashlib,secrets,threading,mimetypes,urllib.parse,urllib.request,urllib.error,http.server,socketserver,html as htmlmod
from datetime import datetime

ROOT_DIR=os.environ.get('LIB_ROOT_DIR','/data')
DATA_DIR=os.environ.get('LIB_DATA_DIR','/app/data')
PORT=int(os.environ.get('LIB_PORT','8899'))
WATCH_INTERVAL=int(os.environ.get('LIB_WATCH_INTERVAL','3600'))
MAX_UPLOAD_SIZE=500*1024*1024
MAX_DOWNLOAD_SIZE=2*1024*1024*1024
CONFIG_FILE=os.path.join(DATA_DIR,'config.json')
USERS_FILE=os.path.join(DATA_DIR,'users.json')
SCAN_FILE=os.path.join(DATA_DIR,'scan_result.json')
UPLOAD_DIR=os.path.join(ROOT_DIR,'uploads')
SKIP_DIRS={'logs','log','工作文件','文档','.workbuddy-ai','$RECYCLE.BIN','System Volume Information','@Recycle','.zsshare_trash','docker','tmp','temp','cache','__pycache__','node_modules','uploads'}
EXT={'.exe':'EXE','.msi':'MSI','.iso':'ISO','.img':'IMG','.zip':'ZIP','.7z':'7Z','.rar':'RAR','.gz':'GZ','.esd':'ESD','.xz':'XZ','.apk':'APK','.dmg':'DMG','.pkg':'PKG','.deb':'DEB','.rpm':'RPM','.vmdk':'VMDK','.ova':'OVA','.ovf':'OVF','.vdi':'VDI','.qcow2':'QCOW2','.wim':'WIM','.txt':'TXT'}
CAT=['操作系统','虚拟化','NAS/存储','路由器/软路由','数据库','开发工具','系统工具','网络/代理','浏览器','办公软件','设计/创意','媒体/娱乐','远程控制','PE/维护','驱动','其他']
DB={'windows':('Windows','操作系统','Windows 系统镜像','https://www.microsoft.com/windows'),'ubuntu':('Ubuntu Server','操作系统','Ubuntu Server 服务器系统','https://ubuntu.com'),'debian':('Debian','操作系统','Debian GNU/Linux 系统','https://www.debian.org'),'centos':('CentOS','操作系统','CentOS Linux 服务器系统','https://www.centos.org'),'openwrt':('OpenWrt','路由器/软路由','OpenWrt 软路由固件','https://openwrt.org'),'proxmox':('Proxmox VE','虚拟化','开源虚拟化管理平台','https://www.proxmox.com'),'truenas':('TrueNAS SCALE','NAS/存储','开源 NAS 操作系统','https://www.truenas.com'),'fnos':('飞牛 OS (fnOS)','NAS/存储','飞牛私有云 NAS 操作系统','https://www.fnos.com'),'ikuai':('iKuai 爱快','路由器/软路由','爱快流控路由系统','https://www.ikuai8.com'),'esxi':('VMware ESXi','虚拟化','VMware ESXi 裸机虚拟化系统','https://www.vmware.com'),'sql server':('SQL Server','数据库','Microsoft SQL Server','https://www.microsoft.com/sql-server'),'mysql':('MySQL','数据库','MySQL 数据库','https://www.mysql.com'),'redis':('Redis','数据库','Redis 内存数据库','https://redis.io'),'wepe':('WePE 微PE','PE/维护','微PE工具箱','https://www.wepe.com.cn'),'virtio':('VirtIO 驱动','驱动','VirtIO Windows 驱动','https://fedoraproject.org/wiki/Windows_Virtio_Drivers'),'winrar':('WinRAR','系统工具','压缩解压工具','https://www.rarlab.com'),'rufus':('Rufus','系统工具','USB 启动盘制作工具','https://rufus.ie'),'rustdesk':('RustDesk','远程控制','远程桌面','https://rustdesk.com'),'chrome':('Google Chrome','浏览器','Google Chrome 浏览器','https://www.google.com/chrome/'),'firefox':('Firefox','浏览器','Mozilla Firefox 浏览器','https://www.mozilla.org/firefox/'),'git':('Git','开发工具','Git 版本控制工具','https://git-scm.com'),'python':('Python','开发工具','Python 编程语言','https://www.python.org')}

def load(p,default):
    try:
        with open(p,encoding='utf-8') as f:return json.load(f)
    except Exception:return default

def save(p,x):
    os.makedirs(os.path.dirname(p),exist_ok=True);tmp=p+'.tmp'
    with open(tmp,'w',encoding='utf-8') as f:json.dump(x,f,ensure_ascii=False,indent=2)
    os.replace(tmp,p)

def default_cfg():return {'software':{}}
def users():return load(USERS_FILE,{'users':[]})
def has_users():return bool(users().get('users'))
def hashpw(p,s=None):
    s=s or secrets.token_hex(16);return s,hashlib.pbkdf2_hmac('sha256',p.encode(),bytes.fromhex(s),150000).hex()
def checkpw(p,u):
    try:return secrets.compare_digest(hashpw(p,u['salt'])[1],u['password'])
    except Exception:return False
def safe_name(n):return re.sub(r'[\\/:*?"<>|\x00-\x1f]','_',os.path.basename(n)).strip() or 'download.bin'
def fmt(n):
    n=float(n)
    for u in ['B','KB','MB','GB','TB']:
        if n<1024:return f'{n:.1f} {u}' if u!='B' else f'{int(n)} B'
        n/=1024
    return f'{n:.1f} PB'
def file_type(p):
    l=p.lower()
    for e,t in sorted(EXT.items(),key=lambda x:-len(x[0])):
        if l.endswith(e):return t
    return 'FILE'
def identify(fn):
    s=fn.lower().replace('_',' ').replace('-',' ')
    for k,v in DB.items():
        if k in s:return v
    return (os.path.splitext(fn)[0],'其他','', '')

def scan():
    out=[]
    if os.path.isdir(ROOT_DIR):
        for root,dirs,files in os.walk(ROOT_DIR):
            dirs[:]=[d for d in dirs if d not in SKIP_DIRS and not d.startswith('.')]
            for fn in files:
                if fn in {'README.md','index.html','config.json','scan_result.json','users.json'} or fn.startswith('.') :continue
                p=os.path.join(root,fn)
                try:
                    st=os.stat(p); rel=os.path.relpath(p,ROOT_DIR).replace('\\','/')
                    out.append({'filename':fn,'path':rel,'size':st.st_size,'sizeText':fmt(st.st_size),'fileType':file_type(fn),'date':datetime.fromtimestamp(st.st_mtime).strftime('%Y-%m-%d %H:%M')})
                except OSError:pass
    out.sort(key=lambda x:x['filename'].lower())
    save(SCAN_FILE,out);return out

def library():
    files=scan();cfg=load(CONFIG_FILE,default_cfg()).get('software',{});groups={}
    for f in files:
        key,name,cat,official=identify(f['filename']);c=cfg.get(key,{})
        if key not in groups:groups[key]={'key':key,'name':c.get('displayName') or name,'category':c.get('category') or cat,'desc':c.get('desc') or '', 'official':c.get('official') or c.get('customOfficial') or official,'versions':[]}
        vc=(c.get('versions',{}) or {}).get(f['path'],{})
        f=dict(f);f['downloadUrl']=vc.get('downloadUrl','');f['localUrl']='/download/'+urllib.parse.quote(f['path'],safe='/')
        groups[key]['versions'].append(f)
    for key,c in cfg.items():
        if key not in groups and isinstance(c,dict) and c.get('displayName'):
            groups[key]={'key':key,'name':c['displayName'],'category':c.get('category','其他'),'desc':c.get('desc',''),'official':c.get('official') or c.get('customOfficial',''),'versions':[]}
    a=list(groups.values());a.sort(key=lambda x:x['name'].lower());return a

SESS={}
def current(h):
    sid=h.get('Cookie','').replace('session=','').split(';')[0].strip();return SESS.get(sid)
def admin_required(h):
    u=current(h);return u if u and u.get('role')=='admin' else None

def page():
    data=library(); cj=json.dumps(data,ensure_ascii=False)
    return '''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>软件库</title><style>
:root{--bg:#f5f7fa;--card:#fff;--text:#182033;--muted:#6b7280;--line:#e5e7eb;--a:#3b73f0;--danger:#dc2626}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Microsoft YaHei",sans-serif}header{position:sticky;top:0;z-index:5;background:#fffffff2;border-bottom:1px solid var(--line);backdrop-filter:blur(12px)}.bar{max-width:1400px;margin:auto;padding:11px 16px;display:flex;align-items:center;gap:12px}.logo{font-weight:800;white-space:nowrap}.search{flex:1;max-width:680px;margin:auto}.search input,.select,input,select{width:100%;border:1px solid var(--line);border-radius:9px;padding:9px 11px;background:#f8fafc;outline:0}.actions{display:flex;gap:7px;align-items:center}.btn{border:1px solid var(--line);background:#fff;border-radius:8px;padding:8px 11px;cursor:pointer}.primary{background:var(--a);color:#fff;border-color:var(--a)}main{max-width:1400px;margin:auto;padding:22px 16px}.hero{display:flex;justify-content:space-between;gap:12px;align-items:end}.hero h1{margin:0;font-size:24px}.muted{color:var(--muted);font-size:12px}.filter{margin:18px 0;display:flex;gap:10px}.filter select{max-width:260px}.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:12px}.card,.panel{background:var(--card);border:1px solid var(--line);border-radius:13px;padding:14px;box-shadow:0 3px 15px #00000009}.card h3{margin:0;font-size:14px}.tag{display:inline-block;font-size:10px;padding:2px 7px;border-radius:5px;background:#eef3ff;color:var(--a);margin:6px 0}.file{border-top:1px solid #f0f1f3;padding:9px 0}.file:first-child{border-top:0}.fn{font-size:12px;word-break:break-all}.meta{font-size:10px;color:var(--muted);margin:3px 0 7px}.links{display:flex;gap:6px;flex-wrap:wrap}.links a,.links button{font-size:10px;text-decoration:none;border:1px solid var(--line);background:#fff;border-radius:6px;padding:5px 7px;color:var(--text);cursor:pointer}.links a.blue{color:var(--a)}.empty{text-align:center;padding:70px;color:var(--muted)}.modal{position:fixed;inset:0;background:#0007;display:none;align-items:center;justify-content:center;padding:15px;z-index:20}.box{background:#fff;border-radius:13px;padding:18px;width:min(680px,100%);max-height:90vh;overflow:auto}.box h2{margin-top:0}.row{display:flex;gap:8px;margin:8px 0}.row>*{flex:1}.adminitem{border-bottom:1px solid var(--line);padding:12px 0}.adminitem:last-child{border:0}.small{font-size:11px}.toast{position:fixed;bottom:20px;left:50%;transform:translateX(-50%);background:#111827;color:#fff;padding:9px 14px;border-radius:8px;display:none;z-index:30}@media(max-width:650px){.bar{flex-wrap:wrap}.search{order:3;flex-basis:100%}.actions .user{display:none}.grid{grid-template-columns:1fr}.hero{align-items:start}.row{display:block}.row>*{margin-bottom:7px}}
</style></head><body><header><div class="bar"><div class="logo">📦 软件库</div><div class="search"><input id="q" placeholder="搜索软件或文件名…" oninput="render()"></div><div class="actions"><span id="who" class="muted user"></span><button class="btn" onclick="openLogin()">登录</button><button class="btn primary" id="adminBtn" style="display:none" onclick="openAdmin()">管理</button></div></div></header><main><div class="hero"><div><h1>软件库</h1><div class="muted" id="stats"></div></div></div><div class="filter"><select id="cat" onchange="render()"><option value="">全部分类</option></select></div><div id="list"></div></main><div id="modal" class="modal"><div class="box" id="box"></div></div><div id="toast" class="toast"></div><script>const DATA='''+cj+''';let ME=null;const esc=s=>String(s??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));const post=async(u,d)=>{let r=await fetch(u,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(d)});return r.json()};function toast(s){let e=document.getElementById('toast');e.textContent=s;e.style.display='block';setTimeout(()=>e.style.display='none',2200)}function render(){let q=document.getElementById('q').value.toLowerCase(),c=document.getElementById('cat').value;let a=DATA.filter(x=>(!c||x.category===c)&&(!q||(x.name+' '+x.desc+' '+x.versions.map(v=>v.filename).join(' ')).toLowerCase().includes(q)));document.getElementById('stats').textContent=`${a.length} 个软件 · ${a.reduce((n,x)=>n+x.versions.length,0)} 个文件`;document.getElementById('list').innerHTML=a.length?a.map(x=>`<section class="card"><h3>${esc(x.name)}</h3><span class="tag">${esc(x.category)}</span><div class="muted">${esc(x.desc)}</div>${x.official?`<div class="links"><a class="blue" target="_blank" href="${esc(x.official)}">官网</a></div>`:''}${x.versions.map(v=>`<div class="file"><div class="fn">${esc(v.filename)}</div><div class="meta">${esc(v.fileType)} · ${esc(v.sizeText)} · ${esc(v.date)}</div><div class="links"><a href="${v.localUrl}">下载</a>${v.downloadUrl?`<a class="blue" target="_blank" href="${esc(v.downloadUrl)}">官方直链</a>`:''}</div></div>`).join('')}</section>`).join(''):'<div class="empty">没有找到文件</div>'}function init(){let s=[...new Set(DATA.map(x=>x.category))].sort();document.getElementById('cat').innerHTML='<option value="">全部分类</option>'+s.map(x=>`<option>${esc(x)}</option>`).join('');render();fetch('/api/me').then(r=>r.json()).then(x=>{ME=x.user||null;if(ME){document.getElementById('who').textContent=ME.username;document.querySelector('.actions button').textContent='退出';document.querySelector('.actions button').onclick=logout;if(ME.role==='admin')document.getElementById('adminBtn').style.display='block'}})}function closeM(){document.getElementById('modal').style.display='none'}function openLogin(){document.getElementById('box').innerHTML=`<h2>${DATA.length?'登录':'创建管理员'}</h2><div class="row"><input id="un" placeholder="用户名"></div><div class="row"><input id="pw" type="password" placeholder="密码"></div><div class="row"><button class="btn primary" onclick="login()">${DATA.length?'登录':'注册管理员'}</button><button class="btn" onclick="closeM()">取消</button></div>`;document.getElementById('modal').style.display='flex'}async function login(){let u=document.getElementById('un').value,p=document.getElementById('pw').value;let r=await post('/api/login',{username:u,password:p});if(r.success){toast('登录成功');closeM();location.reload()}else toast(r.error)}async function logout(){await post('/api/logout',{});location.reload()}function openAdmin(){fetch('/api/admin/data').then(r=>r.json()).then(r=>{if(!r.success)return toast(r.error);let users=r.users;document.getElementById('box').innerHTML=`<h2>管理后台</h2><h3>新增用户</h3><div class="row"><input id="nu" placeholder="用户名"><input id="np" type="password" placeholder="密码"><select id="nr"><option value="user">普通用户</option><option value="admin">管理员</option></select><button class="btn primary" onclick="addUser()">添加</button></div><h3>用户</h3>${users.map(u=>`<div class="adminitem"><b>${esc(u.username)}</b> <span class="tag">${esc(u.role)}</span>${users.length>1?` <button class="btn" onclick="delUser('${esc(u.username)}')">删除</button>`:''}</div>`).join('')}<h3>软件配置</h3><div id="sw">${r.software.map(x=>`<div class="adminitem"><b>${esc(x.name)}</b><div class="small">官网：<input id="off-${esc(x.key)}" value="${esc(x.official)}"></div>${x.versions.map(v=>`<div class="small" style="margin-top:6px">${esc(v.filename)}<input id="url-${esc(x.key)}-${encodeURIComponent(v.path)}" value="${esc(v.downloadUrl)}" placeholder="该文件官方下载地址"><button class="btn" onclick="saveUrl(${JSON.stringify(x.key)},${JSON.stringify(v.path)})">保存</button><button class="btn" onclick="fetchRemote(${JSON.stringify(x.key)},${JSON.stringify(v.path)})">下载留存</button></div>`).join('')}<button class="btn" onclick="saveOfficial(${JSON.stringify(x.key)})">保存官网</button></div>`).join('')}</div><button class="btn" onclick="closeM()">关闭</button>`;document.getElementById('modal').style.display='flex'})}async function addUser(){let r=await post('/api/admin/user',{username:document.getElementById('nu').value,password:document.getElementById('np').value,role:document.getElementById('nr').value});toast(r.success?'用户已添加':r.error);if(r.success)openAdmin()}async function delUser(u){let r=await post('/api/admin/user/delete',{username:u});toast(r.success?'已删除':r.error);if(r.success)openAdmin()}async function saveOfficial(k){let v=document.getElementById('off-'+k).value;let r=await post('/api/admin/software',{name:k,official:v});toast(r.success?'已保存':r.error);if(r.success)location.reload()}async function saveUrl(k,p){let id='url-'+k+'-'+encodeURIComponent(p),v=document.getElementById(id).value;let r=await post('/api/admin/software',{name:k,versionPath:p,downloadUrl:v});toast(r.success?'已保存':'保存失败：'+r.error)}async function fetchRemote(k,p){let id='url-'+k+'-'+encodeURIComponent(p),v=document.getElementById(id).value;if(!v)return toast('请先填写官方下载地址');let r=await post('/api/admin/fetch',{name:k,path:p,url:v});toast(r.success?'已开始下载：完成后自动入库':r.error)}init();</script></body></html>'''

def jsonbody(h):
    n=int(h.headers.get('Content-Length','0') or 0)
    if n>2*1024*1024:raise ValueError('请求过大')
    return json.loads(h.rfile.read(n) or b'{}')

def send(h,obj,status=200):
    b=json.dumps(obj,ensure_ascii=False).encode();h.send_response(status);h.send_header('Content-Type','application/json; charset=utf-8');h.send_header('Content-Length',str(len(b)));h.end_headers();h.wfile.write(b)

class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self,*a):pass
    def do_GET(self):
        p=urllib.parse.urlparse(self.path)
        if p.path=='/':
            b=page().encode();self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b);return
        if p.path=='/api/me':send(self,{'user':current(self)});return
        if p.path.startswith('/download/'):
            rel=urllib.parse.unquote(p.path[len('/download/'):]).lstrip('/');full=os.path.realpath(os.path.join(ROOT_DIR,rel));root=os.path.realpath(ROOT_DIR)
            if not full.startswith(root+os.sep) or not os.path.isfile(full):self.send_error(404);return
            size=os.path.getsize(full);self.send_response(200);self.send_header('Content-Type',mimetypes.guess_type(full)[0] or 'application/octet-stream');self.send_header('Content-Length',str(size));self.send_header('Content-Disposition',f'attachment; filename="{safe_name(os.path.basename(full))}"');self.end_headers()
            with open(full,'rb') as f:
                while True:
                    x=f.read(1024*1024)
                    if not x:break
                    self.wfile.write(x)
            return
        self.send_error(404)
    def do_POST(self):
        p=urllib.parse.urlparse(self.path).path
        try:d=jsonbody(self)
        except Exception as e:return send(self,{'success':False,'error':str(e)},400)
        u=current(self)
        if p=='/api/login':
            us=users();name=str(d.get('username','')).strip();pw=str(d.get('password',''))
            if not us.get('users'):
                if len(name)<2 or len(pw)<6:return send(self,{'success':False,'error':'首次注册：用户名至少2位，密码至少6位'})
                salt,h=hashpw(pw);us={'users':[{'username':name,'password':h,'salt':salt,'role':'admin'}]};save(USERS_FILE,us);u=us['users'][0]
            else:
                u=next((x for x in us['users'] if x.get('username')==name),None)
                if not u or not checkpw(pw,u):return send(self,{'success':False,'error':'用户名或密码错误'},401)
            sid=secrets.token_urlsafe(32);SESS[sid]=u.copy();send(self,{'success':True,'user':u});self.send_header('Set-Cookie',f'session={sid}; HttpOnly; SameSite=Lax; Path=/');return
        if p=='/api/logout':
            sid=self.headers.get('Cookie','').replace('session=','').split(';')[0].strip();SESS.pop(sid,None);send(self,{'success':True});self.send_header('Set-Cookie','session=; Max-Age=0; Path=/');return
        if p=='/api/admin/data':
            if not admin_required(self):return send(self,{'success':False,'error':'需要管理员权限'},403)
            send(self,{'success':True,'users':users().get('users',[]),'software':library()});return
        if p=='/api/admin/user':
            if not admin_required(self):return send(self,{'success':False,'error':'需要管理员权限'},403)
            name=str(d.get('username','')).strip();pw=str(d.get('password',''));role=d.get('role','user')
            us=users()
            if len(name)<2 or len(pw)<6:return send(self,{'success':False,'error':'用户名至少2位，密码至少6位'})
            if any(x.get('username')==name for x in us['users']):return send(self,{'success':False,'error':'用户已存在'})
            salt,h=hashpw(pw);us['users'].append({'username':name,'password':h,'salt':salt,'role':'admin' if role=='admin' else 'user'});save(USERS_FILE,us);return send(self,{'success':True})
        if p=='/api/admin/user/delete':
            if not admin_required(self):return send(self,{'success':False,'error':'需要管理员权限'},403)
            name=str(d.get('username',''));us=users();target=next((x for x in us['users'] if x.get('username')==name),None)
            if not target:return send(self,{'success':False,'error':'用户不存在'})
            if target.get('role')=='admin' and sum(x.get('role')=='admin' for x in us['users'])<=1:return send(self,{'success':False,'error':'不能删除最后一个管理员'})
            us['users']=[x for x in us['users'] if x.get('username')!=name];save(USERS_FILE,us);return send(self,{'success':True})
        if p=='/api/admin/software':
            if not admin_required(self):return send(self,{'success':False,'error':'需要管理员权限'},403)
            name=str(d.get('name','')).strip();cfg=load(CONFIG_FILE,default_cfg());sw=cfg.setdefault('software',{});item=sw.setdefault(name,{})
            if d.get('versionPath'):
                url=str(d.get('downloadUrl','')).strip()
                if url and not re.match(r'^https?://',url,re.I):return send(self,{'success':False,'error':'下载地址必须是 http/https'})
                item.setdefault('versions',{})[str(d['versionPath'])]={'downloadUrl':url}
            else:
                if 'official' in d:item['official']=str(d.get('official') or '').strip()
                if 'displayName' in d:item['displayName']=safe_name(d['displayName'])
                if 'category' in d:item['category']=d['category']
                if 'desc' in d:item['desc']=str(d.get('desc') or '')
            save(CONFIG_FILE,cfg);return send(self,{'success':True})
        if p=='/api/admin/fetch':
            if not admin_required(self):return send(self,{'success':False,'error':'需要管理员权限'},403)
            url=str(d.get('url','')).strip();rel=str(d.get('path','')).replace('\\','/').lstrip('/')
            if not re.match(r'^https?://',url,re.I):return send(self,{'success':False,'error':'仅支持 HTTP/HTTPS'})
            threading.Thread(target=remote,args=(url,rel),daemon=True).start();return send(self,{'success':True,'message':'下载已开始'})
        return send(self,{'success':False,'error':'Not Found'},404)

def remote(url,rel):
    try:
        os.makedirs(UPLOAD_DIR,exist_ok=True);req=urllib.request.Request(url,headers={'User-Agent':'Software-Library/8.0'});r=urllib.request.urlopen(req,timeout=60);fn=safe_name(os.path.basename(urllib.parse.unquote(urllib.parse.urlparse(r.geturl()).path)) or os.path.basename(rel));dest=os.path.join(UPLOAD_DIR,fn);base,ext=os.path.splitext(fn);i=1
        while os.path.exists(dest):dest=os.path.join(UPLOAD_DIR,f'{base}_{i}{ext}');i+=1
        total=0
        with open(dest,'wb') as f:
            while True:
                b=r.read(1024*1024)
                if not b:break
                total+=len(b)
                if total>MAX_DOWNLOAD_SIZE:raise ValueError('远程文件超过2GB限制')
                f.write(b)
        scan()
    except Exception as e:print('[remote]',e)

def main():
    os.makedirs(DATA_DIR,exist_ok=True);os.makedirs(ROOT_DIR,exist_ok=True);scan()
    class S(socketserver.ThreadingMixIn,socketserver.TCPServer):daemon_threads=True;allow_reuse_address=True
    with S(('',PORT),Handler) as srv:
        print(f'Software Library v8 running: http://0.0.0.0:{PORT} root={ROOT_DIR}')
        if WATCH_INTERVAL>0:threading.Thread(target=lambda:watch(srv),daemon=True).start()
        srv.serve_forever()
def watch(srv):
    while True:
        time.sleep(WATCH_INTERVAL)
        try:scan()
        except Exception as e:print('[scan]',e)
if __name__=='__main__':main()
