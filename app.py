#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Software Library Scanner & Web Server
=====================================
Scans a directory for software files and serves a searchable web UI.

Environment variables:
  LIB_ROOT_DIR       Root directory to scan (default: /data)
  LIB_PORT           Web server port (default: 8899)
  LIB_DATA_DIR       Generated files directory (default: /app/data)
  LIB_WATCH_INTERVAL Auto-rescan interval in seconds (default: 3600)
"""

import os
import re
import json
import sys
import time
import threading
import http.server
import socketserver
from datetime import datetime
from pathlib import Path

# ============================================================
# Configuration
# ============================================================

ROOT_DIR = os.environ.get("LIB_ROOT_DIR", "/data")
PORT = int(os.environ.get("LIB_PORT", "8899"))
DATA_DIR = os.environ.get("LIB_DATA_DIR", "/app/data")
WATCH_INTERVAL = int(os.environ.get("LIB_WATCH_INTERVAL", "3600"))

HTML_FILE = os.path.join(DATA_DIR, "index.html")
JSON_FILE = os.path.join(DATA_DIR, "software_library.json")
LOG_DIR = os.path.join(DATA_DIR, "logs")

SUPPORTED_EXTENSIONS = {
    ".exe": "EXE 安装包",
    ".msi": "MSI 安装包",
    ".iso": "ISO 镜像",
    ".img": "IMG 镜像",
    ".zip": "ZIP 压缩包",
    ".7z": "7Z 压缩包",
    ".rar": "RAR 压缩包",
    ".gz": "GZ 压缩包",
    ".esd": "ESD 镜像",
    ".tar.xz": "TAR.XZ 压缩包",
    ".tar.gz": "TAR.GZ 压缩包",
    ".apk": "APK 安装包",
    ".dmg": "DMG 镜像",
    ".pkg": "PKG 安装包",
    ".deb": "DEB 包",
    ".rpm": "RPM 包",
    ".vmdk": "VMDK 虚拟磁盘",
    ".ova": "OVA 虚拟设备",
    ".ovf": "OVF 虚拟设备",
    ".vdi": "VDI 虚拟磁盘",
    ".qcow2": "QCOW2 虚拟磁盘",
    ".wim": "WIM 镜像",
}

SKIP_DIRS = {"logs", "工作文件", "文档", ".workbuddy-ai", "$RECYCLE.BIN", "System Volume Information", "@Recycle", ".zsshare_trash", "docker"}
SKIP_FILES = {"README.md", "index.html", "software_library.json", "update_library.py", "app.py", "deploy.sh", "启动软件库.bat"}

# ============================================================
# Software knowledge base
# ============================================================

SOFTWARE_DB = {
    "vmware": {"name":"VMware Workstation","category":"虚拟化","icon":"🏢","desc":"VMware 虚拟机工作站","official":"https://www.vmware.com"},
    "esxi": {"name":"VMware ESXi","category":"虚拟化","icon":"🏢","desc":"VMware ESXi 裸机虚拟化系统","official":"https://www.vmware.com/products/esxi-and-esx.html"},
    "proxmox": {"name":"Proxmox VE","category":"虚拟化","icon":"🖥️","desc":"开源虚拟化管理平台 (KVM/LXC)","official":"https://www.proxmox.com"},
    "truenas": {"name":"TrueNAS SCALE","category":"NAS/存储","icon":"💾","desc":"开源 NAS 操作系统","official":"https://www.truenas.com"},
    "fnos": {"name":"飞牛 OS (fnOS)","category":"NAS/存储","icon":"💾","desc":"飞牛私有云 NAS 操作系统","official":"https://www.fnos.com"},
    "windows": {"name":"Windows","category":"操作系统","icon":"🪟","desc":"Windows 系统镜像","official":"https://www.microsoft.com/windows"},
    "cn_windows": {"name":"Windows","category":"操作系统","icon":"🪟","desc":"Windows 原版镜像","official":"https://www.microsoft.com"},
    "edrv8": {"name":"EasyDrv 驱动包","category":"驱动","icon":"🔧","desc":"Windows 驱动自动安装包","official":""},
    "wepe": {"name":"WePE 微PE","category":"PE/维护","icon":"🛠️","desc":"微PE工具箱，装机维护利器","official":"https://www.wepe.com.cn"},
    "centos": {"name":"CentOS","category":"操作系统","icon":"🐧","desc":"CentOS Linux 服务器系统","official":"https://www.centos.org"},
    "debian": {"name":"Debian","category":"操作系统","icon":"🐧","desc":"Debian GNU/Linux 系统","official":"https://www.debian.org"},
    "ubuntu": {"name":"Ubuntu Server","category":"操作系统","icon":"🐧","desc":"Ubuntu Server 服务器系统","official":"https://ubuntu.com"},
    "openwrt": {"name":"OpenWrt","category":"路由器/软路由","icon":"📡","desc":"OpenWrt 软路由固件","official":"https://openwrt.org"},
    "istoreos": {"name":"iStoreOS","category":"路由器/软路由","icon":"📡","desc":"iStoreOS 软路由系统","official":"https://www.istoreos.com"},
    "ikuai": {"name":"iKuai 爱快","category":"路由器/软路由","icon":"📡","desc":"爱快流控路由系统","official":"https://www.ikuai8.com"},
    "mwrt": {"name":"Mwrt (四字真言)","category":"路由器/软路由","icon":"📡","desc":"Mwrt 软路由固件","official":""},
    "lean code": {"name":"Lean Code 固件","category":"路由器/软路由","icon":"📡","desc":"Lean Code OpenWrt 固件合集","official":""},
    "ezopwrt": {"name":"EzOpWrt","category":"路由器/软路由","icon":"📡","desc":"EzOpWrt 软路由固件","official":""},
    "bleachwrt": {"name":"BleachWrt","category":"路由器/软路由","icon":"📡","desc":"BleachWrt 软路由固件","official":""},
    "kwrt": {"name":"KWrt","category":"路由器/软路由","icon":"📡","desc":"KWrt 软路由固件","official":""},
    "lede": {"name":"LEDE","category":"路由器/软路由","icon":"📡","desc":"LEDE 软路由固件","official":""},
    "immortalwrt": {"name":"ImmortalWrt","category":"路由器/软路由","icon":"📡","desc":"ImmortalWrt 软路由固件","official":"https://immortalwrt.org"},
    "docker-immortalwrt": {"name":"Docker ImmortalWrt","category":"路由器/软路由","icon":"📡","desc":"带 Docker 的 ImmortalWrt 固件","official":"https://immortalwrt.org"},
    "sql server": {"name":"SQL Server","category":"数据库","icon":"🗄️","desc":"Microsoft SQL Server 数据库","official":"https://www.microsoft.com/sql-server"},
    "sqlserver": {"name":"SQL Server","category":"数据库","icon":"🗄️","desc":"Microsoft SQL Server 数据库","official":"https://www.microsoft.com/sql-server"},
    "mysql": {"name":"MySQL","category":"数据库","icon":"🗄️","desc":"MySQL 数据库","official":"https://www.mysql.com"},
    "redis": {"name":"Redis","category":"数据库","icon":"🗄️","desc":"Redis 内存数据库","official":"https://redis.io"},
    "office": {"name":"Microsoft Office","category":"办公软件","icon":"📊","desc":"Microsoft Office 办公套件","official":"https://www.microsoft.com/microsoft-365"},
    "adobe": {"name":"Adobe","category":"设计/创意","icon":"🎨","desc":"Adobe 创意套件","official":"https://www.adobe.com"},
    "acrobat": {"name":"Adobe Acrobat","category":"设计/创意","icon":"📄","desc":"Adobe Acrobat PDF 编辑器","official":"https://www.adobe.com/acrobat.html"},
    "wps": {"name":"WPS Office","category":"办公软件","icon":"📊","desc":"WPS Office 办公套件","official":"https://www.wps.cn"},
    "creative cloud": {"name":"Adobe Creative Cloud","category":"设计/创意","icon":"🎨","desc":"Adobe Creative Cloud 创意套件","official":"https://www.adobe.com/creativecloud.html"},
    "git": {"name":"Git","category":"开发工具","icon":"🔧","desc":"Git 版本控制工具","official":"https://git-scm.com"},
    "jdk": {"name":"JDK (Java)","category":"开发工具","icon":"☕","desc":"Java Development Kit","official":"https://www.oracle.com/java/technologies/downloads/"},
    "python": {"name":"Python","category":"开发工具","icon":"🐍","desc":"Python 编程语言","official":"https://www.python.org"},
    "pycharm": {"name":"PyCharm","category":"开发工具","icon":"🐍","desc":"PyCharm Python IDE","official":"https://www.jetbrains.com/pycharm/"},
    "jetbrains": {"name":"JetBrains Patch","category":"开发工具","icon":"🔧","desc":"JetBrains IDE 补丁","official":"https://www.jetbrains.com"},
    "navicat": {"name":"Navicat Premium","category":"数据库","icon":"🗄️","desc":"Navicat 数据库管理工具","official":"https://www.navicat.com"},
    "mobaxterm": {"name":"MobaXterm","category":"开发工具","icon":"🖥️","desc":"MobaXterm 终端工具","official":"https://mobaxterm.mobatek.net"},
    "xshell": {"name":"Xshell Plus","category":"开发工具","icon":"🖥️","desc":"Xshell 终端模拟器","official":"https://www.xshell.com"},
    "sublime": {"name":"Sublime Text","category":"开发工具","icon":"📝","desc":"Sublime Text 代码编辑器","official":"https://www.sublimetext.com"},
    "apifox": {"name":"Apifox","category":"开发工具","icon":"🔗","desc":"Apifox API 调试工具","official":"https://apifox.com"},
    "diskgenius": {"name":"DiskGenius","category":"系统工具","icon":"💾","desc":"DiskGenius 磁盘分区管理工具","official":"https://www.diskgenius.com"},
    "ultraiso": {"name":"UltraISO","category":"系统工具","icon":"💿","desc":"UltraISO 光盘镜像工具","official":"https://www.ultraiso.com"},
    "winrar": {"name":"WinRAR","category":"系统工具","icon":"📦","desc":"WinRAR 压缩解压工具","official":"https://www.rarlab.com"},
    "rufus": {"name":"Rufus","category":"系统工具","icon":"💿","desc":"Rufus USB 启动盘制作工具","official":"https://rufus.ie"},
    "balenaetcher": {"name":"balenaEtcher","category":"系统工具","icon":"💿","desc":"balenaEtcher 镜像写入工具","official":"https://etcher.balena.io"},
    "win32diskimager": {"name":"Win32 Disk Imager","category":"系统工具","icon":"💿","desc":"Win32 Disk Imager 镜像写入工具","official":"https://sourceforge.net/projects/win32diskimager/"},
    "geek": {"name":"Geek Uninstaller","category":"系统工具","icon":"🗑️","desc":"Geek 卸载器，强力卸载","official":"https://geekuninstaller.com"},
    "dism": {"name":"Dism++","category":"系统工具","icon":"🔧","desc":"Dism++ Windows 优化工具","official":"http://www.chuyu.me"},
    "startallback": {"name":"StartAllBack","category":"系统工具","icon":"🪟","desc":"StartAllBack Win11 开始菜单工具","official":"https://www.startallback.com"},
    "easybcd": {"name":"EasyBCD","category":"系统工具","icon":"🔧","desc":"EasyBCD 引导管理工具","official":"https://neosmart.net/EasyBCD/"},
    "easyu": {"name":"EasyU","category":"系统工具","icon":"🔧","desc":"EasyU 装机维护工具","official":""},
    "iptoolbox": {"name":"IPToolBox","category":"系统工具","icon":"🌐","desc":"IP 工具箱","official":""},
    "clash": {"name":"Clash","category":"网络/代理","icon":"🌐","desc":"Clash 代理客户端","official":"https://github.com/Dreamacro/clash"},
    "clash.verge": {"name":"Clash Verge","category":"网络/代理","icon":"🌐","desc":"Clash Verge Rev 代理客户端","official":"https://github.com/clash-verge-rev/clash-verge-rev"},
    "bypass": {"name":"Bypass","category":"网络/代理","icon":"🌐","desc":"Bypass 旁路由工具","official":""},
    "rustdesk": {"name":"RustDesk","category":"远程控制","icon":"🖥️","desc":"RustDesk 远程桌面工具","official":"https://rustdesk.com"},
    "chrome": {"name":"Google Chrome","category":"浏览器","icon":"🌐","desc":"Google Chrome 浏览器","official":"https://www.google.com/chrome/"},
    "firefox": {"name":"Firefox","category":"浏览器","icon":"🦊","desc":"Mozilla Firefox 浏览器","official":"https://www.mozilla.org/firefox/"},
    "wallpaper engine": {"name":"Wallpaper Engine","category":"媒体/娱乐","icon":"🖼️","desc":"Wallpaper Engine 动态壁纸","official":"https://www.wallpaperengine.io"},
    "potplayer": {"name":"PotPlayer","category":"媒体/娱乐","icon":"🎬","desc":"PotPlayer 视频播放器","official":"https://potplayer.daum.net"},
    "pot_bd": {"name":"PotPlayer","category":"媒体/娱乐","icon":"🎬","desc":"PotPlayer 视频播放器","official":"https://potplayer.daum.net"},
    "pixpin": {"name":"PixPin","category":"系统工具","icon":"📸","desc":"PixPin 截图工具","official":"https://pixpin.cn"},
    "heu": {"name":"HEU KMS Activator","category":"激活工具","icon":"🔑","desc":"HEU KMS 激活工具","official":"https://github.com/zbezj/HEU_KMS_Activator"},
    "lky_office": {"name":"LKY OfficeTools","category":"激活工具","icon":"🔑","desc":"LKY Office 一键安装激活","official":"https://github.com/OdysseusYuan/LKY_OfficeTools"},
    "asteriskpassword": {"name":"星号密码查看器","category":"系统工具","icon":"🔒","desc":"AsteriskPassword 星号密码查看器","official":""},
    "virtio": {"name":"VirtIO 驱动","category":"驱动","icon":"🔧","desc":"VirtIO Windows 驱动 (KVM/QEMU)","official":"https://fedoraproject.org/wiki/Windows_Virtio_Drivers"},
    "一盘走天下": {"name":"一盘走天下","category":"PE/维护","icon":"🛠️","desc":"一盘走天下 PE 维护合集","official":""},
    "fuint": {"name":"Fuint 会员系统","category":"其他","icon":"📦","desc":"Fuint 会员营销系统","official":"https://www.fuint.cn"},
    "公文排版": {"name":"公文排版工具","category":"办公软件","icon":"📝","desc":"公文排版工具","official":""},
    "vm workstation": {"name":"VM Workstation (Linux)","category":"虚拟化","icon":"🏢","desc":"VMware Workstation for Linux","official":"https://www.vmware.com"},
}


def match_software(filename, dirpath):
    lower = (filename + " " + dirpath).lower()
    for key, info in SOFTWARE_DB.items():
        if key in lower:
            return info["name"], info["category"], info["icon"], info["desc"], info.get("official","")
    if "vm" in lower and "bios" in lower:
        return "VMware BIOS/EFI", "虚拟化", "🏢", "VMware BIOS/EFI 文件", ""
    if "tools" in lower and ("vmware" in lower or "vm" in lower):
        return "VMware Tools", "虚拟化", "🏢", "VMware Tools 驱动包", ""
    if "keygen" in lower or "注册" in lower:
        return "注册机/工具", "激活工具", "🔑", "注册/激活工具", ""
    if "补丁" in lower or "patch" in lower:
        return "补丁工具", "激活工具", "🔑", "软件补丁", ""
    if "virtualprinter" in lower:
        return "Virtual Printer", "虚拟化", "🖨️", "VMware 虚拟打印机", ""
    if "darwin" in lower:
        return "VMware Tools (macOS)", "虚拟化", "🏢", "macOS VMware Tools", ""
    if "solaris" in lower:
        return "Solaris Tools", "虚拟化", "☀️", "Solaris VMware Tools", ""
    if "freebsd" in lower:
        return "FreeBSD Tools", "虚拟化", "🐧", "FreeBSD VMware Tools", ""
    if "netware" in lower:
        return "NetWare Tools", "虚拟化", "📦", "NetWare VMware Tools", ""
    if "winpre" in lower:
        return "Windows Tools (旧版)", "虚拟化", "🪟", "旧版 Windows VMware Tools", ""
    if "tweaker" in lower:
        return "VM Tweaker", "虚拟化", "🔧", "VMware 调整工具", ""
    if "懒人" in lower or "去虚拟化" in lower:
        return "VMware 去虚拟化工具", "虚拟化", "🔧", "VMware 去虚拟化工具", ""
    if "adobe genp" in lower:
        return "Adobe GenP", "设计/创意", "🎨", "Adobe 通用补丁工具", ""
    if "enableloopback" in lower:
        return "EnableLoopback", "网络/代理", "🌐", "UWP 环回代理工具", ""
    if "sysproxy" in lower:
        return "sysproxy", "网络/代理", "🌐", "系统代理设置工具", ""
    if "tapinstall" in lower or ("tap" in lower and "install" in lower):
        return "TAP Driver", "网络/代理", "🌐", "TAP 网卡驱动安装", ""
    if "go-tun2socks" in lower:
        return "go-tun2socks", "网络/代理", "🌐", "TUN 转 SOCKS 工具", ""
    if "clash-core" in lower or "clash-win" in lower:
        return "Clash Core", "网络/代理", "🌐", "Clash 核心程序", ""
    if "unins" in lower:
        return "卸载程序", "系统工具", "🗑️", "软件卸载程序", ""
    if "dgfileviewer" in lower:
        return "DG FileViewer", "系统工具", "💾", "DiskGenius 文件查看器", ""
    if "offlinereg" in lower:
        return "OfflineReg", "系统工具", "🔧", "离线注册表编辑器", ""
    if "redis-desktop" in lower:
        return "Redis Desktop Manager", "数据库", "🗄️", "Redis 可视化管理工具", "https://redisdesktop.com"
    if "tar.xz" in lower:
        return "压缩包", "其他", "📦", "压缩文件", ""
    if "vmdk" in lower:
        return "虚拟磁盘 (VMDK)", "虚拟化", "💽", "VMware 虚拟磁盘文件", ""
    if "ova" in lower or "ovf" in lower:
        return "虚拟设备 (OVF/OVA)", "虚拟化", "💽", "虚拟机导入设备文件", ""
    if "wim" in lower:
        return "WIM 镜像", "操作系统", "🪟", "Windows 映像文件", ""
    return os.path.splitext(filename)[0], "其他", "📦", "软件文件", ""


def format_size(size_bytes):
    if size_bytes == 0:
        return "0 B"
    size = float(size_bytes)
    for unit in ["B","KB","MB","GB","TB"]:
        if size < 1024:
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} PB"


def get_file_date(filepath):
    try:
        mtime = os.path.getmtime(filepath)
        return datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")
    except Exception:
        return ""


def parse_version(filename):
    patterns = [
        r'(\d+\.\d+\.\d+\.\d+)', r'(\d+\.\d+\.\d+)', r'(\d+\.\d+)',
        r'v(\d+\.\d+\.\d+)', r'v(\d+\.\d+)', r'(\d+U\d+\w*)',
        r'(\d+\.\d+\.\d+-\d+)', r'Build(\d+)', r'(\d{4}\.\d+)', r'(\d{4})',
    ]
    for pat in patterns:
        m = re.search(pat, filename, re.IGNORECASE)
        if m:
            return m.group(1)
    return ""


def scan_directory(root_dir):
    items = []
    exts = set(SUPPORTED_EXTENSIONS.keys())
    compound_exts = [".tar.gz", ".tar.xz"]
    for dirpath, dirnames, filenames in os.walk(root_dir):
        dirnames[:] = [d for d in dirnames if d.lower() not in SKIP_DIRS and not d.startswith(".")]
        for filename in filenames:
            if filename.lower() in SKIP_FILES:
                continue
            fullpath = os.path.join(dirpath, filename)
            lower = filename.lower()
            matched_ext = None
            for ce in compound_exts:
                if lower.endswith(ce):
                    matched_ext = ce
                    break
            if not matched_ext:
                _, ext = os.path.splitext(filename)
                ext = ext.lower()
                if ext in exts:
                    matched_ext = ext
            if not matched_ext:
                continue
            try:
                size = os.path.getsize(fullpath)
            except Exception:
                size = 0
            relpath = os.path.relpath(fullpath, root_dir)
            webpath = relpath.replace("\\", "/")
            version = parse_version(filename)
            name, category, icon, desc, official = match_software(filename, dirpath)
            item = {
                "name": name, "filename": filename, "category": category,
                "icon": icon, "desc": desc, "official": official,
                "version": version, "size": size, "sizeText": format_size(size),
                "ext": matched_ext, "fileType": SUPPORTED_EXTENSIONS.get(matched_ext, "文件"),
                "date": get_file_date(fullpath), "path": webpath,
                "relativeDir": os.path.dirname(relpath).replace("\\", "/"),
            }
            items.append(item)
    items.sort(key=lambda x: (x["category"], x["name"].lower(), x["filename"].lower()))
    return items


def generate_html(items, root_dir):
    categories = {}
    for item in items:
        cat = item["category"]
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(item)

    cat_icons = {
        "操作系统":"🪟","虚拟化":"🏢","NAS/存储":"💾","路由器/软路由":"📡",
        "数据库":"🗄️","开发工具":"🔧","系统工具":"🛠️","网络/代理":"🌐",
        "浏览器":"🌍","办公软件":"📊","设计/创意":"🎨","媒体/娱乐":"🎬",
        "远程控制":"🖥️","激活工具":"🔑","PE/维护":"🛠️","驱动":"🔧","其他":"📦",
    }

    json_data = json.dumps(items, ensure_ascii=False)
    total_size = sum(i["size"] for i in items)
    total_size_text = format_size(total_size)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>软件库 | Software Library</title>
<style>
:root {{
  --bg:#f5f6f8; --bg-card:#ffffff; --bg-card-hover:#fafbfc;
  --bg-search:#eef0f3; --text:#1a1d28; --text-dim:#6b7280;
  --text-bright:#111827; --accent:#4f7cff; --accent-glow:rgba(79,124,255,0.15);
  --accent-soft:rgba(79,124,255,0.06); --border:#e0e3eb; --border-bright:#c8ccd6;
  --radius:12px; --green:#16a34a; --orange:#d97706; --red:#dc2626;
  --shadow:0 2px 12px rgba(0,0,0,0.06); --shadow-lg:0 4px 24px rgba(0,0,0,0.08);
}}
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ font-family:-apple-system,'Segoe UI','Microsoft YaHei',sans-serif; background:var(--bg); color:var(--text); line-height:1.6; min-height:100vh; }}
.header {{ position:sticky; top:0; z-index:100; background:rgba(255,255,255,0.9); backdrop-filter:blur(20px); -webkit-backdrop-filter:blur(20px); border-bottom:1px solid var(--border); padding:14px 0; }}
.header-inner {{ max-width:1400px; margin:0 auto; padding:0 24px; display:flex; align-items:center; gap:20px; flex-wrap:wrap; }}
.logo {{ display:flex; align-items:center; gap:12px; flex-shrink:0; }}
.logo-icon {{ width:42px; height:42px; border-radius:10px; background:linear-gradient(135deg,var(--accent),#6b5cff); display:flex; align-items:center; justify-content:center; font-size:20px; box-shadow:var(--shadow); }}
.logo-text h1 {{ font-size:18px; color:var(--text-bright); font-weight:700; }}
.logo-text span {{ font-size:11px; color:var(--text-dim); }}
.search-box {{ flex:1; min-width:200px; position:relative; }}
.search-box input {{ width:100%; padding:10px 16px 10px 42px; background:var(--bg-search); border:1px solid var(--border); border-radius:10px; color:var(--text); font-size:14px; transition:all 0.2s; }}
.search-box input:focus {{ outline:none; border-color:var(--accent); box-shadow:0 0 0 3px var(--accent-glow); }}
.search-box .search-icon {{ position:absolute; left:14px; top:50%; transform:translateY(-50%); color:var(--text-dim); font-size:16px; }}
.stats {{ display:flex; gap:20px; flex-shrink:0; }}
.stat-item {{ text-align:center; }}
.stat-item .num {{ font-size:18px; font-weight:700; color:var(--accent); }}
.stat-item .label {{ font-size:11px; color:var(--text-dim); }}
.cat-bar {{ background:var(--bg-card); border-bottom:1px solid var(--border); padding:8px 0; overflow-x:auto; white-space:nowrap; position:sticky; top:69px; z-index:99; }}
.cat-bar-inner {{ max-width:1400px; margin:0 auto; padding:0 24px; display:flex; gap:8px; }}
.cat-chip {{ display:inline-flex; align-items:center; gap:6px; padding:6px 14px; border-radius:20px; background:transparent; border:1px solid var(--border); color:var(--text-dim); font-size:13px; cursor:pointer; transition:all 0.15s; white-space:nowrap; user-select:none; }}
.cat-chip:hover {{ border-color:var(--border-bright); color:var(--text); }}
.cat-chip.active {{ background:var(--accent-soft); border-color:var(--accent); color:var(--accent); }}
.cat-chip .count {{ font-size:11px; opacity:0.7; margin-left:2px; }}
.container {{ max-width:1400px; margin:0 auto; padding:24px; }}
.section {{ margin-bottom:32px; }}
.section-header {{ display:flex; align-items:center; gap:10px; margin-bottom:16px; padding-bottom:8px; border-bottom:1px solid var(--border); }}
.section-header h2 {{ font-size:17px; color:var(--text-bright); }}
.section-header .cat-icon {{ font-size:22px; }}
.grid {{ display:grid; grid-template-columns:repeat(auto-fill, minmax(330px, 1fr)); gap:14px; }}
.card {{ background:var(--bg-card); border:1px solid var(--border); border-radius:var(--radius); padding:16px; transition:all 0.2s; display:flex; flex-direction:column; gap:10px; box-shadow:var(--shadow); }}
.card:hover {{ border-color:var(--border-bright); box-shadow:var(--shadow-lg); transform:translateY(-1px); }}
.card-top {{ display:flex; align-items:flex-start; gap:12px; }}
.card-icon {{ width:48px; height:48px; border-radius:10px; background:var(--bg-search); display:flex; align-items:center; justify-content:center; font-size:26px; flex-shrink:0; }}
.card-info {{ flex:1; min-width:0; }}
.card-title {{ font-size:14px; font-weight:600; color:var(--text-bright); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }}
.card-version {{ display:inline-block; font-size:11px; color:var(--accent); background:var(--accent-soft); padding:1px 7px; border-radius:4px; margin-left:6px; vertical-align:middle; }}
.card-desc {{ font-size:12px; color:var(--text-dim); margin-top:3px; overflow:hidden; text-overflow:ellipsis; display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; }}
.card-meta {{ display:flex; flex-wrap:wrap; gap:8px; font-size:11px; }}
.meta-tag {{ display:inline-flex; align-items:center; gap:3px; padding:2px 8px; border-radius:4px; background:rgba(0,0,0,0.03); }}
.meta-tag.type {{ color:var(--orange); }}
.meta-tag.size {{ color:var(--green); }}
.meta-tag.date {{ color:var(--text-dim); }}
.card-actions {{ display:flex; gap:8px; margin-top:4px; }}
.btn {{ display:inline-flex; align-items:center; gap:4px; padding:6px 14px; border-radius:8px; font-size:12px; font-weight:500; cursor:pointer; text-decoration:none; transition:all 0.15s; border:none; }}
.btn-download {{ background:var(--accent); color:#fff; flex:1; justify-content:center; }}
.btn-download:hover {{ background:#3a6aff; }}
.btn-official {{ background:transparent; border:1px solid var(--border-bright); color:var(--text-dim); padding:6px 12px; }}
.btn-official:hover {{ border-color:var(--accent); color:var(--accent); }}
.btn-copy {{ background:transparent; border:1px solid var(--border-bright); color:var(--text-dim); padding:6px 10px; font-size:12px; }}
.btn-copy:hover {{ border-color:var(--green); color:var(--green); }}
.card-path {{ font-size:11px; color:var(--text-dim); opacity:0.6; font-family:'Cascadia Code','Consolas',monospace; word-break:break-all; cursor:pointer; transition:opacity 0.15s; }}
.card-path:hover {{ opacity:1; }}
.no-results {{ text-align:center; padding:60px 20px; color:var(--text-dim); }}
.no-results .icon {{ font-size:48px; margin-bottom:16px; }}
.footer {{ text-align:center; padding:24px; color:var(--text-dim); font-size:12px; border-top:1px solid var(--border); margin-top:40px; }}
@media (max-width:768px) {{ .header-inner {{ flex-direction:column; align-items:stretch; }} .stats {{ justify-content:center; }} .grid {{ grid-template-columns:1fr; }} .cat-bar {{ top:120px; }} }}
::-webkit-scrollbar {{ width:8px; height:8px; }}
::-webkit-scrollbar-track {{ background:transparent; }}
::-webkit-scrollbar-thumb {{ background:var(--border-bright); border-radius:4px; }}
::-webkit-scrollbar-thumb:hover {{ background:#a8acb8; }}
@keyframes fadeIn {{ from {{ opacity:0; transform:translateY(8px); }} to {{ opacity:1; transform:translateY(0); }} }}
.card {{ animation:fadeIn 0.3s ease-out; }}
.scan-badge {{ display:inline-flex; align-items:center; gap:4px; font-size:11px; color:var(--text-dim); margin-left:8px; }}
.scan-badge .dot {{ width:8px; height:8px; border-radius:50%; background:var(--green); display:inline-block; animation:pulse 2s infinite; }}
@keyframes pulse {{ 0%,100% {{ opacity:1; }} 50% {{ opacity:0.4; }} }}
</style>
</head>
<body>
<div class="header"><div class="header-inner">
  <div class="logo"><div class="logo-icon">📦</div><div class="logo-text"><h1>软件库 <span class="scan-badge"><span class="dot"></span> Live</span></h1><span>Software Library</span></div></div>
  <div class="search-box"><span class="search-icon">🔍</span><input type="text" id="searchInput" placeholder="搜索软件名、版本、类型..." autocomplete="off"></div>
  <div class="stats"><div class="stat-item"><div class="num" id="statCount">{len(items)}</div><div class="label">文件</div></div><div class="stat-item"><div class="num">{len(categories)}</div><div class="label">分类</div></div><div class="stat-item"><div class="num">{total_size_text}</div><div class="label">总量</div></div></div>
</div></div>
<div class="cat-bar"><div class="cat-bar-inner" id="catBar"><div class="cat-chip active" data-cat="all">📋 全部 <span class="count">({len(items)})</span></div></div></div>
<div class="container" id="container"></div>
<div class="footer"><p>软件库自动扫描生成 · 共 {len(items)} 个文件 · 总计 {total_size_text}</p><p style="margin-top:4px;">最后更新: {now_str}</p></div>
<script>
const ALL_DATA = {json_data};
const CAT_ICONS = {json.dumps(cat_icons, ensure_ascii=False)};
const categories = [...new Set(ALL_DATA.map(i => i.category))];
const catBar = document.getElementById('catBar');
categories.forEach(cat => {{ const count = ALL_DATA.filter(i => i.category === cat).length; const icon = CAT_ICONS[cat] || '📦'; const chip = document.createElement('div'); chip.className = 'cat-chip'; chip.dataset.cat = cat; chip.innerHTML = icon + ' ' + cat + ' <span class="count">(' + count + ')</span>'; chip.onclick = () => selectCategory(cat); catBar.appendChild(chip); }});
let currentCat = 'all'; let searchTerm = '';
function selectCategory(cat) {{ currentCat = cat; document.querySelectorAll('.cat-chip').forEach(c => {{ c.classList.toggle('active', c.dataset.cat === cat); }}); render(); }}
document.getElementById('searchInput').addEventListener('input', e => {{ searchTerm = e.target.value.toLowerCase().trim(); render(); }});
function escapeHtml(str) {{ const div = document.createElement('div'); div.textContent = str; return div.innerHTML; }}
function encodePath(path) {{ return btoa(unescape(encodeURIComponent(path))); }}
function render() {{
  const container = document.getElementById('container');
  let filtered = ALL_DATA;
  if (currentCat !== 'all') filtered = filtered.filter(i => i.category === currentCat);
  if (searchTerm) filtered = filtered.filter(i => (i.name + ' ' + i.filename + ' ' + i.desc + ' ' + i.category + ' ' + (i.version||'')).toLowerCase().includes(searchTerm));
  document.getElementById('statCount').textContent = filtered.length;
  if (filtered.length === 0) {{ container.innerHTML = '<div class="no-results"><div class="icon">🔍</div><p>没有找到匹配的文件</p></div>'; return; }}
  const grouped = {{}};
  filtered.forEach(i => {{ if (!grouped[i.category]) grouped[i.category] = []; grouped[i.category].push(i); }});
  let html = '';
  for (const cat of Object.keys(grouped).sort()) {{
    const items = grouped[cat]; const icon = CAT_ICONS[cat] || '📦';
    html += '<div class="section"><div class="section-header"><span class="cat-icon">' + icon + '</span><h2>' + cat + ' (' + items.length + ')</h2></div><div class="grid">';
    for (const item of items) {{
      html += '<div class="card"><div class="card-top"><div class="card-icon">' + item.icon + '</div><div class="card-info"><div class="card-title">' + escapeHtml(item.name);
      if (item.version) html += '<span class="card-version">v' + escapeHtml(item.version) + '</span>';
      html += '</div><div class="card-desc">' + escapeHtml(item.desc) + '</div></div></div><div class="card-meta">';
      html += '<span class="meta-tag type">' + item.fileType + '</span><span class="meta-tag size">' + item.sizeText + '</span>';
      if (item.date) html += '<span class="meta-tag date">📅 ' + item.date + '</span>';
      html += '</div>';
      const enc = encodePath(item.path);
      html += '<div class="card-path" title="点击复制路径" onclick="copyPath(\\'' + enc + '\\')">' + escapeHtml(item.relativeDir || '/') + '</div>';
      html += '<div class="card-actions"><a class="btn btn-download" href="' + item.path + '" download="' + escapeHtml(item.filename) + '">⬇ 下载</a>';
      if (item.official) html += '<a class="btn btn-official" href="' + item.official + '" target="_blank">🔗 官网</a>';
      html += '<button class="btn btn-copy" onclick="copyPath(\\'' + enc + '\\')">📋 路径</button></div></div>';
    }}
    html += '</div></div>';
  }}
  container.innerHTML = html;
}}
function copyPath(encoded) {{
  const path = decodeURIComponent(escape(atob(encoded)));
  navigator.clipboard.writeText(path).then(() => showToast('路径已复制: ' + path)).catch(() => {{ const ta = document.createElement('textarea'); ta.value = path; document.body.appendChild(ta); ta.select(); try {{ document.execCommand('copy'); showToast('路径已复制'); }} catch(e) {{ showToast('复制失败'); }} document.body.removeChild(ta); }});
}}
function showToast(msg) {{
  let toast = document.getElementById('toast');
  if (!toast) {{ toast = document.createElement('div'); toast.id = 'toast'; toast.style.cssText = 'position:fixed;bottom:30px;left:50%;transform:translateX(-50%);background:#1a1d28;color:#fff;padding:10px 24px;border-radius:8px;font-size:13px;z-index:9999;opacity:0;transition:opacity 0.3s;box-shadow:0 4px 12px rgba(0,0,0,0.2);'; document.body.appendChild(toast); }}
  toast.textContent = msg; toast.style.opacity = '1'; clearTimeout(toast._timer); toast._timer = setTimeout(() => {{ toast.style.opacity = '0'; }}, 2500);
}}
render();
</script>
</body>
</html>"""
    return html


class SoftwareHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT_DIR, **kwargs)

    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        if any(self.path.lower().endswith(ext) for ext in SUPPORTED_EXTENSIONS):
            self.send_header('Content-Disposition', f'attachment; filename="{os.path.basename(self.path)}"')
        super().end_headers()

    def log_message(self, format, *args):
        log_msg = f"[{self.log_date_time_string()}] {format % args}"
        try:
            os.makedirs(LOG_DIR, exist_ok=True)
            with open(os.path.join(LOG_DIR, "server.log"), "a", encoding="utf-8") as f:
                f.write(log_msg + "\n")
        except Exception:
            pass


def run_scan():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Scanning: {ROOT_DIR}")
    items = scan_directory(ROOT_DIR)
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Found {len(items)} files")
    os.makedirs(DATA_DIR, exist_ok=True)
    data = {
        "scanDate": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "rootDir": ROOT_DIR, "totalFiles": len(items),
        "totalSize": sum(i["size"] for i in items),
        "totalSizeText": format_size(sum(i["size"] for i in items)),
        "items": items,
    }
    with open(JSON_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    html = generate_html(items, ROOT_DIR)
    with open(HTML_FILE, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Generated: {HTML_FILE}")
    return items


def run_server(port):
    socketserver.TCPServer.allow_reuse_address = True
    httpd = None
    for p in range(port, port + 20):
        try:
            httpd = socketserver.TCPServer(("", p), SoftwareHandler)
            port = p
            break
        except OSError:
            continue
    if httpd is None:
        print("ERROR: Cannot find available port!")
        return
    print(f"\n{'='*55}")
    print(f"  Software Library Server Running")
    print(f"  URL: http://0.0.0.0:{port}")
    print(f"  Root: {ROOT_DIR}")
    print(f"  Data: {DATA_DIR}")
    print(f"{'='*55}\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
        httpd.shutdown()


def watch_loop(interval):
    while True:
        time.sleep(interval)
        try:
            run_scan()
        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Rescan error: {e}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Software Library Scanner & Server")
    parser.add_argument("--scan-only", action="store_true")
    parser.add_argument("--no-scan", action="store_true")
    parser.add_argument("--port", type=int, default=PORT)
    parser.add_argument("--watch", action="store_true")
    args = parser.parse_args()
    os.makedirs(DATA_DIR, exist_ok=True)
    if not args.no_scan:
        run_scan()
    if args.scan_only:
        return
    if args.watch:
        t = threading.Thread(target=watch_loop, args=(WATCH_INTERVAL,), daemon=True)
        t.start()
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Auto-rescan enabled (every {WATCH_INTERVAL}s)")
    run_server(args.port)


if __name__ == "__main__":
    main()
