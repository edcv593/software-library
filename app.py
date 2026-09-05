#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Software Library Manager v8
===========================
Standalone final version: scanner, responsive UI, authentication, admin panel,
user management, upload, per-file official download URL and remote retention.

Environment variables:
  LIB_ROOT_DIR       Root directory to scan (default: /data)
  LIB_PORT           Web server port (default: 8899)
  LIB_DATA_DIR       Persistent application data (default: /app/data)
  LIB_WATCH_INTERVAL Auto-rescan interval in seconds (default: 3600)
"""
import os
import re
import json
import time
import uuid
import hashlib
import threading
import http.server
import socketserver
import urllib.parse
import shutil
import requests
from datetime import datetime

ROOT_DIR = os.environ.get("LIB_ROOT_DIR", "/data")
PORT = int(os.environ.get("LIB_PORT", "8899"))
DATA_DIR = os.environ.get("LIB_DATA_DIR", "/app/data")
WATCH_INTERVAL = int(os.environ.get("LIB_WATCH_INTERVAL", "3600"))

HTML_FILE = os.path.join(DATA_DIR, "index.html")
SCAN_FILE = os.path.join(DATA_DIR, "scan_result.json")
CONFIG_FILE = os.path.join(DATA_DIR, "config.json")
USERS_FILE = os.path.join(DATA_DIR, "users.json")
UPLOAD_DIR = os.path.join(ROOT_DIR, "uploads")
LOG_DIR = os.path.join(DATA_DIR, "logs")
DOWNLOAD_CACHE = os.path.join(DATA_DIR, "download_cache")

SUPPORTED_EXTENSIONS = {
    ".exe": "EXE", ".msi": "MSI", ".iso": "ISO", ".img": "IMG",
    ".zip": "ZIP", ".7z": "7Z", ".rar": "RAR", ".gz": "GZ",
    ".esd": "ESD", ".tar.xz": "TAR.XZ", ".tar.gz": "TAR.GZ",
    ".apk": "APK", ".dmg": "DMG", ".pkg": "PKG",
    ".deb": "DEB", ".rpm": "RPM",
    ".vmdk": "VMDK", ".ova": "OVA", ".ovf": "OVF",
    ".vdi": "VDI", ".qcow2": "QCOW2", ".wim": "WIM",
}

SKIP_DIRS = {"logs", "log", "工作文件", "文档", ".workbuddy-ai", "$RECYCLE.BIN",
             "System Volume Information", "@Recycle", ".zsshare_trash", "docker",
             "tmp", "temp", "cache", "__pycache__", "node_modules", "uploads"}
SKIP_FILES = {"README.md", "index.html", "software_library.json",
              "update_library.py", "app.py", "deploy.sh", "启动软件库.bat",
              "config.json", "scan_result.json", "users.json"}

MAX_UPLOAD_SIZE = 500 * 1024 * 1024
MAX_DOWNLOAD_SIZE = 2 * 1024 * 1024 * 1024

SOFTWARE_DB = {
    "vmware": {"name":"VMware Workstation","category":"虚拟化","icon":"vmware","desc":"VMware 虚拟机工作站","official":"https://www.vmware.com"},
    "esxi": {"name":"VMware ESXi","category":"虚拟化","icon":"vmware","desc":"VMware ESXi 裸机虚拟化系统","official":"https://www.vmware.com/products/esxi-and-esx.html"},
    "proxmox": {"name":"Proxmox VE","category":"虚拟化","icon":"server","desc":"开源虚拟化管理平台 (KVM/LXC)","official":"https://www.proxmox.com"},
    "truenas": {"name":"TrueNAS SCALE","category":"NAS/存储","icon":"nas","desc":"开源 NAS 操作系统","official":"https://www.truenas.com"},
    "fnos": {"name":"飞牛 OS (fnOS)","category":"NAS/存储","icon":"nas","desc":"飞牛私有云 NAS 操作系统","official":"https://www.fnos.com"},
    "windows": {"name":"Windows","category":"操作系统","icon":"windows","desc":"Windows 系统镜像","official":"https://www.microsoft.com/windows"},
    "cn_windows": {"name":"Windows","category":"操作系统","icon":"windows","desc":"Windows 原版镜像","official":"https://www.microsoft.com"},
    "edrv8": {"name":"EasyDrv 驱动包","category":"驱动","icon":"driver","desc":"Windows 驱动自动安装包","official":""},
    "wepe": {"name":"WePE 微PE","category":"PE/维护","icon":"wrench","desc":"微PE工具箱，装机维护利器","official":"https://www.wepe.com.cn"},
    "centos": {"name":"CentOS","category":"操作系统","icon":"linux","desc":"CentOS Linux 服务器系统","official":"https://www.centos.org"},
    "debian": {"name":"Debian","category":"操作系统","icon":"linux","desc":"Debian GNU/Linux 系统","official":"https://www.debian.org"},
    "ubuntu": {"name":"Ubuntu Server","category":"操作系统","icon":"linux","desc":"Ubuntu Server 服务器系统","official":"https://ubuntu.com"},
    "openwrt": {"name":"OpenWrt","category":"路由器/软路由","icon":"router","desc":"OpenWrt 软路由固件","official":"https://openwrt.org"},
    "istoreos": {"name":"iStoreOS","category":"路由器/软路由","icon":"router","desc":"iStoreOS 软路由系统","official":"https://www.istoreos.com"},
    "ikuai": {"name":"iKuai 爱快","category":"路由器/软路由","icon":"router","desc":"爱快流控路由系统","official":"https://www.ikuai8.com"},
    "immortalwrt": {"name":"ImmortalWrt","category":"路由器/软路由","icon":"router","desc":"ImmortalWrt 软路由系统","official":"https://immortalwrt.org"},
    "sql server": {"name":"SQL Server","category":"数据库","icon":"database","desc":"Microsoft SQL Server","official":"https://www.microsoft.com/sql-server"},
    "mysql": {"name":"MySQL","category":"数据库","icon":"database","desc":"MySQL 数据库","official":"https://www.mysql.com"},
    "redis": {"name":"Redis","category":"数据库","icon":"database","desc":"Redis 内存数据库","official":"https://redis.io"},
    "office": {"name":"Microsoft Office","category":"办公软件","icon":"office","desc":"Microsoft Office 办公套件","official":"https://www.microsoft.com/microsoft-365"},
    "adobe": {"name":"Adobe","category":"设计/创意","icon":"adobe","desc":"Adobe 创意套件","official":"https://www.adobe.com"},
    "acrobat": {"name":"Adobe Acrobat","category":"设计/创意","icon":"pdf","desc":"Adobe Acrobat PDF 编辑器","official":"https://www.adobe.com/acrobat.html"},
    "wps": {"name":"WPS Office","category":"办公软件","icon":"office","desc":"WPS Office 办公套件","official":"https://www.wps.cn"},
    "git": {"name":"Git","category":"开发工具","icon":"code","desc":"Git 版本控制工具","official":"https://git-scm.com"},
    "jdk": {"name":"JDK (Java)","category":"开发工具","icon":"java","desc":"Java Development Kit","official":"https://www.oracle.com/java/technologies/downloads/"},
    "python": {"name":"Python","category":"开发工具","icon":"python","desc":"Python 编程语言","official":"https://www.python.org"},
    "pycharm": {"name":"PyCharm","category":"开发工具","icon":"code","desc":"PyCharm Python IDE","official":"https://www.jetbrains.com/pycharm/"},
    "navicat": {"name":"Navicat Premium","category":"数据库","icon":"database","desc":"Navicat 数据库管理工具","official":"https://www.navicat.com"},
    "mobaxterm": {"name":"MobaXterm","category":"开发工具","icon":"terminal","desc":"MobaXterm 终端工具","official":"https://mobaxterm.mobatek.net"},
    "xshell": {"name":"Xshell Plus","category":"开发工具","icon":"terminal","desc":"Xshell 终端模拟器","official":"https://www.xshell.com"},
    "sublime": {"name":"Sublime Text","category":"开发工具","icon":"code","desc":"Sublime Text 代码编辑器","official":"https://www.sublimetext.com"},
    "diskgenius": {"name":"DiskGenius","category":"系统工具","icon":"disk","desc":"DiskGenius 磁盘分区管理","official":"https://www.diskgenius.com"},
    "ultraiso": {"name":"UltraISO","category":"系统工具","icon":"disk","desc":"UltraISO 光盘镜像工具","official":"https://www.ultraiso.com"},
    "winrar": {"name":"WinRAR","category":"系统工具","icon":"archive","desc":"WinRAR 压缩解压工具","official":"https://www.rarlab.com"},
    "rufus": {"name":"Rufus","category":"系统工具","icon":"usb","desc":"Rufus USB 启动盘制作","official":"https://rufus.ie"},
    "balenaetcher": {"name":"balenaEtcher","category":"系统工具","icon":"usb","desc":"balenaEtcher 镜像写入","official":"https://etcher.balena.io"},
    "geek": {"name":"Geek Uninstaller","category":"系统工具","icon":"trash","desc":"Geek 卸载器","official":"https://geekuninstaller.com"},
    "dism": {"name":"Dism++","category":"系统工具","icon":"wrench","desc":"Dism++ Windows 优化工具","official":"http://www.chuyu.me"},
    "startallback": {"name":"StartAllBack","category":"系统工具","icon":"windows","desc":"StartAllBack Win11 开始菜单","official":"https://www.startallback.com"},
    "easybcd": {"name":"EasyBCD","category":"系统工具","icon":"wrench","desc":"EasyBCD 引导管理","official":"https://neosmart.net/EasyBCD/"},
    "clash": {"name":"Clash","category":"网络/代理","icon":"network","desc":"Clash 代理客户端","official":"https://github.com/Dreamacro/clash"},
    "clash.verge": {"name":"Clash Verge","category":"网络/代理","icon":"network","desc":"Clash Verge Rev 代理客户端","official":"https://github.com/clash-verge-rev/clash-verge-rev"},
    "rustdesk": {"name":"RustDesk","category":"远程控制","icon":"remote","desc":"RustDesk 远程桌面","official":"https://rustdesk.com"},
    "chrome": {"name":"Google Chrome","category":"浏览器","icon":"browser","desc":"Google Chrome 浏览器","official":"https://www.google.com/chrome/"},
    "firefox": {"name":"Firefox","category":"浏览器","icon":"browser","desc":"Mozilla Firefox 浏览器","official":"https://www.mozilla.org/firefox/"},
    "wallpaper engine": {"name":"Wallpaper Engine","category":"媒体/娱乐","icon":"media","desc":"Wallpaper Engine 动态壁纸","official":"https://www.wallpaperengine.io"},
    "potplayer": {"name":"PotPlayer","category":"媒体/娱乐","icon":"media","desc":"PotPlayer 视频播放器","official":"https://potplayer.daum.net"},
    "pixpin": {"name":"PixPin","category":"系统工具","icon":"screenshot","desc":"PixPin 截图工具","official":"https://pixpin.cn"},
    "heu": {"name":"HEU KMS Activator","category":"激活工具","icon":"key","desc":"HEU KMS 激活工具","official":"https://github.com/zbezj/HEU_KMS_Activator"},
    "virtio": {"name":"VirtIO 驱动","category":"驱动","icon":"driver","desc":"VirtIO Windows 驱动","official":"https://fedoraproject.org/wiki/Windows_Virtio_Drivers"},
}

CAT_ICON_MAP = {
    "操作系统":"windows","虚拟化":"vmware","NAS/存储":"nas","路由器/软路由":"router",
    "数据库":"database","开发工具":"code","系统工具":"wrench","网络/代理":"network",
    "浏览器":"browser","办公软件":"office","设计/创意":"adobe","媒体/娱乐":"media",
    "远程控制":"remote","激活工具":"key","PE/维护":"wrench","驱动":"driver","其他":"box",
}

SVG_ICONS = {
    "vmware":'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5M2 12l10 5 10-5"/></svg>',
    "server":'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="3" width="20" height="6" rx="1"/><rect x="2" y="15" width="20" height="6" rx="1"/><line x1="6" y1="6" x2="6.01" y2="6"/><line x1="6" y1="18" x2="6.01" y2="18"/></svg>',
    "nas":'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="4" width="18" height="16" rx="2"/><line x1="7" y1="8" x2="7" y2="8"/><line x1="7" y1="12" x2="7" y2="12"/><line x1="7" y1="16" x2="7" y2="16"/><line x1="11" y1="8" x2="17" y2="8"/><line x1="11" y1="12" x2="17" y2="12"/><line x1="11" y1="16" x2="17" y2="16"/></svg>',
    "windows":'<svg viewBox="0 0 24 24" fill="currentColor"><path d="M3 5.5l8.5-1.2v8.2H3V5.5zm0 13l8.5 1.2v-8.2H3v7zm9.5 1.3L21 21V13h-8.5v6.8zm0-15.6V11H21V3l-8.5 1.2z"/></svg>',
    "linux":'<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 2C8 2 7 6 7 9c0 2-2 4-2 7 0 3 3 4 7 4s7-1 7-4c0-3-2-5-2-7 0-3-1-7-5-7zM8 17c1-1 2-1 4-1s3 0 4 1c-1 1-2 1-4 1s-3 0-4-1z"/></svg>',
    "router":'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="8" width="18" height="10" rx="2"/><path d="M7 8l2-4M17 8l-2-4M7 13h.01M11 13h.01M15 13h.01M19 13h.01"/></svg>',
    "database":'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v7c0 2 4 3 8 3s8-1 8-3V5M4 12v7c0 2 4 3 8 3s8-1 8-3v-7"/></svg>',
    "code":'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M8 9l-4 3 4 3M16 9l4 3-4 3M14 5l-4 14"/></svg>',
    "wrench":'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14.7 6.3a5 5 0 0 0-6.4 6.4L3 18l3 3 5.3-5.3a5 5 0 0 0 6.4-6.4L14 12l-2-2 2.7-3.7z"/></svg>',
    "network":'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="6" cy="12" r="3"/><circle cx="18" cy="6" r="3"/><circle cx="18" cy="18" r="3"/><path d="M8.5 10.5l7-3M8.5 13.5l7 3"/></svg>',
    "browser":'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 9h18M7 6.5h.01M10 6.5h.01"/></svg>',
    "office":'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 4l14 3v10l-14 3V4zM9 9v6M13 10v4"/></svg>',
    "adobe":'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 19L10 5l6 14M7 14h6M14 5l6 14"/></svg>',
    "media":'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="5" width="18" height="14" rx="2"/><path d="M10 9l5 3-5 3V9z"/></svg>',
    "remote":'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="5" width="18" height="12" rx="2"/><path d="M8 21h8M12 17v4"/></svg>',
    "key":'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="8" cy="15" r="4"/><path d="M11 12l8-8 2 2-2 2 2 2-2 2-2-2-4 4"/></svg>',
    "driver":'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="4" y="4" width="16" height="16" rx="2"/><path d="M8 8h8M8 12h8M8 16h5"/></svg>',
    "box":'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 7l9-4 9 4-9 4-9-4zM3 7v10l9 4 9-4V7M12 11v10"/></svg>',
    "archive":'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="5" width="18" height="14" rx="2"/><path d="M8 5v4h8V5M10 13h4"/></svg>',
    "usb":'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 3v14M12 7l-3-3M12 7l3-3M8 17l-3 3M16 17l3 3"/><circle cx="8" cy="20" r="1"/><circle cx="16" cy="20" r="1"/></svg>',
    "trash":'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 7h16M9 7V4h6v3M7 7l1 14h8l1-14M10 11v6M14 11v6"/></svg>',
    "disk":'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="3"/></svg>',
    "java":'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M8 18c4 2 8 0 8-2M9 15c-2 2 6 3 7-1M12 3c3 3-2 4 1 6"/></svg>',
    "python":'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 3c-4 0-5 2-5 5v3h6v2H7c-3 0-4 2-4 4s1 4 4 4h3v-3H7M12 3v3h3c3 0 4 2 4 4v4c0 3-2 4-5 4h-2v3h3c4 0 5-2 5-5v-6c0-4-2-7-6-7h-2z"/></svg>',
    "pdf":'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 3h9l4 4v14H6zM15 3v5h5"/><path d="M8 17h2M8 13h6"/></svg>',
    "screenshot":'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="4" y="4" width="16" height="16" rx="2"/><circle cx="12" cy="12" r="3"/></svg>',
}

def load_json(path, default):
    try:
        with open(path,"r",encoding="utf-8") as f:return json.load(f)
    except Exception:return default

def save_json(path,data):
    os.makedirs(os.path.dirname(path),exist_ok=True);tmp=path+'.tmp'
    with open(tmp,'w',encoding='utf-8') as f:json.dump(data,f,ensure_ascii=False,indent=2)
    os.replace(tmp,path)

def default_config():return {"software":{}}
def load_users():return load_json(USERS_FILE,{"users":[]})
def has_users():return bool(load_users().get("users"))
def hash_password(password,salt=None):
    salt=salt or os.urandom(16).hex();return salt,hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(salt),180000).hex()
def verify_password(password,user):
    try:return hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(user['salt']),180000).hex()==user['password']
    except Exception:return False

def format_size(size):
    size=float(size)
    for u in ('B','KB','MB','GB','TB'):
        if size<1024:return f'{int(size)} {u}' if u=='B' else f'{size:.1f} {u}'
        size/=1024
    return f'{size:.1f} PB'

def get_file_type(filename):
    low=filename.lower()
    for ext,t in sorted(SUPPORTED_EXTENSIONS.items(),key=lambda x:-len(x[0])):
        if low.endswith(ext):return t
    return 'FILE'

def sanitize_filename(name):
    name=os.path.basename(urllib.parse.unquote(str(name or ''))).strip()
    name=re.sub(r'[\\/:*?"<>|\x00-\x1f]','_',name)
    return name or 'download.bin'

def identify_file(filename):
    low=filename.lower().replace('_',' ').replace('-',' ')
    for key,cfg in SOFTWARE_DB.items():
        if key in low:return key,cfg
    stem=os.path.splitext(filename)[0]
    return stem.lower(),{"name":stem,"category":"其他","icon":"box","desc":"","official":""}

def build_entry_list():
    result=[]
    if not os.path.isdir(ROOT_DIR):return result
    for root,dirs,files in os.walk(ROOT_DIR):
        dirs[:]=[d for d in dirs if d not in SKIP_DIRS]
        for fn in files:
            if fn in SKIP_FILES or fn.startswith('.') :continue
            path=os.path.join(root,fn)
            try:
                st=os.stat(path)
                rel=os.path.relpath(path,ROOT_DIR).replace('\\','/')
                result.append({"filename":fn,"path":rel,"size":st.st_size,"sizeText":format_size(st.st_size),"fileType":get_file_type(fn),"date":datetime.fromtimestamp(st.st_mtime).strftime('%Y-%m-%d %H:%M')})
            except OSError:continue
    result.sort(key=lambda x:x['filename'].lower())
    return result

def build_software_list():
    entries=build_entry_list();cfg=load_json(CONFIG_FILE,default_config());overrides=cfg.get('software',{}) or {};grouped={}
    for item in entries:
        key,base=identify_file(item['filename']);x=overrides.get(key,{})
        if key not in grouped:
            grouped[key]={"name":x.get("displayName") or base["name"],"category":x.get("category") or base["category"],"icon":x.get("icon") or base["icon"],"desc":x.get("desc") or base["desc"],"official":x.get("official") or x.get("customOfficial") or base.get("official",""),"showOfficial":x.get("showOfficial",bool(x.get("official") or base.get("official"))),"versions":[]}
        vc=(x.get('versions',{}) or {}).get(item['path'],{})
        v=dict(item);v['displayName']=item['filename'];v['downloadUrl']=vc.get('downloadUrl','') if isinstance(vc,dict) else ''
        grouped[key]['versions'].append(v)
    for key,x in overrides.items():
        if key not in grouped and isinstance(x,dict):
            grouped[key]={"name":x.get("displayName") or key,"category":x.get("category","其他"),"icon":x.get("icon","box"),"desc":x.get("desc",""),"official":x.get("official") or x.get("customOfficial",""),"showOfficial":x.get("showOfficial",True),"versions":[]}
    out=list(grouped.values());out.sort(key=lambda x:x['name'].lower())
    for x in out:x['versions'].sort(key=lambda v:v['filename'].lower(),reverse=True)
    return out

def esc(v):return htmlmod.escape(str(v or ''),quote=True)
def js(v):return json.dumps(v,ensure_ascii=False).replace('</','<\\/')

def generate_html():
    data=build_software_list();total=sum(len(x['versions']) for x in data);cats=sorted({x['category'] for x in data});icons=dict(SVG_ICONS)
    data_json=json.dumps(data,ensure_ascii=False);cats_json=json.dumps(cats,ensure_ascii=False);icons_json=json.dumps(icons,ensure_ascii=False)
    return '''<!doctype html><html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"><title>软件库 | Software Library</title><style>
:root{--bg:#f5f6f8;--card:#fff;--text:#1a1d28;--muted:#6b7280;--accent:#4f7cff;--line:#e0e3eb;--green:#16a34a;--red:#dc2626;--orange:#d97706;--shadow:0 3px 16px rgba(0,0,0,.06)}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Microsoft YaHei",sans-serif}.header{position:sticky;top:0;z-index:20;background:#fffffff2;backdrop-filter:blur(16px);border-bottom:1px solid var(--line)}.header-inner{max-width:1450px;margin:auto;padding:10px 16px;display:flex;gap:12px;align-items:center}.logo{font-weight:800;white-space:nowrap}.logo small{display:block;color:var(--muted);font-size:9px;font-weight:500}.search{flex:1;max-width:680px;margin:auto;position:relative}.search input{width:100%;height:38px;border:1px solid var(--line);border-radius:9px;background:#f2f4f7;padding:0 13px;outline:0}.search input:focus{background:#fff;border-color:var(--accent)}button,input,select{font:inherit}.btn{border:1px solid var(--line);background:#fff;border-radius:8px;padding:7px 10px;font-size:12px;cursor:pointer}.btn.primary{background:var(--accent);border-color:var(--accent);color:#fff}.btn.danger{color:var(--red)}.actions{display:flex;gap:7px;align-items:center}.user{font-size:11px;color:var(--muted)}main{max-width:1450px;margin:auto;padding:22px 16px 45px}.hero{display:flex;justify-content:space-between;align-items:end}.hero h1{font-size:23px;margin:0}.hero p{font-size:11px;color:var(--muted);margin:3px 0}.filter{display:flex;gap:8px;margin:18px 0}.filter select{border:1px solid var(--line);border-radius:8px;background:#fff;padding:8px 12px;min-width:210px}.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(285px,1fr));gap:11px}.card{background:#fff;border:1px solid var(--line);border-radius:13px;padding:13px;box-shadow:var(--shadow)}.card-head{display:flex;gap:10px}.icon{width:38px;height:38px;flex:none;border-radius:9px;background:#eef3ff;color:var(--accent);display:flex;align-items:center;justify-content:center}.icon svg{width:21px;height:21px}.card h2{font-size:14px;margin:0;word-break:break-word}.desc{font-size:10px;color:var(--muted);margin-top:3px}.tag{display:inline-block;margin-top:5px;padding:2px 7px;border-radius:5px;background:#eef3ff;color:var(--accent);font-size:9px}.official{margin-top:8px}.official a{font-size:10px;color:var(--accent);text-decoration:none}.file{margin-top:10px;padding-top:9px;border-top:1px solid #f0f1f3}.filename{font-size:11px;word-break:break-all}.meta{font-size:9px;color:var(--muted);margin:3px 0 6px}.links{display:flex;gap:5px;flex-wrap:wrap}.links a{font-size:10px;text-decoration:none;border:1px solid var(--line);border-radius:6px;padding:4px 7px;color:var(--text)}.links a.blue{color:var(--accent)}.empty{text-align:center;color:var(--muted);padding:70px}.modal-mask{display:none;position:fixed;inset:0;background:rgba(15,23,42,.48);z-index:100;align-items:center;justify-content:center;padding:15px}.modal{background:#fff;border-radius:14px;width:min(900px,100%);max-height:90vh;overflow:auto;padding:18px}.modal h2{margin:0 0 14px;font-size:17px}.form{display:grid;grid-template-columns:1fr 1fr;gap:9px}.form .full{grid-column:1/-1}.form label{font-size:10px;color:var(--muted)}.form input,.form select{width:100%;margin-top:4px;padding:8px;border:1px solid var(--line);border-radius:7px;outline:0}.admin-sw{padding:12px 0;border-bottom:1px solid var(--line)}.admin-sw:last-child{border:0}.admin-file{display:grid;grid-template-columns:1fr minmax(260px,2fr) auto auto;gap:6px;align-items:center;margin-top:7px}.small{font-size:10px;color:var(--muted);word-break:break-all}.users{margin-bottom:15px}.userrow{display:flex;gap:8px;align-items:center;padding:7px 0;border-bottom:1px solid #f0f1f3;font-size:11px}.userrow b{flex:1}.role{font-size:9px;color:var(--accent)}.toast{position:fixed;bottom:22px;left:50%;transform:translateX(-50%);background:#111827;color:#fff;padding:9px 14px;border-radius:8px;font-size:11px;display:none;z-index:200}@media(max-width:700px){.header-inner{flex-wrap:wrap}.search{order:3;flex-basis:100%}.user{display:none}.grid{grid-template-columns:1fr}.admin-file{grid-template-columns:1fr}.form{grid-template-columns:1fr}.form .full{grid-column:auto}.modal{padding:13px}}
</style></head><body><header class="header"><div class="header-inner"><div class="logo">📦 软件库<small>Software Library</small></div><div class="search"><input id="q" placeholder="搜索软件、文件名…" oninput="render()"></div><div class="actions"><span id="who" class="user"></span><button id="loginBtn" class="btn primary" onclick="openLogin()">登录</button><button id="uploadBtn" class="btn" style="display:none" onclick="openUpload()">上传</button><button id="adminBtn" class="btn" style="display:none" onclick="openAdmin()">管理后台</button></div></div></header><main><div class="hero"><div><h1>软件库</h1><p id="stats"></p></div></div><div class="filter"><select id="cat" onchange="render()"><option value="">全部分类</option></select></div><div id="list" class="grid"></div></main><div id="mask" class="modal-mask"><div id="modal" class="modal"></div></div><div id="toast" class="toast"></div><script>const DATA='''+data_json+''';const ICONS='''+icons_json+''';let SESSION=null;const esc=s=>String(s??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));const api=async(u,o={})=>{let r=await fetch(u,o);return r.json()};const post=(u,d)=>api(u,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(d)});function toast(s){let e=document.getElementById('toast');e.textContent=s;e.style.display='block';setTimeout(()=>e.style.display='none',2400)}function openM(x){document.getElementById('modal').innerHTML=x;document.getElementById('mask').style.display='flex'}function closeM(){document.getElementById('mask').style.display='none'}function render(){let q=document.getElementById('q').value.toLowerCase(),c=document.getElementById('cat').value;let a=DATA.filter(x=>(!c||x.category===c)&&(!q||(x.name+' '+x.desc+' '+x.versions.map(v=>v.filename).join(' ')).toLowerCase().includes(q)));document.getElementById('stats').textContent=`${a.length} 个软件 · ${a.reduce((n,x)=>n+x.versions.length,0)} 个文件`;document.getElementById('list').innerHTML=a.length?a.map(x=>`<article class="card"><div class="card-head"><div class="icon">${ICONS[x.icon]||ICONS.box}</div><div><h2>${esc(x.name)}</h2><span class="tag">${esc(x.category)}</span><div class="desc">${esc(x.desc)}</div></div></div>${x.official&&x.showOfficial?`<div class="official"><a target="_blank" href="${esc(x.official)}">访问官网 ↗</a></div>`:''}${x.versions.map(v=>`<div class="file"><div class="filename">${esc(v.filename)}</div><div class="meta">${esc(v.fileType)} · ${esc(v.sizeText)} · ${esc(v.date)}</div><div class="links"><a href="/download/${encodeURIComponent(v.path).replaceAll('%2F','/')}">下载</a>${v.downloadUrl?`<a class="blue" target="_blank" href="${esc(v.downloadUrl)}">官方直链</a>`:''}</div></div>`).join('')}</article>`).join(''):'<div class="empty">没有找到匹配的文件</div>'}function openLogin(){openM(`<h2>${HAS_USERS?'登录':'首次使用：创建管理员'}</h2><div class="form"><label>用户名<input id="un" autocomplete="username"></label><label>密码<input id="pw" type="password" autocomplete="current-password"></label></div><div style="margin-top:14px;display:flex;justify-content:flex-end;gap:7px"><button class="btn" onclick="closeM()">取消</button><button class="btn primary" onclick="login()">${HAS_USERS?'登录':'创建管理员'}</button></div>`)}async function login(){let r=await post('/api/login',{username:document.getElementById('un').value,password:document.getElementById('pw').value});if(r.success){closeM();location.reload()}else toast(r.error||'操作失败')}async function logout(){await post('/api/logout',{});location.reload()}function openUpload(){openM(`<h2>上传文件</h2><input id="file" type="file"><div style="margin-top:14px;display:flex;justify-content:flex-end;gap:7px"><button class="btn" onclick="closeM()">取消</button><button class="btn primary" onclick="upload()">开始上传</button></div>`)}async function upload(){let f=document.getElementById('file').files[0];if(!f)return toast('请选择文件');if(f.size>''' + str(MAX_UPLOAD_SIZE) + ''')return toast('文件超过500MB限制');let fd=new FormData();fd.append('file',f);let r=await fetch('/api/upload',{method:'POST',body:fd});let d=await r.json();toast(d.success?'上传成功':d.error);if(d.success)setTimeout(()=>location.reload(),800)}async function openAdmin(){let r=await api('/api/admin/data');if(!r.success)return toast(r.error);let users=r.users;openM(`<h2>管理后台</h2><h3>添加账户</h3><div class="form"><label>用户名<input id="nu"></label><label>密码<input id="np" type="password"></label><label>角色<select id="nr"><option value="user">普通用户</option><option value="admin">管理员</option></select></label></div><div style="margin:8px 0"><button class="btn primary" onclick="addUser()">添加账户</button></div><div class="users"><h3>账户</h3>${users.map(u=>`<div class="userrow"><b>${esc(u.username)}</b><span class="role">${esc(u.role)}</span>${!(u.role==='admin'&&users.filter(x=>x.role==='admin').length<=1)?`<button class="btn danger" onclick="delUser(${JSON.stringify(u.username)})">删除</button>`:''}</div>`).join('')}</div><h3>软件及文件配置</h3>${r.software.map(x=>`<div class="admin-sw"><b>${esc(x.name)}</b><div class="small">官网地址</div><input id="off-${CSS.escape(x.key||x.name)}" value="${esc(x.official)}" style="width:100%;margin-top:4px;padding:7px;border:1px solid #e0e3eb;border-radius:7px"><button class="btn" style="margin-top:5px" onclick="saveOfficial(${JSON.stringify(x.key||x.name)})">保存官网</button>${x.versions.map(v=>`<div class="admin-file"><span class="small">${esc(v.filename)}</span><input id="url-${btoa(unescape(encodeURIComponent(x.name+'|'+v.path))).replace(/=/g,'')}" value="${esc(v.downloadUrl)}" placeholder="该文件官方下载地址"><button class="btn" onclick="saveUrl(${JSON.stringify(x.key||x.name)},${JSON.stringify(v.path)})">保存</button><button class="btn" onclick="fetchFile(${JSON.stringify(x.key||x.name)},${JSON.stringify(v.path)})">下载留存</button></div>`).join('')}</div>`).join('')}<div style="margin-top:15px;text-align:right"><button class="btn" onclick="closeM()">关闭</button></div>`)}function keyid(k,p){return 'url-'+btoa(unescape(encodeURIComponent(k+'|'+p))).replace(/=/g,'')}async function addUser(){let r=await post('/api/admin/user',{username:document.getElementById('nu').value,password:document.getElementById('np').value,role:document.getElementById('nr').value});toast(r.success?'账户已添加':r.error);if(r.success)openAdmin()}async function delUser(u){let r=await post('/api/admin/user/delete',{username:u});toast(r.success?'账户已删除':r.error);if(r.success)openAdmin()}async function saveOfficial(k){let e=document.getElementById('off-'+CSS.escape(k)),r=await post('/api/admin/software',{name:k,official:e.value});toast(r.success?'官网地址已保存':r.error)}async function saveUrl(k,p){let e=document.getElementById(keyid(k,p)),r=await post('/api/admin/software',{name:k,versionPath:p,downloadUrl:e.value});toast(r.success?'官方下载地址已保存':r.error)}async function fetchFile(k,p){let e=document.getElementById(keyid(k,p));if(!e.value)return toast('请先填写官方下载地址');let r=await post('/api/admin/fetch',{name:k,path:p,url:e.value});toast(r.success?'已开始下载留存':r.error)}async function init(){let r=await api('/api/session');if(r.success)SESSION={username:r.username,role:r.role};let cats='''+cats_json+''';document.getElementById('cat').innerHTML='<option value="">全部分类</option>'+cats.map(x=>`<option>${esc(x)}</option>`).join('');document.getElementById('loginBtn').textContent=SESSION?'退出':'登录';document.getElementById('loginBtn').onclick=SESSION?logout:openLogin;if(SESSION){document.getElementById('who').textContent=SESSION.username;document.getElementById('uploadBtn').style.display='block';if(SESSION.role==='admin')document.getElementById('adminBtn').style.display='block'}else if(!HAS_USERS){openLogin()}render()}const HAS_USERS=''' + ('true' if has_users() else 'false') + ''';init();</script></body></html>'''
    return cssfix_html()

def cssfix_html():
    # generate_html is already a complete document; retained as a named hook for compatibility.
    return _generated_html

# The frontend above is produced by generate_html; this assignment keeps the source compact
# while avoiding any external template dependency.
_generated_html = None

def regenerate_html():
    global _generated_html
    # generate_html returns a complete page except for the compatibility hook.
    # Build it with a temporary direct implementation below.
    data=build_software_list();total=sum(len(x['versions']) for x in data);cats=sorted({x['category'] for x in data});icons=json.dumps(SVG_ICONS,ensure_ascii=False);dj=json.dumps(data,ensure_ascii=False);cj=json.dumps(cats,ensure_ascii=False)
    cards=''.join(f'<article class="card"><div class="card-head"><div class="icon">{SVG_ICONS.get(x["icon"],SVG_ICONS["box"])}</div><div><h2>{esc(x["name"])}</h2><span class="tag">{esc(x["category"])}</span><div class="desc">{esc(x["desc"])}</div></div></div>'+ (f'<div class="official"><a target="_blank" href="{esc(x["official"])}">访问官网 ↗</a></div>' if x.get('official') and x.get('showOfficial') else '') + ''.join(f'<div class="file"><div class="filename">{esc(v["filename"])}</div><div class="meta">{esc(v["fileType"])} · {esc(v["sizeText"])} · {esc(v["date"])}</div><div class="links"><a href="/download/{urllib.parse.quote(v["path"],safe="/")}">下载</a>'+ (f'<a class="blue" target="_blank" href="{esc(v["downloadUrl"])}">官方直链</a>' if v.get('downloadUrl') else '') +'</div></div>' for v in x['versions'])+'</article>' for x in data)
    return f'''<!doctype html><html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"><title>软件库 | Software Library</title><style>{PAGE_CSS}</style></head><body><header class="header"><div class="header-inner"><div class="logo">📦 软件库<small>Software Library v8</small></div><div class="search"><input id="q" placeholder="搜索软件、文件名…" oninput="render()"></div><div class="actions"><span id="who" class="user"></span><button id="loginBtn" class="btn primary">登录</button><button id="uploadBtn" class="btn" style="display:none">上传</button><button id="adminBtn" class="btn" style="display:none">管理后台</button></div></div></header><main><div class="hero"><div><h1>软件库</h1><p id="stats">{len(data)} 个软件 · {total} 个文件</p></div></div><div class="filter"><select id="cat"><option value="">全部分类</option></select></div><div id="list" class="grid">{cards or '<div class="empty">没有找到文件</div>'}</div></main><div id="mask" class="modal-mask"><div id="modal" class="modal"></div></div><div id="toast" class="toast"></div><script>const DATA={dj};const ICONS={icons};const HAS_USERS={'true' if has_users() else 'false'};let SESSION=null;const esc=s=>String(s??'').replace(/[&<>"']/g,m=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[m]));const api=async(u,o={{}})=>(await fetch(u,o)).json();const post=(u,d)=>api(u,{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(d)}});function toast(s){{let e=document.getElementById('toast');e.textContent=s;e.style.display='block';setTimeout(()=>e.style.display='none',2200)}}function openM(x){{document.getElementById('modal').innerHTML=x;document.getElementById('mask').style.display='flex'}}function closeM(){{document.getElementById('mask').style.display='none'}}function render(){{let q=document.getElementById('q').value.toLowerCase(),c=document.getElementById('cat').value;let a=DATA.filter(x=>(!c||x.category===c)&&(!q||(x.name+' '+x.desc+' '+x.versions.map(v=>v.filename).join(' ')).toLowerCase().includes(q)));document.getElementById('stats').textContent=`${{a.length}} 个软件 · ${{a.reduce((n,x)=>n+x.versions.length,0)}} 个文件`;document.getElementById('list').innerHTML=a.map(x=>`<article class="card"><div class="card-head"><div class="icon">${{ICONS[x.icon]||ICONS.box}}</div><div><h2>${{esc(x.name)}}</h2><span class="tag">${{esc(x.category)}}</span><div class="desc">${{esc(x.desc)}}</div></div></div>${{x.official&&x.showOfficial?`<div class="official"><a target="_blank" href="${{esc(x.official)}}">访问官网 ↗</a></div>`:''}}${{x.versions.map(v=>`<div class="file"><div class="filename">${{esc(v.filename)}}</div><div class="meta">${{esc(v.fileType)}} · ${{esc(v.sizeText)}} · ${{esc(v.date)}}</div><div class="links"><a href="/download/${{encodeURIComponent(v.path).replaceAll('%2F','/')}}">下载</a>${{v.downloadUrl?`<a class="blue" target="_blank" href="${{esc(v.downloadUrl)}}">官方直链</a>`:''}}</div></div>`).join('')}}</article>`).join('')||'<div class="empty">没有找到文件</div>'}}function openLogin(){{openM(`<h2>${{HAS_USERS?'登录':'首次使用：创建管理员'}}</h2><div class="form"><label>用户名<input id="un"></label><label>密码<input id="pw" type="password"></label></div><div class="modal-actions"><button class="btn" onclick="closeM()">取消</button><button class="btn primary" onclick="login()">${{HAS_USERS?'登录':'创建管理员'}}</button></div>`)}}async function login(){{let r=await post('/api/login',{{username:document.getElementById('un').value,password:document.getElementById('pw').value}});if(r.success)location.reload();else toast(r.error)}}async function logout(){{await post('/api/logout',{{}});location.reload()}}function openUpload(){{openM(`<h2>上传文件</h2><input id="file" type="file"><div class="modal-actions"><button class="btn" onclick="closeM()">取消</button><button class="btn primary" onclick="upload()">上传</button></div>`)}}async function upload(){{let f=document.getElementById('file').files[0];if(!f)return toast('请选择文件');if(f.size>{MAX_UPLOAD_SIZE})return toast('文件超过500MB限制');let fd=new FormData();fd.append('file',f);let r=await fetch('/api/upload',{{method:'POST',body:fd}});let d=await r.json();toast(d.success?'上传成功':d.error);if(d.success)setTimeout(()=>location.reload(),700)}}function openAdmin(){{api('/api/admin/data').then(r=>{{if(!r.success)return toast(r.error);openM('<h2>管理后台</h2><div class="admin-note">用户管理和软件/文件直链管理请在此处完成。'+r.users.length+' 个账户，'+r.software.length+' 个软件。</div><div class="modal-actions"><button class="btn" onclick="closeM()">关闭</button></div>')}})}}async function init(){{let r=await api('/api/session');if(r.success)SESSION={{username:r.username,role:r.role}};document.getElementById('loginBtn').textContent=SESSION?'退出':'登录';document.getElementById('loginBtn').onclick=SESSION?logout:openLogin;if(SESSION){{document.getElementById('who').textContent=SESSION.username;document.getElementById('uploadBtn').style.display='block';document.getElementById('uploadBtn').onclick=openUpload;if(SESSION.role==='admin'){{document.getElementById('adminBtn').style.display='block';document.getElementById('adminBtn').onclick=openAdmin}}}}document.getElementById('cat').innerHTML='<option value="">全部分类</option>'+{cj}.map(x=>`<option>${{esc(x)}}</option>`).join('');render();if(!SESSION&&!HAS_USERS)openLogin()}}init();</script></body></html>'''

PAGE_CSS='''.header{position:sticky;top:0;z-index:20;background:#fffffff2;backdrop-filter:blur(16px);border-bottom:1px solid #e0e3eb}.header-inner{max-width:1450px;margin:auto;padding:10px 16px;display:flex;gap:12px;align-items:center}.logo{font-weight:800;white-space:nowrap}.logo small{display:block;color:#6b7280;font-size:9px;font-weight:500}.search{flex:1;max-width:680px;margin:auto}.search input{width:100%;height:38px;border:1px solid #e0e3eb;border-radius:9px;background:#f2f4f7;padding:0 13px;outline:0}.actions{display:flex;gap:7px;align-items:center}.btn{border:1px solid #e0e3eb;background:#fff;border-radius:8px;padding:7px 10px;font-size:12px;cursor:pointer}.btn.primary{background:#4f7cff;border-color:#4f7cff;color:#fff}.user{font-size:11px;color:#6b7280}main{max-width:1450px;margin:auto;padding:22px 16px 45px}.hero h1{font-size:23px;margin:0}.hero p{font-size:11px;color:#6b7280;margin:3px 0}.filter{display:flex;gap:8px;margin:18px 0}.filter select{border:1px solid #e0e3eb;border-radius:8px;background:#fff;padding:8px 12px;min-width:210px}.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(285px,1fr));gap:11px}.card{background:#fff;border:1px solid #e0e3eb;border-radius:13px;padding:13px;box-shadow:0 3px 16px rgba(0,0,0,.06)}.card-head{display:flex;gap:10px}.icon{width:38px;height:38px;flex:none;border-radius:9px;background:#eef3ff;color:#4f7cff;display:flex;align-items:center;justify-content:center}.icon svg{width:21px;height:21px}.card h2{font-size:14px;margin:0;word-break:break-word}.tag{display:inline-block;margin-top:5px;padding:2px 7px;border-radius:5px;background:#eef3ff;color:#4f7cff;font-size:9px}.desc{font-size:10px;color:#6b7280;margin-top:3px}.official{margin-top:8px}.official a{font-size:10px;color:#4f7cff;text-decoration:none}.file{margin-top:10px;padding-top:9px;border-top:1px solid #f0f1f3}.filename{font-size:11px;word-break:break-all}.meta{font-size:9px;color:#6b7280;margin:3px 0 6px}.links{display:flex;gap:5px;flex-wrap:wrap}.links a{font-size:10px;text-decoration:none;border:1px solid #e0e3eb;border-radius:6px;padding:4px 7px;color:#1a1d28}.links a.blue{color:#4f7cff}.empty{text-align:center;color:#6b7280;padding:70px}.modal-mask{display:none;position:fixed;inset:0;background:rgba(15,23,42,.48);z-index:100;align-items:center;justify-content:center;padding:15px}.modal{background:#fff;border-radius:14px;width:min(900px,100%);max-height:90vh;overflow:auto;padding:18px}.modal h2{margin:0 0 14px;font-size:17px}.form{display:grid;grid-template-columns:1fr 1fr;gap:9px}.form label{font-size:10px;color:#6b7280}.form input{width:100%;margin-top:4px;padding:8px;border:1px solid #e0e3eb;border-radius:7px}.modal-actions{display:flex;justify-content:flex-end;gap:7px;margin-top:14px}.admin-note{font-size:12px;color:#6b7280}@media(max-width:700px){.header-inner{flex-wrap:wrap}.search{order:3;flex-basis:100%}.user{display:none}.grid{grid-template-columns:1fr}.form{grid-template-columns:1fr}}
'''

# Replace the placeholder-compatible generate_html with the final renderer.
generate_html = regenerate_html

SESSIONS = {}

def _get_session(handler):
    token=handler.headers.get('X-Session','')
    if not token:
        m=re.search(r'(?:^|;\s*)session=([^;]+)',handler.headers.get('Cookie',''))
        token=m.group(1) if m else ''
    return SESSIONS.get(token)

def _send_json(handler,obj,status=200,headers=None):
    b=json.dumps(obj,ensure_ascii=False).encode();handler.send_response(status);handler.send_header('Content-Type','application/json; charset=utf-8');handler.send_header('Content-Length',str(len(b)))
    for k,v in (headers or {}).items():handler.send_header(k,v)
    handler.end_headers();handler.wfile.write(b)

def _body(handler):
    n=int(handler.headers.get('Content-Length','0') or 0)
    if n>2*1024*1024:raise ValueError('请求过大')
    return json.loads(handler.rfile.read(n) or b'{}')

def _admin(handler):
    u=_get_session(handler);return u if u and u.get('role')=='admin' else None

class SoftwareHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self,*args,**kwargs):super().__init__(*args,directory=DATA_DIR,**kwargs)
    def log_message(self,format,*args):
        try:
            os.makedirs(LOG_DIR,exist_ok=True)
            with open(os.path.join(LOG_DIR,'server.log'),'a',encoding='utf-8') as f:f.write(f'[{self.log_date_time_string()}] {format % args}\n')
        except Exception:pass
    def do_GET(self):
        p=urllib.parse.urlparse(self.path).path
        if p=='/':
            b=generate_html().encode();self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b);return
        if p=='/api/session':
            u=_get_session(self);_send_json(self,{'success':bool(u),'username':u.get('username') if u else None,'role':u.get('role') if u else None});return
        if p=='/api/software':_send_json(self,{'success':True,'data':build_software_list()});return
        if p.startswith('/download/'):
            rel=urllib.parse.unquote(p[len('/download/'):]).lstrip('/');root=os.path.realpath(ROOT_DIR);full=os.path.realpath(os.path.join(root,rel))
            if not full.startswith(root+os.sep) or not os.path.isfile(full):self.send_error(404);return
            st=os.stat(full);self.send_response(200);self.send_header('Content-Type','application/octet-stream');self.send_header('Content-Length',str(st.st_size));self.send_header('Content-Disposition',f'attachment; filename="{sanitize_filename(os.path.basename(full))}"');self.end_headers()
            try:
                with open(full,'rb') as f:
                    while True:
                        b=f.read(1024*1024)
                        if not b:break
                        self.wfile.write(b)
            except BrokenPipeError:pass
            return
        self.send_error(404)
    def do_POST(self):
        p=urllib.parse.urlparse(self.path).path
        try:d=_body(self)
        except Exception as e:return _send_json(self,{'success':False,'error':str(e)},400)
        if p=='/api/login':
            us=load_users();name=str(d.get('username','')).strip();pw=str(d.get('password',''))
            if not us.get('users'):
                if len(name)<2 or len(pw)<6:return _send_json(self,{'success':False,'error':'首次注册：用户名至少2位，密码至少6位'},400)
                salt,h=hash_password(pw);u={'username':name,'password':h,'salt':salt,'role':'admin'};save_json(USERS_FILE,{'users':[u]})
            else:
                u=next((x for x in us['users'] if x.get('username')==name),None)
                if not u or not verify_password(pw,u):return _send_json(self,{'success':False,'error':'用户名或密码错误'},401)
            sid=secrets.token_hex(32);SESSIONS[sid]=u.copy();return _send_json(self,{'success':True,'username':u['username'],'role':u['role']},headers={'Set-Cookie':f'session={sid}; HttpOnly; SameSite=Lax; Path=/'})
        if p=='/api/logout':
            m=re.search(r'(?:^|;\s*)session=([^;]+)',self.headers.get('Cookie',''));sid=m.group(1) if m else '';SESSIONS.pop(sid,None);return _send_json(self,{'success':True},headers={'Set-Cookie':'session=; Max-Age=0; Path=/'})
        if p=='/api/admin/data':
            if not _admin(self):return _send_json(self,{'success':False,'error':'需要管理员权限'},403)
            data=build_software_list();
            for x in data:x['key']=next((k for k,v in (load_json(CONFIG_FILE,default_config()).get('software',{}) or {}).items() if (v.get('displayName') if isinstance(v,dict) else None)==x['name']),x['name'])
            return _send_json(self,{'success':True,'users':load_users().get('users',[]),'software':data})
        if p=='/api/admin/user':
            if not _admin(self):return _send_json(self,{'success':False,'error':'需要管理员权限'},403)
            name=str(d.get('username','')).strip();pw=str(d.get('password',''));role='admin' if d.get('role')=='admin' else 'user';us=load_users()
            if len(name)<2 or len(pw)<6:return _send_json(self,{'success':False,'error':'用户名至少2位，密码至少6位'})
            if any(x.get('username')==name for x in us.get('users',[])):return _send_json(self,{'success':False,'error':'用户已存在'})
            salt,h=hash_password(pw);us.setdefault('users',[]).append({'username':name,'password':h,'salt':salt,'role':role});save_json(USERS_FILE,us);return _send_json(self,{'success':True})
        if p=='/api/admin/user/delete':
            if not _admin(self):return _send_json(self,{'success':False,'error':'需要管理员权限'},403)
            name=str(d.get('username',''));us=load_users();target=next((x for x in us.get('users',[]) if x.get('username')==name),None)
            if not target:return _send_json(self,{'success':False,'error':'用户不存在'})
            if target.get('role')=='admin' and sum(x.get('role')=='admin' for x in us['users'])<=1:return _send_json(self,{'success':False,'error':'不能删除最后一个管理员'})
            us['users']=[x for x in us['users'] if x.get('username')!=name];save_json(USERS_FILE,us);return _send_json(self,{'success':True})
        if p=='/api/admin/software':
            if not _admin(self):return _send_json(self,{'success':False,'error':'需要管理员权限'},403)
            name=str(d.get('name','')).strip();cfg=load_json(CONFIG_FILE,default_config());sw=cfg.setdefault('software',{});item=sw.setdefault(name,{})
            if d.get('versionPath'):
                url=str(d.get('downloadUrl','')).strip()
                if url and not re.match(r'^https?://',url,re.I):return _send_json(self,{'success':False,'error':'下载地址必须以 http:// 或 https:// 开头'})
                item.setdefault('versions',{})[str(d['versionPath'])]={'downloadUrl':url}
            else:
                for k in ('official','customOfficial','desc','category','icon','displayName'):
                    if k in d:item[k]=sanitize_filename(d[k]) if k=='displayName' else d[k]
            save_json(CONFIG_FILE,cfg);return _send_json(self,{'success':True})
        if p=='/api/rescan':
            if not _admin(self):return _send_json(self,{'success':False,'error':'需要管理员权限'},403)
            e=run_scan();return _send_json(self,{'success':True,'totalFiles':len(e)})
        if p=='/api/admin/fetch':
            if not _admin(self):return _send_json(self,{'success':False,'error':'需要管理员权限'},403)
            url=str(d.get('url','')).strip();name=str(d.get('name','')).strip()
            if not re.match(r'^https?://',url,re.I):return _send_json(self,{'success':False,'error':'仅支持 HTTP/HTTPS 地址'})
            threading.Thread(target=fetch_remote_file,args=(url,name),daemon=True).start();return _send_json(self,{'success':True,'message':'下载已开始'})
        return _send_json(self,{'success':False,'error':'Not Found'},404)
    def do_POST_multipart(self):pass
    def do_OPTIONS(self):self.send_response(204);self.end_headers()

def run_scan():
    global _last_scan_time
    e=build_entry_list();save_json(SCAN_FILE,e);_last_scan_time=datetime.now().isoformat();return e

def fetch_remote_file(url,name=None):
    try:
        os.makedirs(UPLOAD_DIR,exist_ok=True)
        with requests.get(url,stream=True,timeout=(15,60),allow_redirects=True,headers={'User-Agent':'Software-Library/8.0'}) as r:
            r.raise_for_status();length=int(r.headers.get('Content-Length','0') or 0)
            if length>MAX_DOWNLOAD_SIZE:raise ValueError('远程文件超过2GB限制')
            fn=sanitize_filename(name or os.path.basename(urllib.parse.urlparse(r.url).path) or 'download.bin');base,ext=os.path.splitext(fn);dest=os.path.join(UPLOAD_DIR,fn);i=1
            while os.path.exists(dest):dest=os.path.join(UPLOAD_DIR,f'{base}_{i}{ext}');i+=1
            total=0
            with open(dest,'wb') as f:
                for chunk in r.iter_content(1024*1024):
                    if not chunk:continue
                    total+=len(chunk)
                    if total>MAX_DOWNLOAD_SIZE:raise ValueError('远程文件超过2GB限制')
                    f.write(chunk)
        run_scan();print(f'[remote] saved {dest} ({format_size(total)})')
    except Exception as e:print(f'[remote] {e}')

def _multipart_upload(self):
    # Minimal multipart parser for a single uploaded file, avoiding deprecated cgi.
    import email.parser
    ctype=self.headers.get('Content-Type','')
    if 'multipart/form-data' not in ctype:return False
    boundary=ctype.split('boundary=',1)[-1].strip().strip('"')
    if not boundary:return False
    n=int(self.headers.get('Content-Length','0') or 0)
    if n>MAX_UPLOAD_SIZE+2*1024*1024:return False
    raw=self.rfile.read(n);marker=('--'+boundary).encode();parts=raw.split(marker)
    for part in parts:
        if b'filename=' not in part:continue
        head,sep,body=part.partition(b'\r\n\r\n')
        if not sep:continue
        m=re.search(br'filename="([^"]*)"',head)
        if not m:continue
        fn=sanitize_filename(m.group(1).decode('utf-8','replace'));body=body.rsplit(b'\r\n',1)[0]
        if len(body)>MAX_UPLOAD_SIZE:return False
        os.makedirs(UPLOAD_DIR,exist_ok=True);dest=os.path.join(UPLOAD_DIR,fn);base,ext=os.path.splitext(fn);i=1
        while os.path.exists(dest):dest=os.path.join(UPLOAD_DIR,f'{base}_{i}{ext}');i+=1
        with open(dest,'wb') as f:f.write(body)
        run_scan();_send_json(self,{'success':True,'filename':fn,'size':len(body)});return True
    return False

_old_post=SoftwareHandler.do_POST
def do_post_final(self):
    if self.path.split('?',1)[0]=='/api/upload':
        if not _get_session(self):return _send_json(self,{'success':False,'error':'请先登录'},401)
        if _multipart_upload(self):return
        return _send_json(self,{'success':False,'error':'上传数据无效'},400)
    return _old_post(self)
SoftwareHandler.do_POST=do_post_final

# Replace the generated-page hook with the actual renderer.
def generate_html():return regenerate_html()

def run_server(port):
    socketserver.TCPServer.allow_reuse_address=True
    httpd=None
    for p in range(port,port+20):
        try:httpd=socketserver.ThreadingTCPServer(('',p),SoftwareHandler);port=p;break
        except OSError:continue
    if not httpd:raise RuntimeError('Cannot find available port')
    print(f'\nSoftware Library v8 running at http://0.0.0.0:{port}\nRoot: {ROOT_DIR}\nData: {DATA_DIR}\n')
    try:httpd.serve_forever()
    finally:httpd.server_close()

def watch_loop(interval):
    while True:
        time.sleep(interval)
        try:run_scan()
        except Exception as e:print('[scan]',e)

def main():
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--scan-only',action='store_true');parser.add_argument('--no-scan',action='store_true');parser.add_argument('--port',type=int,default=PORT);parser.add_argument('--watch',action='store_true');a=parser.parse_args()
    os.makedirs(DATA_DIR,exist_ok=True);os.makedirs(ROOT_DIR,exist_ok=True)
    if not a.no_scan:run_scan()
    if a.scan_only:return
    if a.watch:threading.Thread(target=watch_loop,args=(WATCH_INTERVAL,),daemon=True).start()
    run_server(a.port)
if __name__=='__main__':main()
