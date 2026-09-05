#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Software Library Manager v7

v7 keeps the proven v6 scanner/auth/download backend and replaces the generated
frontend with a compact responsive UI. Admins can edit file display metadata,
official/download URLs and user accounts; normal users can upload files.
"""
import os
import json
import html
import socket
import ipaddress
import urllib.parse
from datetime import datetime

import app

# v7 defaults are intentionally compatible with the v6 data directory.
VERSION = "7.0"


def _cfg():
    return app.load_json(app.CONFIG_FILE, app.default_config())


def build_entry_list_v7():
    entries = app._ORIGINAL_BUILD_ENTRY_LIST()
    cfg = _cfg().get("software", {})
    for e in entries:
        x = cfg.get(e["path"], {})
        e["displayName"] = x.get("displayName") or e["filename"]
        e["version"] = x.get("version", "")
        e["source"] = x.get("source", "")
        # Never invent a version when it is not explicitly configured.
        e["name"] = e["displayName"]
    return entries


# Save the v6 implementation before monkey-patching the module globals.
app._ORIGINAL_BUILD_ENTRY_LIST = app.build_entry_list
app.build_entry_list = build_entry_list_v7


def _safe_remote_url(url):
    """Allow HTTP(S), but reject localhost/private/link-local destinations."""
    try:
        p = urllib.parse.urlparse(url)
        if p.scheme not in ("http", "https") or not p.hostname:
            return False, "只允许 http/https 地址"
        host = p.hostname
        try:
            ips = {x[4][0] for x in socket.getaddrinfo(host, None)}
        except socket.gaierror:
            return False, "域名无法解析"
        for raw in ips:
            try:
                ip = ipaddress.ip_address(raw)
                if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
                    return False, "不允许下载内网或保留地址"
            except ValueError:
                pass
        return True, ""
    except Exception:
        return False, "下载地址无效"


_ORIGINAL_FETCH_HANDLER = app.SoftwareHandler._handle_fetch_url


def _handle_fetch_url_v7(self):
    if app._fetch_status.get("active"):
        self._serve_json({"success": False, "error": "已有下载任务进行中"})
        return
    data = self._read_body()
    url = (data.get("url") or "").strip()
    name = (data.get("name") or "").strip() or None
    ok, err = _safe_remote_url(url)
    if not ok:
        self._serve_json({"success": False, "error": err})
        return
    import threading
    threading.Thread(target=app.fetch_remote_file, args=(url, name), daemon=True).start()
    self._serve_json({"success": True, "message": "下载已开始"})


app.SoftwareHandler._handle_fetch_url = _handle_fetch_url_v7


def _handle_admin_software_v7(self):
    try:
        data = self._read_body()
        path = data.get("path")
        if not path:
            self._serve_json({"success": False, "error": "path is required"})
            return
        cfg = _cfg()
        sw = cfg.setdefault("software", {})
        item = sw.setdefault(path, {})
        allowed = ("category", "icon", "desc", "official", "customOfficial", "showOfficial",
                   "displayName", "version", "source")
        for key in allowed:
            if key in data:
                value = data[key]
                if key in ("displayName", "version", "source", "desc", "official", "customOfficial"):
                    value = str(value or "").strip()
                    if key == "displayName":
                        value = os.path.basename(value.replace("\\", "/")) or ""
                if key == "showOfficial":
                    value = bool(value)
                item[key] = value
        app.save_json(app.CONFIG_FILE, cfg)
        self._serve_json({"success": True, "message": "已保存"})
    except Exception as e:
        self._serve_json({"success": False, "error": str(e)})


app.SoftwareHandler._handle_admin_software = _handle_admin_software_v7


# Prevent the last administrator from being deleted/demoted accidentally.
_ORIGINAL_DELETE_USER = app.delete_user


def delete_user_v7(username):
    users = app.load_users()
    target = next((u for u in users.get("users", []) if u.get("username") == username), None)
    if not target:
        return False, "用户不存在"
    if target.get("role") == "admin":
        admins = [u for u in users.get("users", []) if u.get("role") == "admin"]
        if len(admins) <= 1:
            return False, "不能删除最后一个管理员"
    return _ORIGINAL_DELETE_USER(username)


app.delete_user = delete_user_v7


# ------------------------- v7 frontend -------------------------
CSS = r'''
:root{--bg:#f4f6f8;--card:#fff;--text:#172033;--muted:#6b7280;--line:#e5e7eb;--accent:#3b73f0;--accent2:#285fd4;--green:#16a34a;--red:#dc2626;--orange:#d97706;--sidebar:#111827;--sidebar2:#1f2937;--radius:14px;--shadow:0 5px 20px rgba(15,23,42,.06)}
*{box-sizing:border-box}html,body{margin:0;min-height:100%;background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Microsoft YaHei",sans-serif}body{overflow-x:hidden}button,input,select{font:inherit}.app{min-height:100vh}.top{height:62px;background:rgba(255,255,255,.94);backdrop-filter:blur(14px);border-bottom:1px solid var(--line);display:flex;align-items:center;gap:14px;padding:0 20px;position:sticky;top:0;z-index:30}.brand{font-weight:800;font-size:17px;white-space:nowrap}.brand small{display:block;font-size:9px;color:var(--muted);font-weight:500;letter-spacing:.5px}.search{flex:1;max-width:650px;margin:auto;position:relative}.search input{width:100%;height:38px;border:1px solid var(--line);border-radius:10px;background:#f7f8fa;padding:0 14px 0 38px;outline:0}.search input:focus{border-color:var(--accent);background:#fff;box-shadow:0 0 0 3px rgba(59,115,240,.1)}.search:before{content:'⌕';position:absolute;left:14px;top:6px;color:var(--muted);font-size:20px;z-index:1}.top-actions{display:flex;gap:7px;align-items:center}.btn{border:1px solid var(--line);background:#fff;color:var(--text);border-radius:9px;padding:7px 11px;font-size:12px;cursor:pointer;white-space:nowrap}.btn:hover{border-color:#b9c3d4}.btn.primary{background:var(--accent);border-color:var(--accent);color:#fff}.btn.primary:hover{background:var(--accent2)}.btn.danger{color:var(--red);border-color:#fecaca}.btn.green{color:var(--green);border-color:#bbf7d0}.btn:disabled{opacity:.5;cursor:not-allowed}.user-pill{font-size:12px;color:var(--muted);white-space:nowrap}.layout{display:flex;max-width:1500px;margin:auto}.side{width:220px;flex:0 0 220px;padding:18px 12px;position:sticky;top:62px;height:calc(100vh - 62px);overflow:auto}.nav-title{font-size:10px;color:#9ca3af;margin:4px 10px 8px;text-transform:uppercase;letter-spacing:1px}.nav{display:flex;flex-direction:column;gap:4px}.nav button{border:0;background:transparent;text-align:left;padding:10px 12px;border-radius:9px;color:var(--muted);cursor:pointer;font-size:13px}.nav button:hover,.nav button.active{background:#fff;color:var(--accent);box-shadow:var(--shadow)}.main{flex:1;min-width:0;padding:22px 20px 40px}.hero{display:flex;align-items:end;justify-content:space-between;gap:15px;margin-bottom:18px}.hero h1{font-size:22px;margin:0 0 3px}.hero p{margin:0;color:var(--muted);font-size:12px}.stats{display:flex;gap:8px}.stat{background:#fff;border:1px solid var(--line);border-radius:10px;padding:7px 13px;text-align:center}.stat b{display:block;font-size:15px}.stat span{font-size:9px;color:var(--muted)}.filters{display:flex;gap:8px;overflow:auto;padding-bottom:3px;margin-bottom:18px}.chip{border:1px solid var(--line);background:#fff;color:var(--muted);padding:6px 11px;border-radius:999px;font-size:11px;cursor:pointer;white-space:nowrap}.chip.active{background:var(--accent);color:#fff;border-color:var(--accent)}.section{margin-bottom:22px}.section-head{display:flex;justify-content:space-between;align-items:center;margin-bottom:9px}.section-head h2{font-size:14px;margin:0}.section-head span{font-size:10px;color:var(--muted)}.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(270px,1fr));gap:10px}.card{background:#fff;border:1px solid var(--line);border-radius:var(--radius);padding:13px;box-shadow:var(--shadow);transition:.15s;min-width:0}.card:hover{transform:translateY(-1px);border-color:#cbd5e1}.card-top{display:flex;gap:10px}.ico{width:38px;height:38px;border-radius:9px;background:#eef3ff;color:var(--accent);display:flex;align-items:center;justify-content:center;font-weight:800;font-size:12px;flex:0 0 auto}.ct{min-width:0;flex:1}.name{font-size:13px;font-weight:700;word-break:break-all;line-height:1.4}.version{display:inline-block;margin-top:3px;font-size:10px;color:var(--accent);background:#eef3ff;padding:1px 6px;border-radius:4px}.desc{font-size:10px;color:var(--muted);margin-top:4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.meta{display:flex;gap:5px;flex-wrap:wrap;margin-top:9px}.tag{font-size:9px;color:var(--muted);background:#f6f7f9;padding:2px 6px;border-radius:4px}.tag.type{color:var(--orange)}.tag.size{color:var(--green)}.card-foot{display:flex;justify-content:flex-end;gap:6px;margin-top:10px}.empty{text-align:center;color:var(--muted);padding:60px 20px}.admin{display:flex;gap:16px}.admin-nav{width:180px;flex:0 0 180px}.admin-nav button{width:100%;border:0;background:transparent;text-align:left;padding:10px;border-radius:8px;font-size:12px;color:var(--muted);cursor:pointer}.admin-nav button.active,.admin-nav button:hover{background:#fff;color:var(--accent)}.panel{flex:1;min-width:0;background:#fff;border:1px solid var(--line);border-radius:14px;padding:18px;box-shadow:var(--shadow)}.panel h2{font-size:16px;margin:0 0 4px}.panel .hint{font-size:11px;color:var(--muted);margin-bottom:14px}.toolbar{display:flex;gap:7px;flex-wrap:wrap;margin-bottom:12px}.toolbar input,.toolbar select,.edit input,.edit select{border:1px solid var(--line);border-radius:8px;padding:7px 9px;outline:0;background:#fff;font-size:11px;min-width:0}.toolbar input:focus,.edit input:focus,.edit select:focus{border-color:var(--accent)}.table{border:1px solid var(--line);border-radius:10px;overflow:auto}.row{display:grid;grid-template-columns:minmax(180px,1.2fr) minmax(150px,1fr) 95px;gap:8px;padding:9px 10px;border-bottom:1px solid #f0f1f3;align-items:center}.row:last-child{border:0}.row.head{font-size:10px;color:var(--muted);background:#fafafa}.edit{display:grid;grid-template-columns:1fr 1fr;gap:8px}.edit label{font-size:10px;color:var(--muted)}.edit label.full{grid-column:1/-1}.edit input,.edit select{width:100%;margin-top:4px}.user-row{display:flex;align-items:center;gap:10px;padding:10px 0;border-bottom:1px solid #f0f1f3}.user-row .un{font-weight:600;font-size:12px;flex:1}.role{font-size:9px;padding:3px 7px;border-radius:5px;background:#eef3ff;color:var(--accent)}.role.admin{background:#fff3e8;color:var(--orange)}.modal-mask{position:fixed;inset:0;background:rgba(15,23,42,.45);display:flex;align-items:center;justify-content:center;z-index:100}.modal{width:min(620px,92vw);max-height:90vh;overflow:auto;background:#fff;border-radius:14px;padding:20px}.modal h2{margin:0 0 15px;font-size:17px}.modal-actions{display:flex;justify-content:flex-end;gap:7px;margin-top:16px}.progress{height:8px;background:#edf0f4;border-radius:99px;overflow:hidden;margin-top:12px}.progress i{display:block;height:100%;background:var(--accent);width:0}.toast{position:fixed;left:50%;bottom:25px;transform:translateX(-50%);background:#111827;color:#fff;padding:9px 15px;border-radius:8px;font-size:12px;z-index:999;display:none}.toast.show{display:block}.mobile-menu{display:none}.muted{color:var(--muted)}
@media(max-width:900px){.side{width:70px;flex-basis:70px}.nav button{font-size:0;text-align:center}.nav button:before{content:'•';font-size:18px}.nav-title{font-size:0}.admin-nav{display:none}.admin{display:block}.top{padding:0 10px}.brand{font-size:14px}.user-pill{display:none}.grid{grid-template-columns:repeat(auto-fill,minmax(220px,1fr))}}
@media(max-width:620px){.top{height:auto;min-height:58px;flex-wrap:wrap;padding:8px 10px}.search{order:3;flex-basis:100%;max-width:none}.layout{display:block}.side{display:none}.main{padding:15px 10px}.hero{align-items:flex-start}.hero h1{font-size:18px}.stats{display:none}.grid{grid-template-columns:1fr}.top-actions .admin-btn{display:none}.mobile-menu{display:block}.filters{margin-right:-10px}.row{grid-template-columns:1fr}.row.head{display:none}.edit{grid-template-columns:1fr}.edit label.full{grid-column:auto}.panel{padding:13px}}
'''


def esc(v):
    return html.escape(str(v or ""), quote=True)


def js(v):
    return json.dumps(v, ensure_ascii=False).replace("</", "<\\/")


def generate_html_v7():
    entries = app.build_entry_list()
    cats = {}
    for e in entries:
        cats[e["category"]] = cats.get(e["category"], 0) + 1
    data = json.dumps(entries, ensure_ascii=False)
    cats_json = json.dumps(cats, ensure_ascii=False)
    has_users = app.has_users()
    html_page = '''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>软件库 v7</title>''' + CSS + '''</head><body><div id="app"></div><div id="modal"></div><div class="toast" id="toast"></div><script>
const DATA=''' + js(entries) + ''', CATS=''' + cats_json + ''', HAS_USERS=''' + ('true' if has_users else 'false') + ''';
let ENTRIES=DATA, SESSION=null, page='home', adminPage='files', filter='', cat='全部', polling=false;
const $=id=>document.getElementById(id); const esc=s=>String(s??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
function toast(s){const t=$('toast');t.textContent=s;t.classList.add('show');setTimeout(()=>t.classList.remove('show'),2200)}
function cookie(n){return document.cookie.split('; ').find(x=>x.startsWith(n+'='))?.split('=').slice(1).join('=')||''}
async function api(url,opt={}){opt.headers=Object.assign({'Content-Type':'application/json'},opt.headers||{});if(SESSION)opt.headers['X-Session']=SESSION.token;let r=await fetch(url,opt);try{return await r.json()}catch(e){return {success:false,error:'服务器响应异常'}}}
function icon(e){return esc((e.ext||'FILE').replace('.','').slice(0,5).toUpperCase())}
function render(){renderTop(); if(page==='admin')renderAdmin(); else renderHome()}
function renderTop(){let a='';if(SESSION){a+='<span class="user-pill">'+esc(SESSION.username)+'</span>';if(SESSION.role==='admin')a+='<button class="btn admin-btn" onclick="goAdmin()">管理后台</button>';a+='<button class="btn" onclick="doUpload()">上传</button><button class="btn" onclick="logout()">退出</button>'}else{a+='<button class="btn primary" onclick="showLogin()">登录</button>'} $('app').innerHTML='<header class="top"><div class="brand" onclick="goHome()">软件库<small>SOFTWARE LIBRARY · v7</small></div><div class="search"><input id="search" value="'+esc(filter)+'" placeholder="搜索文件名、版本、分类..." oninput="filter=this.value;renderHome()"></div><div class="top-actions"><button class="btn mobile-menu" onclick="toggleNav()">菜单</button>'+a+'</div></header><div class="layout"><aside class="side" id="side"><div class="nav-title">导航</div><div class="nav"><button class="'+(page==='home'?'active':'')+'" onclick="goHome()">软件库</button><button onclick="scrollTop()">全部文件</button><button onclick="showUploadTip()">上传文件</button></div></aside><main class="main" id="main"></main></div>'}
function toggleNav(){$('side').style.display=$('side').style.display==='block'?'none':'block'} function scrollTop(){window.scrollTo({top:0,behavior:'smooth'})} function showUploadTip(){if(SESSION)doUpload();else showLogin()}
function goHome(){page='home';render()} function goAdmin(){if(SESSION?.role!=='admin'){showLogin();return}page='admin';render()}
function renderHome(){if(page!=='home')return;let list=ENTRIES.filter(e=>(cat==='全部'||e.category===cat)&&(!filter||[e.filename,e.displayName,e.version,e.category,e.desc].join(' ').toLowerCase().includes(filter.toLowerCase())));let h='<div class="hero"><div><h1>软件库</h1><p>文件名优先显示，版本仅在手动维护后展示。</p></div><div class="stats"><div class="stat"><b>'+ENTRIES.length+'</b><span>文件</span></div><div class="stat"><b>'+Object.keys(CATS).length+'</b><span>分类</span></div></div></div><div class="filters"><button class="chip '+(cat==='全部'?'active':'')+'" onclick="cat=\'全部\';renderHome()">全部 '+ENTRIES.length+'</button>';for(const [k,n] of Object.entries(CATS))h+='<button class="chip '+(cat===k?'active':'')+'" onclick="cat='+js(k)+';renderHome()">'+esc(k)+' '+n+'</button>';h+='</div>';
if(!list.length){h+='<div class="empty">没有找到匹配的软件文件</div>'}else{const groups={};for(const e of list)(groups[e.category]??=[]).push(e);for(const [k,arr] of Object.entries(groups)){h+='<section class="section"><div class="section-head"><h2>'+esc(k)+'</h2><span>'+arr.length+' 个文件</span></div><div class="grid">';for(const e of arr){const i=ENTRIES.indexOf(e), official=e.customOfficial||e.official||'';h+='<article class="card"><div class="card-top"><div class="ico">'+icon(e)+'</div><div class="ct"><div class="name" title="'+esc(e.displayName)+'">'+esc(e.displayName)+'</div>'+(e.version?'<span class="version">版本 '+esc(e.version)+'</span>':'')+'<div class="desc">'+esc(e.desc||'')+'</div></div></div><div class="meta"><span class="tag type">'+esc(e.fileType||e.ext)+'</span><span class="tag size">'+esc(e.sizeText)+'</span><span class="tag">'+esc(e.date||'')+'</span></div><div class="card-foot"><button class="btn primary" onclick="download('+i+')">下载</button>'+(e.showOfficial&&official?'<a class="btn green" href="'+esc(official)+'" target="_blank" rel="noopener">官网</a>':'')+'</div></article>'}h+='</div></section>'}}$('main').innerHTML=h}
function download(i){const e=ENTRIES[i];if(e)location.href='/'+e.path.split('/').map(encodeURIComponent).join('/')}
function renderAdmin(){let h='<div class="hero"><div><h1>管理后台</h1><p>只有管理员可以修改文件元数据、官网地址和账户。</p></div><button class="btn" onclick="goHome()">返回软件库</button></div><div class="admin"><nav class="admin-nav"><button class="'+(adminPage==='files'?'active':'')+'" onclick="adminPage=\'files\';renderAdmin()">文件与地址</button><button class="'+(adminPage==='users'?'active':'')+'" onclick="adminPage=\'users\';renderAdmin()">用户管理</button><button class="'+(adminPage==='fetch'?'active':'')+'" onclick="adminPage=\'fetch\';renderAdmin()">远程下载</button><button class="'+(adminPage==='system'?'active':'')+'" onclick="adminPage=\'system\';renderAdmin()">系统</button></nav><section class="panel">'+(adminPage==='files'?filesPanel():adminPage==='users'?usersPanel():adminPage==='fetch'?fetchPanel():systemPanel())+'</section></div>';$('main').innerHTML=h;if(adminPage==='users')loadUsers();if(adminPage==='fetch')pollFetch()}
function filesPanel(){return '<h2>文件与地址</h2><div class="hint">默认显示真实文件名。版本不再自动猜测；管理员可以手动填写。官网地址和实际下载地址分开维护。</div><div class="toolbar"><input id="af" placeholder="搜索文件名..." oninput="renderFileRows()"><select id="ac" onchange="renderFileRows()"><option value="">全部分类</option>'+Object.keys(CATS).map(x=>'<option>'+esc(x)+'</option>').join('')+'</select></div><div class="table" id="fileRows"></div>'}
function renderFileRows(){let f=($('af')?.value||'').toLowerCase(),c=$('ac')?.value||'';let list=ENTRIES.map((e,i)=>({e,i})).filter(x=>(!f||x.e.filename.toLowerCase().includes(f))&&(!c||x.e.category===c));let h='<div class="row head"><div>文件</div><div>官网 / 下载地址</div><div>操作</div></div>';for(const {e,i} of list){h+='<div class="row"><div><b style="font-size:11px;word-break:break-all">'+esc(e.filename)+'</b><div class="muted" style="font-size:9px">'+esc(e.category)+' · '+esc(e.sizeText)+'</div></div><div><input id="u'+i+'" style="width:100%" value="'+esc(e.customOfficial||'')+'" placeholder="官方实际下载地址"><div style="margin-top:4px"><input id="o'+i+'" style="width:100%" value="'+esc(e.official||'')+'" placeholder="官网地址"></div></div><div><button class="btn primary" onclick="editFile('+i+')">编辑</button></div></div>'} $('fileRows').innerHTML=h||'<div class="empty">没有匹配文件</div>'}
function editFile(i){const e=ENTRIES[i];$('modal').innerHTML='<div class="modal-mask"><div class="modal"><h2>编辑文件</h2><div class="edit"><label class="full">文件显示名称<input id="mname" value="'+esc(e.displayName||e.filename)+'"></label><label>版本<input id="mver" value="'+esc(e.version||'')+'" placeholder="留空表示不显示"></label><label>分类<select id="mcat">'+Object.keys(CATS).map(x=>'<option '+(x===e.category?'selected':'')+'>'+esc(x)+'</option>').join('')+'<option>其他</option></select></label><label class="full">官网地址<input id="moff" value="'+esc(e.official||'')+'"></label><label class="full">官方下载地址（下载留存用）<input id="mdown" value="'+esc(e.customOfficial||'')+'"></label><label class="full">描述<input id="mdesc" value="'+esc(e.desc||'')+'"></label></div><div class="modal-actions"><button class="btn" onclick="closeModal()">取消</button><button class="btn primary" onclick="saveFile('+i+')">保存</button></div></div></div>'}
async function saveFile(i){const e=ENTRIES[i],r=await api('/api/admin/software',{method:'PUT',body:{path:e.path,displayName:$('mname').value,version:$('mver').value,category:$('mcat').value,official:$('moff').value,customOfficial:$('mdown').value,desc:$('mdesc').value,showOfficial:!!$('moff').value}});if(r.success){Object.assign(e,{displayName:$('mname').value,version:$('mver').value,category:$('mcat').value,official:$('moff').value,customOfficial:$('mdown').value,desc:$('mdesc').value,showOfficial:!!$('moff').value});closeModal();renderAdmin();toast('已保存')}else toast(r.error||'保存失败')}
function closeModal(){$('modal').innerHTML=''}
function usersPanel(){return '<h2>用户管理</h2><div class="hint">管理员可以创建普通用户或管理员。普通用户可以上传文件，但不能修改软件信息。</div><div class="toolbar"><input id="nu" placeholder="用户名"><input id="np" type="password" placeholder="密码"><select id="nr"><option value="user">普通用户</option><option value="admin">管理员</option></select><button class="btn primary" onclick="addUser()">添加账户</button></div><div id="users">加载中...</div>'}
async function loadUsers(){const r=await api('/api/users');if(!r.success){$('users').textContent=r.error||'加载失败';return}let h='';for(const u of r.users)h+='<div class="user-row"><div class="un">'+esc(u.username)+'<div class="muted" style="font-size:9px">创建于 '+esc(u.created||'-')+'</div></div><span class="role '+u.role+'">'+(u.role==='admin'?'管理员':'普通用户')+'</span>'+(u.username!==SESSION.username?'<button class="btn danger" onclick="delUser('+js(u.username)+')">删除</button>':'');h+='</div>';$('users').innerHTML=h||'<div class="empty">暂无用户</div>'}
async function addUser(){let u=$('nu').value.trim(),p=$('np').value,r=$('nr').value;if(!u||!p)return toast('请填写用户名和密码');let x=await api('/api/users',{method:'POST',body:{username:u,password:p,role:r}});toast(x.success?'用户已添加':x.error||'添加失败');if(x.success){$('nu').value='';$('np').value='';loadUsers()}}
async function delUser(u){if(!confirm('确认删除 '+u+'？'))return;let r=await api('/api/users/'+encodeURIComponent(u),{method:'DELETE'});toast(r.success?'已删除':r.error||'删除失败');if(r.success)loadUsers()}
function fetchPanel(){return '<h2>远程下载入库</h2><div class="hint">管理员输入官方下载地址，服务器下载后留存在上传目录并自动加入软件库。下载地址与官网地址分开保存。</div><div class="toolbar"><input id="fu" style="flex:1" placeholder="https://example.com/file.iso"><input id="fn" placeholder="保存文件名（可选）"><button class="btn primary" id="fb" onclick="startFetch()">开始下载</button></div><div id="fs" class="muted" style="font-size:11px"></div>'}
async function startFetch(){let u=$('fu').value.trim(),n=$('fn').value.trim();if(!u)return toast('请输入下载地址');let r=await api('/api/admin/fetch-url',{method:'POST',body:{url:u,name:n}});toast(r.success?'下载已开始':r.error||'启动失败');if(r.success)pollFetch()}
async function pollFetch(){if(polling)return;polling=true;try{while(adminPage==='fetch'){let r=await api('/api/fetch-status');if($('fs'))$('fs').textContent=r.message||'';if(!r.active){if((r.message||'').startsWith('完成')){await loadData();toast('文件已入库')}break}await new Promise(x=>setTimeout(x,1200))}}finally{polling=false}}
function systemPanel(){return '<h2>系统</h2><div class="hint">重新扫描软件库目录；扫描不会修改管理员手动维护的配置。</div><button class="btn primary" onclick="rescan()">重新扫描</button>'}
async function rescan(){let r=await api('/api/rescan',{method:'POST'});toast(r.success?'扫描已启动':r.error||'失败');if(r.success)setTimeout(()=>location.reload(),2500)}
function showLogin(){const first=!HAS_USERS;$('modal').innerHTML='<div class="modal-mask"><div class="modal" style="max-width:380px"><h2>'+(first?'首次创建管理员':'登录软件库')+'</h2><p class="muted" style="font-size:11px">'+(first?'首次使用请创建管理员账户。':'请输入账户和密码。')+'</p><div class="edit"><label class="full">用户名<input id="lu" autocomplete="username"></label><label class="full">密码<input id="lp" type="password" autocomplete="current-password"></label></div><div id="le" style="color:var(--red);font-size:11px;margin-top:8px"></div><div class="modal-actions"><button class="btn" onclick="closeModal()">取消</button><button class="btn primary" onclick="login('+(first?'true':'false')+')">'+(first?'创建并登录':'登录')+'</button></div></div></div>'}
async function login(first){let u=$('lu').value.trim(),p=$('lp').value,r=await api(first?'/api/register':'/api/login',{method:'POST',body:{username:u,password:p}});if(r.success){SESSION={token:r.session,username:r.username,role:r.role};document.cookie='session='+r.session+'; Max-Age=604800; Path=/; SameSite=Lax';closeModal();render()}else $('le').textContent=r.error||'操作失败'}
async function logout(){await api('/api/logout',{method:'POST'});document.cookie='session=; Max-Age=0; Path=/';SESSION=null;goHome()}
function doUpload(){if(!SESSION)return showLogin();$('modal').innerHTML='<div class="modal-mask"><div class="modal"><h2>上传文件</h2><div id="drop" style="border:2px dashed var(--line);border-radius:10px;padding:35px;text-align:center;color:var(--muted);cursor:pointer">选择文件或拖到这里<br><small>最大 500MB，文件名保持原样</small></div><input id="fi" type="file" hidden><div class="progress"><i id="pf"></i></div><div id="us" class="muted" style="font-size:11px;margin-top:6px"></div><div class="modal-actions"><button class="btn" onclick="closeModal()">关闭</button></div></div></div>';let d=$('drop'),f=$('fi');d.onclick=()=>f.click();f.onchange=()=>f.files[0]&&upload(f.files[0]);d.ondragover=e=>e.preventDefault();d.ondrop=e=>{e.preventDefault();e.dataTransfer.files[0]&&upload(e.dataTransfer.files[0])}}
function upload(file){if(file.size>500*1024*1024)return toast('文件超过 500MB');let fd=new FormData();fd.append('file',file);let x=new XMLHttpRequest();x.open('POST','/api/upload');if(SESSION)x.setRequestHeader('X-Session',SESSION.token);x.upload.onprogress=e=>{if(e.lengthComputable){let p=Math.round(e.loaded/e.total*100);$('pf').style.width=p+'%';$('us').textContent='上传中 '+p+'%'}};x.onload=()=>{let r={};try{r=JSON.parse(x.responseText)}catch(e){}if(r.success){$('us').textContent='上传成功，正在更新...';setTimeout(()=>location.reload(),2200)}else toast(r.error||'上传失败')};x.onerror=()=>toast('上传失败');x.send(fd)}
async function loadData(){let r=await fetch('/api/software');if(r.ok){let d=await r.json();if(d.success)ENTRIES=d.data}}
async function init(){let t=cookie('session');if(t){let r=await api('/api/session');if(r.success)SESSION={token:t,username:r.username,role:r.role}}render();if(!SESSION&&!HAS_USERS)showLogin();if(page==='admin'&&adminPage==='files')setTimeout(renderFileRows,0)}
const _oldRenderAdmin=renderAdmin;renderAdmin=function(){_oldRenderAdmin();if(adminPage==='files')setTimeout(renderFileRows,0)};init();
</script></body></html>'''
    return html_page


app.generate_html = generate_html_v7


def main():
    os.makedirs(app.DATA_DIR, exist_ok=True)
    os.makedirs(app.UPLOAD_DIR, exist_ok=True)
    import argparse
    p=argparse.ArgumentParser(description='Software Library Manager v7')
    p.add_argument('--no-scan',action='store_true')
    p.add_argument('--scan-only',action='store_true')
    p.add_argument('--watch',action='store_true')
    p.add_argument('--port',type=int,default=app.PORT)
    a=p.parse_args()
    if not a.no_scan:
        app.refresh_library()
    else:
        with open(app.HTML_FILE,'w',encoding='utf-8') as f:f.write(generate_html_v7())
    if a.scan_only:return
    if a.watch:
        import threading,time
        threading.Thread(target=app.watch_loop,args=(app.WATCH_INTERVAL,),daemon=True).start()
    app.run_server(a.port)

if __name__=='__main__':main()
