#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Software Library Manager v6
==========================
Scans NAS directory for software files, provides a searchable web UI
with user authentication, admin panel, file upload, remote URL fetch
(download-to-library) and download system.

Environment variables:
  LIB_ROOT_DIR       Root directory to scan (default: /data)
  LIB_PORT           Web server port (default: 8899)
  LIB_DATA_DIR       Generated files directory (default: /app/data)
  LIB_UPLOAD_DIR     Upload / fetched files directory (default: <LIB_DATA_DIR>/uploads)
  LIB_WATCH_INTERVAL Auto-rescan interval in seconds (default: 3600)

Only the Python standard library is required (no pip packages).
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
import urllib.request
from datetime import datetime

# ============================================================
# Configuration
# ============================================================

ROOT_DIR = os.environ.get("LIB_ROOT_DIR", "/data")
PORT = int(os.environ.get("LIB_PORT", "8899"))
DATA_DIR = os.environ.get("LIB_DATA_DIR", "/app/data")
UPLOAD_DIR = os.environ.get("LIB_UPLOAD_DIR", os.path.join(DATA_DIR, "uploads"))
WATCH_INTERVAL = int(os.environ.get("LIB_WATCH_INTERVAL", "3600"))

HTML_FILE = os.path.join(DATA_DIR, "index.html")
SCAN_FILE = os.path.join(DATA_DIR, "scan_result.json")
CONFIG_FILE = os.path.join(DATA_DIR, "config.json")
USERS_FILE = os.path.join(DATA_DIR, "users.json")
LOG_DIR = os.path.join(DATA_DIR, "logs")

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
              "config.json", "scan_result.json", "users.json", "server.log"}

MAX_UPLOAD_SIZE = 500 * 1024 * 1024         # 500MB (browser upload)
MAX_DOWNLOAD_SIZE = 2 * 1024 * 1024 * 1024  # 2GB (remote URL fetch)

UPLOAD_URL_PREFIX = "uploads/"  # web path prefix for files stored in UPLOAD_DIR

# ============================================================
# Software knowledge base (category / icon / desc only;
# display name is always the raw filename)
# ============================================================

SOFTWARE_DB = {
    "vmware": {"category": "虚拟化", "icon": "vmware", "desc": "VMware 虚拟机工作站", "official": "https://www.vmware.com"},
    "esxi": {"category": "虚拟化", "icon": "vmware", "desc": "VMware ESXi 裸机虚拟化系统", "official": "https://www.vmware.com/products/esxi-and-esx.html"},
    "proxmox": {"category": "虚拟化", "icon": "server", "desc": "开源虚拟化管理平台 (KVM/LXC)", "official": "https://www.proxmox.com"},
    "truenas": {"category": "NAS/存储", "icon": "nas", "desc": "开源 NAS 操作系统", "official": "https://www.truenas.com"},
    "fnos": {"category": "NAS/存储", "icon": "nas", "desc": "飞牛私有云 NAS 操作系统", "official": "https://www.fnos.com"},
    "windows": {"category": "操作系统", "icon": "windows", "desc": "Windows 系统镜像", "official": "https://www.microsoft.com/windows"},
    "esd": {"category": "操作系统", "icon": "windows", "desc": "Windows 系统镜像", "official": ""},
    "edrv8": {"category": "驱动", "icon": "driver", "desc": "Windows 驱动自动安装包", "official": ""},
    "wepe": {"category": "PE/维护", "icon": "wrench", "desc": "微PE工具箱，装机维护利器", "official": "https://www.wepe.com.cn"},
    "centos": {"category": "操作系统", "icon": "linux", "desc": "CentOS Linux 服务器系统", "official": "https://www.centos.org"},
    "debian": {"category": "操作系统", "icon": "linux", "desc": "Debian GNU/Linux 系统", "official": "https://www.debian.org"},
    "ubuntu": {"category": "操作系统", "icon": "linux", "desc": "Ubuntu 服务器系统", "official": "https://ubuntu.com"},
    "openwrt": {"category": "路由器/软路由", "icon": "router", "desc": "OpenWrt 软路由固件", "official": "https://openwrt.org"},
    "istoreos": {"category": "路由器/软路由", "icon": "router", "desc": "iStoreOS 软路由系统", "official": "https://www.istoreos.com"},
    "ikuai": {"category": "路由器/软路由", "icon": "router", "desc": "爱快流控路由系统", "official": "https://www.ikuai8.com"},
    "immortalwrt": {"category": "路由器/软路由", "icon": "router", "desc": "ImmortalWrt 软路由固件", "official": "https://immortalwrt.org"},
    "sql server": {"category": "数据库", "icon": "database", "desc": "Microsoft SQL Server", "official": "https://www.microsoft.com/sql-server"},
    "sqlserver": {"category": "数据库", "icon": "database", "desc": "Microsoft SQL Server", "official": "https://www.microsoft.com/sql-server"},
    "mysql": {"category": "数据库", "icon": "database", "desc": "MySQL 数据库", "official": "https://www.mysql.com"},
    "redis": {"category": "数据库", "icon": "database", "desc": "Redis 内存数据库", "official": "https://redis.io"},
    "office": {"category": "办公软件", "icon": "office", "desc": "Microsoft Office 办公套件", "official": "https://www.microsoft.com/microsoft-365"},
    "adobe": {"category": "设计/创意", "icon": "adobe", "desc": "Adobe 创意套件", "official": "https://www.adobe.com"},
    "acrobat": {"category": "设计/创意", "icon": "pdf", "desc": "Adobe Acrobat PDF 编辑器", "official": "https://www.adobe.com/acrobat.html"},
    "wps": {"category": "办公软件", "icon": "office", "desc": "WPS Office 办公套件", "official": "https://www.wps.cn"},
    "pycharm": {"category": "开发工具", "icon": "code", "desc": "PyCharm Python IDE", "official": "https://www.jetbrains.com/pycharm/"},
    "jdk": {"category": "开发工具", "icon": "java", "desc": "Java Development Kit", "official": "https://www.oracle.com/java/technologies/downloads/"},
    "python": {"category": "开发工具", "icon": "python", "desc": "Python 编程语言", "official": "https://www.python.org"},
    "navicat": {"category": "数据库", "icon": "database", "desc": "Navicat 数据库管理工具", "official": "https://www.navicat.com"},
    "mobaxterm": {"category": "开发工具", "icon": "terminal", "desc": "MobaXterm 终端工具", "official": "https://mobaxterm.mobatek.net"},
    "xshell": {"category": "开发工具", "icon": "terminal", "desc": "Xshell 终端模拟器", "official": "https://www.xshell.com"},
    "sublime": {"category": "开发工具", "icon": "code", "desc": "Sublime Text 代码编辑器", "official": "https://www.sublimetext.com"},
    "vscode": {"category": "开发工具", "icon": "code", "desc": "Visual Studio Code 编辑器", "official": "https://code.visualstudio.com"},
    "diskgenius": {"category": "系统工具", "icon": "disk", "desc": "DiskGenius 磁盘分区管理", "official": "https://www.diskgenius.com"},
    "ultraiso": {"category": "系统工具", "icon": "disk", "desc": "UltraISO 光盘镜像工具", "official": "https://www.ultraiso.com"},
    "winrar": {"category": "系统工具", "icon": "archive", "desc": "WinRAR 压缩解压工具", "official": "https://www.rarlab.com"},
    "7zip": {"category": "系统工具", "icon": "archive", "desc": "7-Zip 压缩工具", "official": "https://www.7-zip.org"},
    "rufus": {"category": "系统工具", "icon": "usb", "desc": "Rufus USB 启动盘制作", "official": "https://rufus.ie"},
    "etcher": {"category": "系统工具", "icon": "usb", "desc": "balenaEtcher 镜像写入", "official": "https://etcher.balena.io"},
    "geek": {"category": "系统工具", "icon": "trash", "desc": "Geek 卸载器", "official": "https://geekuninstaller.com"},
    "dism": {"category": "系统工具", "icon": "wrench", "desc": "Dism++ Windows 优化工具", "official": "http://www.chuyu.me"},
    "startallback": {"category": "系统工具", "icon": "windows", "desc": "StartAllBack Win11 开始菜单", "official": "https://www.startallback.com"},
    "easybcd": {"category": "系统工具", "icon": "wrench", "desc": "EasyBCD 引导管理", "official": "https://neosmart.net/EasyBCD/"},
    "clash": {"category": "网络/代理", "icon": "network", "desc": "Clash 代理客户端", "official": "https://github.com/Dreamacro/clash"},
    "v2ray": {"category": "网络/代理", "icon": "network", "desc": "V2Ray 代理客户端", "official": "https://www.v2ray.com"},
    "rustdesk": {"category": "远程控制", "icon": "remote", "desc": "RustDesk 远程桌面", "official": "https://rustdesk.com"},
    "todesk": {"category": "远程控制", "icon": "remote", "desc": "ToDesk 远程桌面", "official": "https://www.todesk.com"},
    "chrome": {"category": "浏览器", "icon": "browser", "desc": "Google Chrome 浏览器", "official": "https://www.google.com/chrome/"},
    "firefox": {"category": "浏览器", "icon": "browser", "desc": "Mozilla Firefox 浏览器", "official": "https://www.mozilla.org/firefox/"},
    "edge": {"category": "浏览器", "icon": "browser", "desc": "Microsoft Edge 浏览器", "official": "https://www.microsoft.com/edge"},
    "wallpaper engine": {"category": "媒体/娱乐", "icon": "media", "desc": "Wallpaper Engine 动态壁纸", "official": "https://www.wallpaperengine.io"},
    "potplayer": {"category": "媒体/娱乐", "icon": "media", "desc": "PotPlayer 视频播放器", "official": "https://potplayer.daum.net"},
    "pixpin": {"category": "系统工具", "icon": "screenshot", "desc": "PixPin 截图工具", "official": "https://pixpin.cn"},
    "snipaste": {"category": "系统工具", "icon": "screenshot", "desc": "Snipaste 截图工具", "official": "https://www.snipaste.com"},
    "everything": {"category": "系统工具", "icon": "search", "desc": "Everything 文件搜索", "official": "https://www.voidtools.com"},
    "heu": {"category": "激活工具", "icon": "key", "desc": "HEU KMS 激活工具", "official": ""},
    "virtio": {"category": "驱动", "icon": "driver", "desc": "VirtIO Windows 驱动", "official": "https://fedoraproject.org/wiki/Windows_Virtio_Drivers"},
}

CAT_ICON_MAP = {
    "操作系统": "windows", "虚拟化": "vmware", "NAS/存储": "nas", "路由器/软路由": "router",
    "数据库": "database", "开发工具": "code", "系统工具": "wrench", "网络/代理": "network",
    "浏览器": "browser", "办公软件": "office", "设计/创意": "adobe", "媒体/娱乐": "media",
    "远程控制": "remote", "激活工具": "key", "PE/维护": "wrench", "驱动": "driver", "其他": "box",
}

SVG_ICONS = {
    "vmware": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5M2 12l10 5 10-5"/></svg>',
    "server": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="3" width="20" height="6" rx="1"/><rect x="2" y="15" width="20" height="6" rx="1"/><line x1="6" y1="6" x2="6.01" y2="6"/><line x1="6" y1="18" x2="6.01" y2="18"/></svg>',
    "nas": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="4" width="18" height="16" rx="2"/><line x1="7" y1="8" x2="7" y2="8"/><line x1="7" y1="12" x2="7" y2="12"/><line x1="7" y1="16" x2="7" y2="16"/><line x1="11" y1="8" x2="17" y2="8"/><line x1="11" y1="12" x2="17" y2="12"/><line x1="11" y1="16" x2="17" y2="16"/></svg>',
    "windows": '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M3 5.5l8.5-1.2v8.2H3V5.5zm0 13l8.5 1.2v-8.2H3v7zm9.5 1.3L21 21V13h-8.5v6.8zm0-15.6V11H21V3l-8.5 1.2z"/></svg>',
    "linux": '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 2C9 2 8 4 8 6c0 1-1 2-1.5 3.5C6 11 6 12 7 13c.5.5 1 2 1 3 0 1.5-1 2-1 3 0 .5.5 1 1.5 1s2-1 3.5-1 2.5 1 3.5 1 1.5-.5 1.5-1c0-1-1-1.5-1-3 0-1 .5-2.5 1-3 1-1 1-2-.5-3.5C15 8 14 7 14 6c0-2-1-4-2-4z"/></svg>',
    "router": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="14" width="20" height="7" rx="1"/><line x1="6" y1="17.5" x2="6.01" y2="17.5"/><line x1="10" y1="17.5" x2="10.01" y2="17.5"/><path d="M12 14V8M8 8a4 4 0 018 0"/></svg>',
    "database": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5v6c0 1.7 4 3 9 3s9-1.3 9-3V5"/><path d="M3 11v6c0 1.7 4 3 9 3s9-1.3 9-3v-6"/></svg>',
    "office": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><line x1="3" y1="9" x2="21" y2="9"/><line x1="9" y1="21" x2="9" y2="9"/></svg>',
    "adobe": '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M3 3h5l4 8 4-8h5v18h-5v-8l-4 8-4-8v8H3z" opacity="0.9"/></svg>',
    "pdf": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><path d="M14 2v6h6"/></svg>',
    "code": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>',
    "java": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M8 18c-2 0-3-1-3-2 0-1 1-2 4-2v2c0 1 .5 2 1 2z"/><path d="M11 15c-4-1-5-3-5-5 0-2 3-3 6-3v2c-2 0-3 .5-3 1.5S10 12 13 13"/><path d="M14 12c4-1 5-3 5-5 0-2-3-3-6-3v2c2 0 3 .5 3 1.5S16 9 13 10"/></svg>',
    "python": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2c-3 0-5 1-5 3v2h5v1H5c-2 0-3 2-3 4s1 4 3 4h2v-2c0-2 2-3 4-3h3c2 0 3-1 3-3V5c0-2-2-3-5-3z"/><circle cx="9" cy="4.5" r="0.5" fill="currentColor"/></svg>',
    "terminal": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/></svg>',
    "disk": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="3"/></svg>',
    "archive": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="21 8 21 21 3 21 3 8"/><rect x="1" y="3" width="22" height="5"/><line x1="10" y1="12" x2="14" y2="12"/></svg>',
    "usb": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="4" r="2"/><path d="M12 6v6"/><path d="M9 12h6"/><path d="M12 12v8a2 2 0 002 2 2 2 0 002-2"/></svg>',
    "trash": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/></svg>',
    "wrench": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14.7 6.3a4 4 0 00-5.4 5.4L3 18l3 3 6.3-6.3a4 4 0 005.4-5.4l-2.5 2.5-2.5-.5-.5-2.5 2.5-2.5z"/></svg>',
    "network": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15 15 0 010 20M12 2a15 15 0 000 20"/></svg>',
    "remote": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="4" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="18" x2="12" y2="21"/></svg>',
    "browser": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15 15 0 010 20M12 2a15 15 0 000 20"/></svg>',
    "media": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="23 7 16 12 23 17 23 7"/><rect x="1" y="5" width="15" height="14" rx="2"/></svg>',
    "screenshot": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M23 19a2 2 0 01-2 2H3a2 2 0 01-2-2V8a2 2 0 012-2h4l2-3h6l2 3h4a2 2 0 012 2z"/><circle cx="12" cy="13" r="4"/></svg>',
    "key": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 2l-2 2m-7.5 7.5a5 5 0 11-7 7 5 5 0 017-7zm0 0L21 2m-9.5 9.5l5 5"/></svg>',
    "lock": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0110 0v4"/></svg>',
    "driver": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="6" width="20" height="12" rx="2"/><line x1="6" y1="10" x2="6" y2="10"/><line x1="6" y1="14" x2="6" y2="14"/><line x1="10" y1="10" x2="18" y2="10"/><line x1="10" y1="14" x2="18" y2="14"/></svg>',
    "box": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 8l-9-5-9 5v8l9 5 9-5V8z"/><path d="M3 8l9 5 9-5M12 13v8"/></svg>',
    "download": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>',
    "upload": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>',
    "link": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10 13a5 5 0 007 0l3-3a5 5 0 00-7-7l-1 1"/><path d="M14 11a5 5 0 00-7 0l-3 3a5 5 0 007 7l1-1"/></svg>',
    "copy": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/></svg>',
    "refresh": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15"/></svg>',
    "folder": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z"/></svg>',
    "file": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M13 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V9z"/><polyline points="13 2 13 9 20 9"/></svg>',
    "search": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>',
    "package": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="16.5" y1="5.5" x2="7.5" y2="14.5"/><polygon points="21 8 21 21 3 21 3 8 12 1 21 8"/><polyline points="3 8 12 13 21 8"/></svg>',
    "edit": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>',
    "plus": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>',
    "back": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/></svg>',
    "external": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>',
    "chevron": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"/></svg>',
    "layers": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/></svg>',
    "settings": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-2 2 2 2 0 01-2-2v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83 0 2 2 0 010-2.83l.06-.06a1.65 1.65 0 00.33-1.82 1.65 1.65 0 00-1.51-1H3a2 2 0 01-2-2 2 2 0 012-2h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 010-2.83 2 2 0 012.83 0l.06.06a1.65 1.65 0 001.82.33H9a1.65 1.65 0 001-1.51V3a2 2 0 012-2 2 2 0 012 2v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 0 2 2 0 010 2.83l-.06.06a1.65 1.65 0 00-.33 1.82V9a1.65 1.65 0 001.51 1H21a2 2 0 012 2 2 2 0 01-2 2h-.09a1.65 1.65 0 00-1.51 1z"/></svg>',
    "user": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>',
    "users": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 00-3-3.87M16 3.13a4 4 0 010 7.75"/></svg>',
    "logout": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>',
    "save": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 21H5a2 2 0 01-2-2V5a2 2 0 012-2h11l5 5v11a2 2 0 01-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/></svg>',
    "close": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>',
    "menu": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/></svg>',
    "cloud-download": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="16 13 16 22 8 22 8 13"/><path d="M20.35 17.35A4 4 0 0018 10h-1.26A8 8 0 103 16.3"/><polyline points="16 13 12 17 8 13"/></svg>',
}


def get_svg(name):
    return SVG_ICONS.get(name, SVG_ICONS["box"])

# ============================================================
# User authentication
# ============================================================

def hash_password(password):
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def load_users():
    data = load_json(USERS_FILE, None)
    if data is None:
        return {"users": []}
    return data


def save_users(users_data):
    save_json(USERS_FILE, users_data)


def has_users():
    users = load_users()
    return len(users.get("users", [])) > 0


def find_user(username):
    users = load_users()
    for u in users.get("users", []):
        if u.get("username") == username:
            return u
    return None


def create_user(username, password, role="user"):
    if len(username) < 2 or len(password) < 3:
        return False, "用户名至少2位，密码至少3位"
    users = load_users()
    if any(u.get("username") == username for u in users.get("users", [])):
        return False, "用户名已存在"
    users["users"].append({
        "username": username,
        "password": hash_password(password),
        "role": role,
        "created": datetime.now().strftime("%Y-%m-%d %H:%M"),
    })
    save_users(users)
    return True, "创建成功"


def verify_user(username, password):
    u = find_user(username)
    if not u:
        return False, "用户不存在"
    if u.get("password") != hash_password(password):
        return False, "密码错误"
    return True, u


def delete_user(username):
    users = load_users()
    before = len(users.get("users", []))
    users["users"] = [u for u in users.get("users", []) if u.get("username") != username]
    if len(users["users"]) < before:
        save_users(users)
        return True, "已删除"
    return False, "用户不存在"


# Simple in-memory session store: token -> {username, role}
_sessions = {}


def create_session(username, role):
    token = uuid.uuid4().hex
    _sessions[token] = {"username": username, "role": role, "time": time.time()}
    return token


def get_session(token):
    if not token:
        return None
    s = _sessions.get(token)
    if not s:
        return None
    if time.time() - s["time"] > 7 * 86400:  # session valid for 7 days
        _sessions.pop(token, None)
        return None
    return s


def destroy_session(token):
    _sessions.pop(token, None)

# ============================================================
# Software matching (strict, word-boundary based)
# ============================================================

def _key_match(key, text):
    """Match on word boundaries so e.g. 'git' no longer matches 'DigitalEdition'."""
    k = re.escape(key.lower())
    return re.search(r"(?<![a-z0-9])" + k + r"(?![a-z0-9])", text)


def match_software(filename, dirpath):
    """Return (category, icon, desc, official). Display name is always the filename."""
    lower = filename.lower()
    parent = os.path.basename(dirpath).lower()
    search_str = lower + " " + parent

    for key, info in SOFTWARE_DB.items():
        if _key_match(key, search_str):
            return info["category"], info["icon"], info["desc"], info.get("official", "")

    if "vmware" in search_str and _key_match("tools", search_str):
        return "虚拟化", "vmware", "VMware Tools 驱动包", ""
    if _key_match("keygen", lower) or "注册机" in lower:
        return "激活工具", "key", "注册/激活工具", ""
    if _key_match("patch", lower) or "补丁" in lower or _key_match("crack", lower):
        return "激活工具", "key", "软件补丁", ""
    if _key_match("winpe", lower) or _key_match("pe", parent):
        return "PE/维护", "wrench", "PE 维护工具", ""

    ext = os.path.splitext(filename)[1].lower()
    ext_icons = {".exe": "box", ".msi": "box", ".iso": "disk", ".img": "disk", ".zip": "archive",
                 ".7z": "archive", ".rar": "archive", ".gz": "archive", ".apk": "box",
                 ".dmg": "disk", ".vmdk": "disk", ".ova": "box", ".ovf": "box", ".wim": "disk"}
    return "其他", ext_icons.get(ext, "file"), "", ""


def format_size(size_bytes):
    if size_bytes == 0:
        return "0 B"
    size = float(size_bytes)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
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

# ============================================================
# Scanner
# ============================================================

def _scan_tree(base_dir, items, seen, url_prefix):
    exts = set(SUPPORTED_EXTENSIONS.keys())
    compound_exts = [".tar.gz", ".tar.xz"]
    for dirpath, dirnames, filenames in os.walk(base_dir):
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
            relpath = os.path.relpath(fullpath, base_dir).replace("\\", "/")
            webpath = url_prefix + relpath if url_prefix else relpath
            if webpath in seen:
                continue
            seen.add(webpath)
            category, icon, desc, official = match_software(filename, dirpath)
            items.append({
                "name": filename,  # display name = raw filename
                "filename": filename,
                "category": category,
                "icon": icon,
                "desc": desc,
                "official": official,
                "size": size,
                "sizeText": format_size(size),
                "ext": matched_ext,
                "fileType": SUPPORTED_EXTENSIONS.get(matched_ext, "FILE"),
                "date": get_file_date(fullpath),
                "path": webpath,
            })


def scan_directory():
    """Scan ROOT_DIR plus UPLOAD_DIR (uploads live outside the read-only share)."""
    items = []
    seen = set()
    _scan_tree(ROOT_DIR, items, seen, "")
    if os.path.isdir(UPLOAD_DIR):
        try:
            real_upload = os.path.realpath(UPLOAD_DIR)
            real_root = os.path.realpath(ROOT_DIR)
            if not real_upload.startswith(real_root + os.sep) and real_upload != real_root:
                _scan_tree(UPLOAD_DIR, items, seen, UPLOAD_URL_PREFIX)
        except Exception:
            pass
    items.sort(key=lambda x: (x["category"], x["name"].lower()))
    return items

# ============================================================
# Data layer
# ============================================================

def load_json(filepath, default):
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json(filepath, data):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def default_config():
    return {"software": {}, "version": 2}


def run_scan():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Scanning: {ROOT_DIR} + {UPLOAD_DIR}")
    items = scan_directory()
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Found {len(items)} files")
    os.makedirs(DATA_DIR, exist_ok=True)
    data = {
        "scanDate": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "rootDir": ROOT_DIR,
        "totalFiles": len(items),
        "totalSize": sum(i["size"] for i in items),
        "totalSizeText": format_size(sum(i["size"] for i in items)),
        "items": items,
    }
    save_json(SCAN_FILE, data)
    return items


def build_entry_list():
    """One flat entry per file; overrides are keyed by web path."""
    scan_data = load_json(SCAN_FILE, {"items": []})
    config = load_json(CONFIG_FILE, default_config())
    overrides = config.get("software", {})

    entries = []
    for item in scan_data.get("items", []):
        entry = {
            "name": item["filename"],
            "filename": item["filename"],
            "category": item["category"],
            "icon": item["icon"],
            "desc": item["desc"],
            "official": item.get("official", ""),
            "customOfficial": "",
            "showOfficial": False,
            "size": item["size"],
            "sizeText": item["sizeText"],
            "fileType": item.get("fileType", ""),
            "date": item.get("date", ""),
            "path": item["path"],
        }
        cfg = overrides.get(item["path"], {})
        for key in ("category", "icon", "desc", "official", "customOfficial", "showOfficial"):
            if key in cfg:
                entry[key] = cfg[key]
        entries.append(entry)
    return entries


def refresh_library():
    """Rescan + regenerate index.html (blocking; callers hold _scan_lock)."""
    global _last_scan_time
    with _scan_lock:
        try:
            run_scan()
            html = generate_html()
            with open(HTML_FILE, "w", encoding="utf-8") as f:
                f.write(html)
            _last_scan_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        except Exception as e:
            print(f"Refresh error: {e}")


def refresh_library_async():
    if _scan_lock.locked():
        return
    threading.Thread(target=refresh_library, daemon=True).start()

# ============================================================
# Remote URL fetch (download-to-library)
# ============================================================

_fetch_lock = threading.Lock()
_fetch_status = {"active": False, "message": ""}


def _filename_from_response(resp, url, custom_name):
    if custom_name:
        name = custom_name.strip()
    else:
        name = ""
        cd = resp.headers.get("Content-Disposition") or ""
        m = re.search(r"filename\*\s*=\s*UTF-8''([^;]+)", cd, re.I) or \
            re.search(r'filename\s*=\s*"?([^";]+)"?', cd, re.I)
        if m:
            try:
                name = urllib.parse.unquote(m.group(1).strip().strip('"'))
            except Exception:
                name = m.group(1).strip().strip('"')
        if not name:
            name = os.path.basename(urllib.parse.urlparse(url).path)
    name = os.path.basename(name.replace("\\", "/").replace("\x00", ""))
    return name or "download.bin"


def fetch_remote_file(url, custom_name=None):
    """Download a remote file into UPLOAD_DIR so it stays in the library."""
    global _fetch_status
    with _fetch_lock:
        _fetch_status = {"active": True, "message": "正在连接..."}
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (compatible; software-library/6.0)"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                total = int(resp.headers.get("Content-Length") or 0)
                if total and total > MAX_DOWNLOAD_SIZE:
                    raise Exception(f"文件超过大小限制 ({format_size(MAX_DOWNLOAD_SIZE)})")
                fname = _filename_from_response(resp, url, custom_name)
                os.makedirs(UPLOAD_DIR, exist_ok=True)
                dest = os.path.join(UPLOAD_DIR, fname)
                base, ext = os.path.splitext(fname)
                i = 1
                while os.path.exists(dest):
                    dest = os.path.join(UPLOAD_DIR, f"{base}({i}){ext}")
                    i += 1
                done = 0
                with open(dest, "wb") as f:
                    while True:
                        chunk = resp.read(256 * 1024)
                        if not chunk:
                            break
                        done += len(chunk)
                        if done > MAX_DOWNLOAD_SIZE:
                            raise Exception(f"文件超过大小限制 ({format_size(MAX_DOWNLOAD_SIZE)})")
                        f.write(chunk)
                        if total:
                            _fetch_status["message"] = f"下载中 {done * 100 // total}% ({format_size(done)})"
                        else:
                            _fetch_status["message"] = f"下载中 ({format_size(done)})"
            saved = os.path.basename(dest)
            _fetch_status["message"] = f"已下载 {saved}，正在更新软件库..."
            refresh_library()
            _fetch_status = {"active": False, "message": f"完成: {saved} 已入库"}
        except Exception as e:
            _fetch_status = {"active": False, "message": f"失败: {e}"}

# ============================================================
# HTML generator (SPA)
# ============================================================

def generate_html():
    entries = build_entry_list()
    categories = {}
    for e in entries:
        categories[e["category"]] = categories.get(e["category"], 0) + 1

    total_files = len(entries)
    total_size = sum(e["size"] for e in entries)
    total_size_text = format_size(total_size)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    has_registered_users = has_users()

    all_icons = {}
    wanted = set(list(CAT_ICON_MAP.values()) + [e["icon"] for e in entries] + [
        "download", "upload", "cloud-download", "link", "refresh", "search", "package",
        "edit", "plus", "back", "external", "chevron", "settings", "file", "folder",
        "layers", "user", "users", "logout", "save", "close", "lock", "box", "menu", "key"])
    for name in wanted:
        all_icons[name] = SVG_ICONS.get(name, SVG_ICONS["box"])

    icons_json = json.dumps(all_icons, ensure_ascii=False)
    cat_icons_json = json.dumps(CAT_ICON_MAP, ensure_ascii=False)

    # ---- CSS (plain string, no f-string) ----
    css = """<style>
:root{
--bg:#f5f6f8;--bg-card:#fff;--bg-search:#eef0f3;--text:#1a1d28;--text-dim:#6b7280;
--text-bright:#111827;--accent:#4f7cff;--accent-glow:rgba(79,124,255,0.15);
--accent-soft:rgba(79,124,255,0.08);--border:#e0e3eb;--border-bright:#c8ccd6;
--radius:12px;--green:#16a34a;--orange:#d97706;--red:#dc2626;
--shadow:0 2px 12px rgba(0,0,0,0.06);--shadow-lg:0 4px 24px rgba(0,0,0,0.08);
--purple:#534AB7;--purple-soft:#EEEDFE;
}
*{margin:0;padding:0;box-sizing:border-box;}
html,body{max-width:100%;overflow-x:hidden;}
body{font-family:-apple-system,'Segoe UI','Microsoft YaHei',sans-serif;background:var(--bg);color:var(--text);line-height:1.6;min-height:100vh;}
.header{position:sticky;top:0;z-index:100;background:rgba(255,255,255,0.92);backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px);border-bottom:1px solid var(--border);padding:10px 0;}
.header-inner{max-width:1400px;margin:0 auto;padding:0 16px;display:flex;align-items:center;gap:10px;flex-wrap:wrap;}
.logo{display:flex;align-items:center;gap:10px;flex-shrink:0;cursor:pointer;}
.logo-icon{width:36px;height:36px;border-radius:8px;background:linear-gradient(135deg,var(--accent),#6b5cff);display:flex;align-items:center;justify-content:center;box-shadow:var(--shadow);}
.logo-icon svg{width:18px;height:18px;color:#fff;}
.logo-text h1{font-size:16px;color:var(--text-bright);font-weight:700;}
.search-box{flex:1;min-width:160px;position:relative;}
.search-box input{width:100%;padding:8px 12px 8px 34px;background:var(--bg-search);border:1px solid var(--border);border-radius:8px;color:var(--text);font-size:13px;transition:all 0.2s;}
.search-box input:focus{outline:none;border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-glow);}
.search-box .search-icon{position:absolute;left:10px;top:50%;transform:translateY(-50%);color:var(--text-dim);display:flex;align-items:center;}
.search-box .search-icon svg{width:14px;height:14px;}
.cat-filter{flex-shrink:0;}
.cat-filter select{padding:7px 10px;border-radius:8px;border:1px solid var(--border);background:var(--bg-card);color:var(--text);font-size:12px;cursor:pointer;outline:none;max-width:170px;}
.cat-filter select:focus{border-color:var(--accent);}
.stats{display:flex;gap:14px;flex-shrink:0;}
.stat-item{text-align:center;}
.stat-item .num{font-size:14px;font-weight:700;color:var(--accent);}
.stat-item .label{font-size:9px;color:var(--text-dim);}
.header-btns{display:flex;gap:4px;flex-shrink:0;}
.header-btn{display:inline-flex;align-items:center;gap:4px;padding:6px 10px;border-radius:6px;font-size:12px;font-weight:500;cursor:pointer;background:var(--bg-card);border:1px solid var(--border-bright);color:var(--text-dim);transition:all 0.15s;text-decoration:none;white-space:nowrap;}
.header-btn:hover{border-color:var(--accent);color:var(--accent);}
.header-btn.primary{background:var(--accent);color:#fff;border-color:var(--accent);}
.header-btn.primary:hover{background:#3a6aff;color:#fff;}
.dropdown{position:relative;display:inline-block;}
.dropdown-menu{display:none;position:absolute;right:0;top:100%;min-width:170px;background:var(--bg-card);border:1px solid var(--border);border-radius:8px;box-shadow:var(--shadow-lg);z-index:200;padding:4px 0;margin-top:4px;}
.dropdown-menu.show{display:block;}
.dropdown-menu button{display:flex;align-items:center;gap:8px;padding:8px 16px;font-size:13px;color:var(--text);background:none;border:none;width:100%;text-align:left;cursor:pointer;transition:background 0.1s;}
.dropdown-menu button:hover{background:var(--accent-soft);color:var(--accent);}
.dropdown-menu .divider{height:1px;background:var(--border);margin:4px 0;}
.container{max-width:1400px;margin:0 auto;padding:16px;}
.section{margin-bottom:24px;}
.section-header{display:flex;align-items:center;gap:8px;margin-bottom:12px;padding-bottom:6px;border-bottom:1px solid var(--border);flex-wrap:wrap;}
.section-header h2{font-size:15px;color:var(--text-bright);}
.section-header .cat-icon{color:var(--accent);display:flex;align-items:center;}
.section-header .cat-icon svg{width:18px;height:18px;}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:12px;}
.card{background:var(--bg-card);border:1px solid var(--border);border-radius:var(--radius);padding:14px;transition:all 0.2s;display:flex;flex-direction:column;gap:8px;box-shadow:var(--shadow);cursor:pointer;animation:fadeIn 0.25s ease-out;}
.card:hover{border-color:var(--border-bright);box-shadow:var(--shadow-lg);transform:translateY(-1px);}
.card-top{display:flex;align-items:flex-start;gap:10px;}
.card-icon{width:40px;height:40px;border-radius:8px;background:var(--bg-search);display:flex;align-items:center;justify-content:center;flex-shrink:0;color:var(--accent);}
.card-icon svg{width:20px;height:20px;}
.card-info{flex:1;min-width:0;}
.card-title{font-size:13px;font-weight:600;color:var(--text-bright);word-break:break-all;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;line-height:1.4;}
.card-desc{font-size:11px;color:var(--text-dim);margin-top:2px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
.card-meta{display:flex;flex-wrap:wrap;gap:4px;font-size:10px;}
.meta-tag{display:inline-flex;align-items:center;gap:2px;padding:1px 6px;border-radius:3px;background:rgba(0,0,0,0.03);}
.meta-tag.type{color:var(--orange);}
.meta-tag.size{color:var(--green);}
.meta-tag.date{color:var(--text-dim);}
.card-footer{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-top:2px;flex-wrap:wrap;}
.no-results{text-align:center;padding:40px 16px;color:var(--text-dim);}
.footer{text-align:center;padding:16px;color:var(--text-dim);font-size:11px;border-top:1px solid var(--border);margin-top:24px;}
.btn{display:inline-flex;align-items:center;justify-content:center;gap:4px;padding:6px 14px;border-radius:6px;font-size:12px;font-weight:500;cursor:pointer;text-decoration:none;transition:all 0.15s;border:none;}
.btn svg{width:14px;height:14px;}
.btn-download{background:var(--accent);color:#fff;}
.btn-download:hover{background:#3a6aff;}
.btn-official{background:transparent;border:1px solid var(--green);color:var(--green);}
.btn-official:hover{background:rgba(22,163,74,0.08);}
.btn-external{background:transparent;border:1px solid var(--purple);color:var(--purple);}
.btn-external:hover{background:var(--purple-soft);}
.btn-back{background:transparent;border:1px solid var(--border-bright);color:var(--text-dim);}
.btn-back:hover{border-color:var(--accent);color:var(--accent);}
.btn-primary{background:var(--accent);color:#fff;}
.btn-primary:hover{background:#3a6aff;}
.btn-danger{background:transparent;border:1px solid var(--red);color:var(--red);}
.btn-danger:hover{background:rgba(220,38,38,0.08);}
.btn:disabled{opacity:0.5;cursor:not-allowed;}
.btn-sm{padding:4px 8px;font-size:11px;}
.btn-xs{padding:2px 6px;font-size:10px;}
@keyframes fadeIn{from{opacity:0;transform:translateY(6px);}to{opacity:1;transform:translateY(0);}}
::-webkit-scrollbar{width:6px;height:6px;}
::-webkit-scrollbar-track{background:transparent;}
::-webkit-scrollbar-thumb{background:var(--border-bright);border-radius:3px;}
.toast{position:fixed;bottom:24px;left:50%;transform:translateX(-50%);background:#1a1d28;color:#fff;padding:8px 20px;border-radius:6px;font-size:13px;z-index:9999;opacity:0;transition:opacity 0.3s;box-shadow:0 4px 12px rgba(0,0,0,0.2);}
.toast.show{opacity:1;}
.modal-overlay{position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.4);z-index:2000;display:flex;align-items:center;justify-content:center;}
.modal{background:var(--bg-card);border-radius:12px;padding:24px;max-width:420px;width:90%;box-shadow:var(--shadow-lg);max-height:90vh;overflow-y:auto;}
.modal h2{font-size:18px;color:var(--text-bright);margin-bottom:16px;display:flex;align-items:center;gap:8px;}
.modal h2 svg{width:20px;height:20px;color:var(--accent);}
.form-group{margin-bottom:12px;}
.form-group label{display:block;font-size:12px;color:var(--text-dim);margin-bottom:4px;}
.form-group input,.form-group select{width:100%;padding:8px 12px;border:1px solid var(--border);border-radius:6px;font-size:13px;color:var(--text);outline:none;transition:all 0.2s;background:var(--bg-card);}
.form-group input:focus{border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-glow);}
.modal-btns{display:flex;gap:8px;margin-top:16px;}
.modal-error{color:var(--red);font-size:12px;margin-bottom:8px;display:none;}
.admin-wrap{max-width:1000px;margin:0 auto;}
.admin-back{margin-bottom:14px;}
.admin-section{background:var(--bg-card);border:1px solid var(--border);border-radius:var(--radius);padding:16px;margin-bottom:16px;box-shadow:var(--shadow);}
.admin-section h3{font-size:14px;color:var(--text-bright);margin-bottom:4px;display:flex;align-items:center;gap:6px;}
.admin-section h3 svg{width:16px;height:16px;color:var(--purple);}
.admin-section .section-desc{font-size:11px;color:var(--text-dim);margin-bottom:12px;}
.admin-toolbar{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px;}
.admin-toolbar input{flex:1;min-width:160px;padding:7px 10px;border:1px solid var(--border);border-radius:6px;font-size:12px;outline:none;background:var(--bg-card);color:var(--text);}
.admin-toolbar input:focus{border-color:var(--accent);}
.url-rows{max-height:420px;overflow-y:auto;border:1px solid var(--border);border-radius:8px;padding:0 10px;}
.edit-row{display:grid;grid-template-columns:minmax(120px,1.2fr) minmax(160px,2fr) auto;gap:6px;align-items:center;padding:8px 0;border-bottom:1px solid var(--border);}
.edit-row:last-child{border-bottom:none;}
.edit-row .row-name{font-size:12px;font-weight:500;color:var(--text-bright);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
.edit-row input{width:100%;min-width:0;padding:5px 8px;border:1px solid var(--border);border-radius:4px;font-size:12px;outline:none;}
.edit-row input:focus{border-color:var(--accent);}
.edit-row .row-btns{display:flex;gap:4px;flex-wrap:wrap;}
.user-row{display:flex;align-items:center;gap:10px;padding:8px 0;border-bottom:1px solid var(--border);flex-wrap:wrap;}
.user-row:last-child{border-bottom:none;}
.user-row .user-info{flex:1;min-width:120px;}
.user-row .user-name{font-size:13px;font-weight:500;color:var(--text-bright);}
.user-row .user-role{font-size:11px;color:var(--text-dim);}
.role-badge{display:inline-block;padding:1px 6px;border-radius:3px;font-size:10px;font-weight:500;}
.role-badge.admin{background:var(--purple-soft);color:var(--purple);}
.role-badge.user{background:var(--accent-soft);color:var(--accent);}
.upload-area{border:2px dashed var(--border-bright);border-radius:10px;padding:30px;text-align:center;cursor:pointer;transition:all 0.2s;}
.upload-area:hover{border-color:var(--accent);background:var(--accent-soft);}
.upload-area svg{width:32px;height:32px;color:var(--text-dim);margin-bottom:8px;}
.upload-area p{color:var(--text-dim);font-size:13px;}
.progress-bar{width:100%;height:4px;background:var(--bg-search);border-radius:2px;overflow:hidden;}
.progress-fill{height:100%;background:var(--accent);transition:width 0.3s;}
.fetch-status{font-size:12px;color:var(--text-dim);margin-top:8px;display:none;align-items:center;gap:6px;}
.fetch-status.show{display:flex;}
@media(max-width:900px){.stats{display:none;}}
@media(max-width:768px){
.header-inner{flex-direction:column;align-items:stretch;}
.search-box{min-width:0;}
.cat-filter select{max-width:100%;}
.grid{grid-template-columns:1fr;}
.edit-row{grid-template-columns:1fr;}
}
</style>"""

    # ---- HTML body ----
    body = f"""</head>
<body>
<div class="header"><div class="header-inner">
  <div class="logo" onclick="goHome()"><div class="logo-icon">{get_svg("package")}</div><div class="logo-text"><h1>软件库</h1></div></div>
  <div class="search-box"><span class="search-icon">{get_svg("search")}</span><input type="text" id="searchInput" placeholder="搜索文件名..." autocomplete="off" oninput="onSearch(this.value)"></div>
  <div class="cat-filter">
    <select id="catSelect" onchange="selectCategory(this.value)"><option value="all">全部分类 ({len(categories)})</option></select>
  </div>
  <div class="stats"><div class="stat-item"><div class="num" id="statCount">{total_files}</div><div class="label">文件</div></div><div class="stat-item"><div class="num">{len(categories)}</div><div class="label">分类</div></div><div class="stat-item"><div class="num">{total_size_text}</div><div class="label">总量</div></div></div>
  <div class="header-btns" id="headerBtns"></div>
</div></div>
<div class="container" id="container"></div>
<div class="footer"><p>软件库 · 共 {total_files} 个文件 · 总计 {total_size_text}</p><p style="margin-top:2px;">最后更新: {now_str}</p></div>
<div id="modalContainer"></div>
"""

    # ---- JS (plain string with placeholders, no f-string) ----
    js = """<script>
const ICONS=__ICONS_JSON__;
const CAT_ICONS=__CAT_ICONS_JSON__;
const HAS_USERS=__HAS_USERS__;
let SESSION=null;
let ENTRIES=[];
let currentView='home',searchTerm='',currentCat='all';
let pollingFetch=false;

function svg(n,s){const v=ICONS[n]||ICONS['box'];return '<span style="width:'+(s||26)+'px;height:'+(s||26)+'px;display:inline-flex;align-items:center;justify-content:center;flex-shrink:0">'+v+'</span>';}
function esc(s){const d=document.createElement('div');d.textContent=s==null?'':String(s);return d.innerHTML;}
function showToast(msg){let t=document.getElementById('toast');if(!t){t=document.createElement('div');t.id='toast';t.className='toast';document.body.appendChild(t);}t.textContent=msg;t.classList.add('show');clearTimeout(t._timer);t._timer=setTimeout(()=>t.classList.remove('show'),2500);}

function getCookie(n){const m=document.cookie.match(new RegExp('(^| )'+n+'=([^;]+)'));return m?m[2]:'';}
function setCookie(n,v,d){const e=new Date();e.setTime(e.getTime()+d*86400000);document.cookie=n+'='+v+';expires='+e.toUTCString()+';path=/';}
function delCookie(n){document.cookie=n+'=;expires=Thu,01 Jan 1970 00:00:00 UTC;path=/';}

async function api(url,opts){
  opts=opts||{};
  opts.headers=opts.headers||{};
  if(SESSION)opts.headers['X-Session']=SESSION.token;
  if(opts.body&&typeof opts.body==='object'){opts.headers['Content-Type']='application/json';opts.body=JSON.stringify(opts.body);}
  const r=await fetch(url,opts);
  return r.json();
}

function renderHeaderBtns(){
  const c=document.getElementById('headerBtns');
  if(!SESSION){
    if(HAS_USERS){
      c.innerHTML='<button class="header-btn" onclick="showLogin()">'+svg('lock',12)+' 登录</button>';
    }else{
      c.innerHTML='<button class="header-btn primary" onclick="showRegister()">'+svg('user',12)+' 注册管理员</button>';
    }
    return;
  }
  let h='<div class="dropdown" id="userDropdown">';
  h+='<button class="header-btn" onclick="toggleDropdown()">'+svg('user',12)+' '+esc(SESSION.username)+' '+svg('chevron',10)+'</button>';
  h+='<div class="dropdown-menu" id="dropdownMenu">';
  h+='<button onclick="doUpload()">'+svg('upload',12)+' 上传文件</button>';
  if(SESSION.role==='admin'){
    h+='<button onclick="goAdmin()">'+svg('settings',12)+' 管理面板</button>';
  }
  h+='<div class="divider"></div>';
  h+='<button onclick="doLogout()" style="color:var(--red)">'+svg('logout',12)+' 退出登录</button>';
  h+='</div></div>';
  c.innerHTML=h;
}

function toggleDropdown(){
  const m=document.getElementById('dropdownMenu');
  if(m)m.classList.toggle('show');
}
document.addEventListener('click',function(e){
  const d=document.getElementById('userDropdown');
  if(d&&!d.contains(e.target)){const m=document.getElementById('dropdownMenu');if(m)m.classList.remove('show');}
});

function showLogin(){
  const mc=document.getElementById('modalContainer');
  mc.innerHTML='<div class="modal-overlay" onclick="if(event.target===this)closeModal()"><div class="modal"><h2>'+svg('lock',20)+' 登录</h2><div class="modal-error" id="loginErr"></div><div class="form-group"><label>用户名</label><input type="text" id="loginUser" placeholder="输入用户名" autocomplete="username"></div><div class="form-group"><label>密码</label><input type="password" id="loginPass" placeholder="输入密码" autocomplete="current-password" onkeydown="if(event.key===\\'Enter\\')doLogin()"></div><div class="modal-btns"><button class="btn btn-primary" style="flex:1" onclick="doLogin()">'+svg('lock',12)+' 登录</button><button class="btn btn-back" onclick="closeModal()">取消</button></div></div></div>';
  setTimeout(()=>{const i=document.getElementById('loginUser');if(i)i.focus();},100);
}
function showRegister(){
  const mc=document.getElementById('modalContainer');
  mc.innerHTML='<div class="modal-overlay" onclick="if(event.target===this)closeModal()"><div class="modal"><h2>'+svg('user',20)+' 注册管理员</h2><p style="font-size:12px;color:var(--text-dim);margin-bottom:12px;">首次使用，创建的账号将作为管理员。之后可在管理面板中添加普通账户。</p><div class="modal-error" id="regErr"></div><div class="form-group"><label>用户名</label><input type="text" id="regUser" placeholder="创建用户名"></div><div class="form-group"><label>密码</label><input type="password" id="regPass" placeholder="创建密码（至少3位）"></div><div class="form-group"><label>确认密码</label><input type="password" id="regPass2" placeholder="再次输入密码" onkeydown="if(event.key===\\'Enter\\')doRegister()"></div><div class="modal-btns"><button class="btn btn-primary" style="flex:1" onclick="doRegister()">'+svg('plus',12)+' 注册</button></div></div></div>';
  setTimeout(()=>{const i=document.getElementById('regUser');if(i)i.focus();},100);
}
function closeModal(){document.getElementById('modalContainer').innerHTML='';}

async function doLogin(){
  const u=document.getElementById('loginUser').value.trim();
  const p=document.getElementById('loginPass').value;
  const err=document.getElementById('loginErr');
  if(!u||!p){err.style.display='block';err.textContent='请填写用户名和密码';return;}
  const r=await api('/api/login',{method:'POST',body:{username:u,password:p}});
  if(r.success){SESSION={token:r.session,username:r.username,role:r.role};setCookie('session',r.session,7);closeModal();renderHeaderBtns();render();showToast('登录成功');}
  else{err.style.display='block';err.textContent=r.error||'登录失败';}
}
async function doRegister(){
  const u=document.getElementById('regUser').value.trim();
  const p=document.getElementById('regPass').value;
  const p2=document.getElementById('regPass2').value;
  const err=document.getElementById('regErr');
  if(!u||!p){err.style.display='block';err.textContent='请填写用户名和密码';return;}
  if(p!==p2){err.style.display='block';err.textContent='两次密码不一致';return;}
  const r=await api('/api/register',{method:'POST',body:{username:u,password:p}});
  if(r.success){SESSION={token:r.session,username:u,role:'admin'};setCookie('session',r.session,7);closeModal();renderHeaderBtns();render();showToast('注册成功，您现在是管理员');}
  else{err.style.display='block';err.textContent=r.error||'注册失败';}
}
function doLogout(){delCookie('session');SESSION=null;currentView='home';renderHeaderBtns();render();showToast('已退出登录');}

function goHome(){currentView='home';render();}
function goAdmin(){if(!SESSION||SESSION.role!=='admin'){showToast('需要管理员权限');return;}currentView='admin';render();}
function onSearch(v){searchTerm=v.toLowerCase().trim();if(currentView!=='home')currentView='home';render();}
function selectCategory(cat){currentCat=cat;if(currentView!=='home')currentView='home';render();}

function getFiltered(){
  let d=ENTRIES;
  if(currentCat!=='all')d=d.filter(e=>e.category===currentCat);
  if(searchTerm)d=d.filter(e=>(e.filename+' '+e.desc+' '+e.category).toLowerCase().includes(searchTerm));
  return d;
}

function renderCatSelect(){
  const sel=document.getElementById('catSelect');
  if(!sel)return;
  const cats=[...new Set(ENTRIES.map(e=>e.category))].sort();
  let opts='<option value="all">全部分类 ('+ENTRIES.length+')</option>';
  for(const c of cats){
    const n=ENTRIES.filter(e=>e.category===c).length;
    opts+='<option value="'+esc(c)+'"'+(currentCat===c?' selected':'')+'>'+esc(c)+' ('+n+')</option>';
  }
  sel.innerHTML=opts;
}

function render(){
  const c=document.getElementById('container');
  if(currentView==='admin')renderAdmin(c);
  else renderHome(c);
}

function dlHref(e){return '/download/'+encodeURIComponent(e.path);}

function renderHome(c){
  renderCatSelect();
  const d=getFiltered();
  document.getElementById('statCount').textContent=d.length;
  if(d.length===0){c.innerHTML='<div class="no-results">'+svg('search',40)+'<p style="margin-top:12px;">没有找到匹配的文件</p></div>';return;}
  const grouped={};
  d.forEach(e=>{if(!grouped[e.category])grouped[e.category]=[];grouped[e.category].push(e);});
  let h='';
  for(const cat of Object.keys(grouped).sort()){
    h+='<div class="section"><div class="section-header"><span class="cat-icon">'+svg(CAT_ICONS[cat]||'box',18)+'</span><h2>'+esc(cat)+' ('+grouped[cat].length+')</h2></div><div class="grid">';
    for(const e of grouped[cat]){
      h+='<div class="card" onclick="dlEntry('+ENTRIES.indexOf(e)+')">';
      h+='<div class="card-top"><div class="card-icon">'+svg(e.icon,20)+'</div><div class="card-info"><div class="card-title" title="'+esc(e.filename)+'">'+esc(e.filename)+'</div>'+(e.desc?'<div class="card-desc">'+esc(e.desc)+'</div>':'')+'</div></div>';
      h+='<div class="card-meta"><span class="meta-tag type">'+esc(e.fileType)+'</span><span class="meta-tag size">'+e.sizeText+'</span>';
      if(e.date)h+='<span class="meta-tag date">'+e.date+'</span>';
      h+='</div><div class="card-footer">';
      h+='<a class="btn btn-download btn-sm" href="'+dlHref(e)+'" download="'+esc(e.filename)+'" onclick="event.stopPropagation()">'+svg('download',12)+' 下载</a>';
      const url=e.customOfficial||e.official;
      if(e.showOfficial&&url){
        h+='<a class="btn btn-official btn-sm" href="'+esc(url)+'" target="_blank" rel="noopener" onclick="event.stopPropagation()">'+svg('external',12)+' 官网</a>';
      }
      h+='</div></div>';
    }
    h+='</div></div>';
  }
  c.innerHTML=h;
}

function dlEntry(i){const e=ENTRIES[i];if(e)window.location.href=dlHref(e);}

/* ===================== Admin ===================== */

function renderAdmin(c){
  if(!SESSION||SESSION.role!=='admin'){
    c.innerHTML='<div class="no-results">'+svg('lock',40)+'<p style="margin-top:12px;">需要管理员权限</p></div>';
    return;
  }
  let h='<div class="admin-wrap">';
  h+='<div class="admin-back"><button class="btn btn-back btn-sm" onclick="goHome()">'+svg('back',12)+' 返回软件库</button></div>';

  h+='<div class="admin-section"><h3>'+svg('cloud-download',16)+' 远程下载入库</h3><p class="section-desc">输入任意下载地址，服务器会将文件下载到软件库中留存（最大 2GB），完成后自动刷新列表。</p>';
  h+='<div class="admin-toolbar"><input type="text" id="fetchUrlInput" placeholder="https://example.com/file.iso（下载地址）"><input type="text" id="fetchNameInput" placeholder="保存文件名（可选）" style="max-width:200px"><button class="btn btn-primary" id="fetchGoBtn" onclick="startFetchUrl()">'+svg('cloud-download',12)+' 开始下载</button></div>';
  h+='<div class="fetch-status" id="fetchStatus"><span class="spinning" id="fetchSpin">'+svg('refresh',12)+'</span><span id="fetchStatusText"></span></div>';
  h+='</div>';

  h+='<div class="admin-section"><h3>'+svg('link',16)+' 官网下载地址管理</h3><p class="section-desc">为文件设置官网地址后，用户可见"官网"按钮；点"入库"可将该地址的文件直接下载到软件库留存。</p>';
  h+='<div class="admin-toolbar"><input type="text" id="adminUrlFilter" placeholder="按文件名过滤..." oninput="renderUrlRows()"></div>';
  h+='<div class="url-rows" id="urlRows"></div>';
  h+='</div>';

  h+='<div class="admin-section"><h3>'+svg('users',16)+' 用户管理</h3><p class="section-desc">仅管理员可进入本页面；管理员可添加/删除账户，普通账户可上传文件。</p><div id="userList">加载中...</div>';
  h+='<div class="admin-toolbar" style="margin-top:10px;"><input type="text" id="newUser" placeholder="新用户名"><input type="password" id="newPass" placeholder="密码"><select id="newRole" style="max-width:120px"><option value="user">普通用户</option><option value="admin">管理员</option></select><button class="btn btn-sm btn-primary" onclick="addUser()">'+svg('plus',12)+' 添加</button></div>';
  h+='</div>';

  h+='<div class="admin-section"><h3>'+svg('refresh',16)+' 系统管理</h3><p class="section-desc">重新扫描共享目录与上传目录；系统每小时也会自动扫描一次。</p><button class="btn btn-primary" id="rescanBtn" onclick="doRescan()">'+svg('refresh',12)+' 重新扫描</button></div>';

  h+='</div>';
  c.innerHTML=h;
  renderUrlRows();
  loadUserList();
}

function renderUrlRows(){
  const box=document.getElementById('urlRows');
  if(!box)return;
  const f=(document.getElementById('adminUrlFilter')?document.getElementById('adminUrlFilter').value:'').toLowerCase().trim();
  let h='';
  let count=0;
  for(let i=0;i<ENTRIES.length;i++){
    const e=ENTRIES[i];
    if(f&&e.filename.toLowerCase().indexOf(f)<0)continue;
    const url=e.customOfficial||e.official||'';
    h+='<div class="edit-row">';
    h+='<div class="row-name" title="'+esc(e.filename)+'">'+esc(e.filename)+'</div>';
    h+='<input type="text" id="url_'+i+'" value="'+esc(url)+'" placeholder="官网下载地址（可选）">';
    h+='<div class="row-btns">';
    h+='<button class="btn btn-sm btn-primary" title="保存地址" onclick="saveOfficial('+i+')">'+svg('save',12)+'</button>';
    h+='<button class="btn btn-sm '+(e.showOfficial?'btn-danger':'btn-official')+'" title="'+(e.showOfficial?'隐藏官网按钮':'显示官网按钮')+'" onclick="toggleOfficial('+i+')">'+(e.showOfficial?'隐藏':'显示')+'</button>';
    h+='<button class="btn btn-sm btn-external" title="打开地址" onclick="openOfficial('+i+')">'+svg('external',12)+'</button>';
    h+='<button class="btn btn-sm btn-download" title="下载入库留存" onclick="fetchEntry('+i+')">入库</button>';
    h+='</div></div>';
    count++;
  }
  box.innerHTML=h||'<p style="color:var(--text-dim);font-size:12px;padding:10px 0;">没有匹配的文件</p>';
}

async function saveOfficial(i){
  const e=ENTRIES[i];if(!e)return;
  const inp=document.getElementById('url_'+i);
  const url=inp?inp.value.trim():'';
  const r=await api('/api/admin/software',{method:'PUT',body:{path:e.path,customOfficial:url,showOfficial:url?true:e.showOfficial}});
  if(r.success){
    e.customOfficial=url;
    if(url)e.showOfficial=true;
    showToast(url?'地址已保存':'已清空地址');
    renderUrlRows();
  }else{showToast(r.error||'保存失败');}
}

async function toggleOfficial(i){
  const e=ENTRIES[i];if(!e)return;
  const r=await api('/api/admin/software',{method:'PUT',body:{path:e.path,showOfficial:!e.showOfficial}});
  if(r.success){e.showOfficial=!e.showOfficial;renderUrlRows();showToast(e.showOfficial?'已显示官网按钮':'已隐藏官网按钮');}
  else{showToast(r.error||'操作失败');}
}

function openOfficial(i){
  const e=ENTRIES[i];if(!e)return;
  const inp=document.getElementById('url_'+i);
  const url=(inp?inp.value.trim():'')||e.customOfficial||e.official;
  if(url)window.open(url,'_blank','noopener');
  else showToast('该文件未设置地址');
}

function fetchEntry(i){
  const e=ENTRIES[i];if(!e)return;
  const inp=document.getElementById('url_'+i);
  const url=(inp?inp.value.trim():'')||e.customOfficial||e.official;
  if(!url){showToast('请先填写下载地址');return;}
  startFetch(url,'');
}

async function startFetchUrl(){
  const u=document.getElementById('fetchUrlInput').value.trim();
  const n=document.getElementById('fetchNameInput').value.trim();
  if(!u){showToast('请输入下载地址');return;}
  startFetch(u,n);
}

async function startFetch(url,name){
  const r=await api('/api/admin/fetch-url',{method:'POST',body:{url:url,name:name}});
  if(!r.success){showToast(r.error||'无法开始下载');return;}
  showToast('开始下载，请稍候...');
  const btn=document.getElementById('fetchGoBtn');
  if(btn)btn.disabled=true;
  pollFetchStatus();
}

async function pollFetchStatus(){
  if(pollingFetch)return;
  pollingFetch=true;
  try{
    while(true){
      if(!document.getElementById('fetchStatus'))break;
      const r=await api('/api/fetch-status');
      const box=document.getElementById('fetchStatus');
      const txt=document.getElementById('fetchStatusText');
      const spin=document.getElementById('fetchSpin');
      if(box)box.classList.add('show');
      if(txt)txt.textContent=r.message||'';
      if(spin)spin.style.display=r.active?'inline-flex':'none';
      if(!r.active){
        const btn=document.getElementById('fetchGoBtn');
        if(btn)btn.disabled=false;
        if((r.message||'').indexOf('完成')===0){
          await loadData();
          render();
          showToast('文件已入库');
        }
        break;
      }
      await new Promise(res=>setTimeout(res,1500));
    }
  }finally{pollingFetch=false;}
}

async function loadUserList(){
  const r=await api('/api/users');
  const box=document.getElementById('userList');
  if(!box)return;
  if(!r.success){box.innerHTML='<p style="color:var(--red);font-size:12px;">'+esc(r.error||'加载失败')+'</p>';return;}
  let h='';
  for(const u of r.users){
    h+='<div class="user-row"><div class="user-info"><div class="user-name">'+esc(u.username)+'</div><div class="user-role">创建于 '+esc(u.created||'-')+'</div></div><span class="role-badge '+u.role+'">'+(u.role==='admin'?'管理员':'普通用户')+'</span>';
    if(u.username!==SESSION.username)h+='<button class="btn btn-sm btn-danger" onclick="delUser(\\''+esc(u.username).replace(/'/g,"\\\\'")+'\\')">删除</button>';
    h+='</div>';
  }
  box.innerHTML=h||'<p style="color:var(--text-dim);font-size:12px;">暂无用户</p>';
}

async function addUser(){
  const u=document.getElementById('newUser').value.trim();
  const p=document.getElementById('newPass').value;
  const role=document.getElementById('newRole').value;
  if(!u||!p){showToast('请填写用户名和密码');return;}
  const r=await api('/api/users',{method:'POST',body:{username:u,password:p,role:role}});
  if(r.success){showToast('用户已添加');document.getElementById('newUser').value='';document.getElementById('newPass').value='';loadUserList();}
  else{showToast(r.error||'添加失败');}
}

async function delUser(name){
  if(!confirm('确认删除用户 '+name+'？'))return;
  const r=await api('/api/users/'+encodeURIComponent(name),{method:'DELETE'});
  if(r.success){showToast('已删除');loadUserList();}
  else{showToast(r.error||'删除失败');}
}

/* ===================== Upload ===================== */

function doUpload(){
  if(!SESSION){showLogin();return;}
  const mc=document.getElementById('modalContainer');
  mc.innerHTML='<div class="modal-overlay" onclick="if(event.target===this)closeModal()"><div class="modal" style="max-width:480px;"><h2>'+svg('upload',20)+' 上传文件</h2><div class="upload-area" id="uploadArea">'+svg('upload',32)+'<p>点击选择文件，或将文件拖拽到此处</p><p style="font-size:11px;margin-top:4px;">最大 500MB · 上传后自动加入软件库</p></div><input type="file" id="fileInput" style="display:none"><div id="uploadProgress" style="display:none"><div class="progress-bar"><div class="progress-fill" id="progressFill" style="width:0%"></div></div><p style="text-align:center;margin-top:6px;font-size:12px;color:var(--text-dim)" id="uploadStatus">上传中...</p></div><div class="modal-btns"><button class="btn btn-back" onclick="closeModal()">关闭</button></div></div></div>';
  const area=document.getElementById('uploadArea');
  const input=document.getElementById('fileInput');
  area.onclick=function(){input.click();};
  input.onchange=function(){if(this.files.length>0)handleFile(this.files[0]);};
  area.ondragover=function(e){e.preventDefault();this.style.borderColor='var(--accent)';this.style.background='var(--accent-soft)';};
  area.ondragleave=function(e){e.preventDefault();this.style.borderColor='var(--border-bright)';this.style.background='transparent';};
  area.ondrop=function(e){e.preventDefault();this.style.borderColor='var(--border-bright)';this.style.background='transparent';if(e.dataTransfer.files.length>0)handleFile(e.dataTransfer.files[0]);};
}

function handleFile(file){
  if(!file)return;
  const formData=new FormData();
  formData.append('file',file);
  document.getElementById('uploadProgress').style.display='block';
  document.getElementById('uploadArea').style.display='none';
  const xhr=new XMLHttpRequest();
  xhr.upload.addEventListener('progress',function(e){if(e.lengthComputable){const pct=Math.round(e.loaded/e.total*100);document.getElementById('progressFill').style.width=pct+'%';document.getElementById('uploadStatus').textContent='上传中... '+pct+'%';}});
  xhr.addEventListener('load',function(){
    let r={};
    try{r=JSON.parse(xhr.responseText);}catch(e){}
    if(r.success){document.getElementById('uploadStatus').textContent='上传成功，正在更新软件库...';setTimeout(()=>location.reload(),2500);}
    else{showToast(r.error||'上传失败');document.getElementById('uploadProgress').style.display='none';document.getElementById('uploadArea').style.display='block';}
  });
  xhr.addEventListener('error',function(){showToast('上传失败');document.getElementById('uploadProgress').style.display='none';document.getElementById('uploadArea').style.display='block';});
  xhr.open('POST','/api/upload');
  if(SESSION)xhr.setRequestHeader('X-Session',SESSION.token);
  xhr.send(formData);
}

/* ===================== Rescan ===================== */

async function doRescan(){
  const btn=document.getElementById('rescanBtn');
  if(btn){btn.disabled=true;btn.innerHTML=svg('refresh',12)+' 扫描中...';}
  const r=await api('/api/rescan',{method:'POST'});
  if(r.success){showToast('扫描完成，正在刷新...');setTimeout(()=>location.reload(),2500);}
  else{
    showToast(r.error||'扫描失败');
    if(btn){btn.disabled=false;btn.innerHTML=svg('refresh',12)+' 重新扫描';}
  }
}

/* ===================== Init ===================== */

async function loadData(){
  const r=await fetch('/api/software');
  const d=await r.json();
  if(d.success)ENTRIES=d.data;
}

async function init(){
  const token=getCookie('session');
  if(token){
    const r=await api('/api/session');
    if(r.success){SESSION={token:token,username:r.username,role:r.role};}
  }
  await loadData();
  renderHeaderBtns();
  render();
  if(!SESSION&&!HAS_USERS){showRegister();}
}
init();
</script>
</body>
</html>"""

    js = js.replace("__ICONS_JSON__", icons_json)
    js = js.replace("__CAT_ICONS_JSON__", cat_icons_json)
    js = js.replace("__HAS_USERS__", "true" if has_registered_users else "false")

    html = ("<!DOCTYPE html>\n<html lang=\"zh-CN\">\n<head>\n<meta charset=\"UTF-8\">\n"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">\n"
            "<title>软件库 | Software Library</title>\n" + css + "\n" + body + js)
    return html

# ============================================================
# HTTP Handler
# ============================================================

_scan_lock = threading.Lock()
_last_scan_time = ""


def resolve_library_path(rel_path):
    """Map a web path ('uploads/x' or 'dir/x') to a safe absolute file path."""
    rel_path = (rel_path or "").replace("\\", "/")
    if rel_path.startswith(UPLOAD_URL_PREFIX):
        base, rel = UPLOAD_DIR, rel_path[len(UPLOAD_URL_PREFIX):]
    else:
        base, rel = ROOT_DIR, rel_path
    safe = os.path.normpath(os.path.join(base, rel))
    base_n = os.path.normpath(base)
    if safe != base_n and not safe.startswith(base_n + os.sep):
        return None  # path traversal
    return safe if os.path.isfile(safe) else None


class SoftwareHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DATA_DIR, **kwargs)

    def _get_session(self):
        token = self.headers.get('X-Session', '')
        if not token:
            cookie = self.headers.get('Cookie', '')
            m = re.search(r'session=([a-f0-9]+)', cookie)
            if m:
                token = m.group(1)
        return get_session(token)

    def _require_auth(self, role=None):
        s = self._get_session()
        if not s:
            self._serve_json({"success": False, "error": "未登录"})
            return None
        if role and s.get("role") != role:
            self._serve_json({"success": False, "error": "权限不足（需要管理员）"})
            return None
        return s

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = urllib.parse.unquote(parsed.path)

        if path == '/' or path == '/index.html':
            self._serve_file(HTML_FILE, 'text/html; charset=utf-8')
            return

        if path.startswith('/download/'):
            rel_path = path[len('/download/'):]
            safe_path = resolve_library_path(rel_path)
            if safe_path:
                self._serve_download(safe_path)
            else:
                self.send_error(404, "File not found")
            return

        if path == '/api/software':
            self._serve_json({"success": True, "data": build_entry_list()})
            return

        if path == '/api/session':
            s = self._get_session()
            if s:
                self._serve_json({"success": True, "username": s["username"], "role": s["role"]})
            else:
                self._serve_json({"success": False})
            return

        if path == '/api/users':
            s = self._require_auth('admin')
            if not s:
                return
            users = load_users()
            safe_users = [{"username": u["username"], "role": u["role"], "created": u.get("created", "")}
                          for u in users.get("users", [])]
            self._serve_json({"success": True, "users": safe_users})
            return

        if path == '/api/scan-status':
            self._serve_json({"scanning": _scan_lock.locked(), "lastScan": _last_scan_time})
            return

        if path == '/api/fetch-status':
            self._serve_json(dict(_fetch_status))
            return

        super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = urllib.parse.unquote(parsed.path)

        if path == '/api/register':
            self._handle_register()
            return

        if path == '/api/login':
            self._handle_login()
            return

        if path == '/api/logout':
            token = self.headers.get('X-Session', '')
            destroy_session(token)
            self._serve_json({"success": True})
            return

        if path == '/api/rescan':
            s = self._require_auth('admin')
            if not s:
                return
            refresh_library_async()
            self._serve_json({"success": True, "message": "扫描已启动"})
            return

        if path == '/api/admin/software':
            s = self._require_auth('admin')
            if not s:
                return
            self._handle_admin_software()
            return

        if path == '/api/admin/fetch-url':
            s = self._require_auth('admin')
            if not s:
                return
            self._handle_fetch_url()
            return

        if path == '/api/upload':
            s = self._require_auth()  # any logged-in user may upload
            if not s:
                return
            self._handle_upload()
            return

        if path == '/api/users':
            s = self._require_auth('admin')
            if not s:
                return
            self._handle_add_user()
            return

        self.send_error(404, "Not found")

    def do_PUT(self):
        parsed = urllib.parse.urlparse(self.path)
        path = urllib.parse.unquote(parsed.path)
        if path == '/api/admin/software':
            s = self._require_auth('admin')
            if not s:
                return
            self._handle_admin_software()
            return
        self.send_error(404, "Not found")

    def do_DELETE(self):
        parsed = urllib.parse.urlparse(self.path)
        path = urllib.parse.unquote(parsed.path)
        if path.startswith('/api/admin/software/'):
            s = self._require_auth('admin')
            if not s:
                return
            name = urllib.parse.unquote(path[len('/api/admin/software/'):])
            self._handle_admin_delete(name)
            return
        if path.startswith('/api/users/'):
            s = self._require_auth('admin')
            if not s:
                return
            name = urllib.parse.unquote(path[len('/api/users/'):])
            if s["username"] == name:
                self._serve_json({"success": False, "error": "不能删除自己"})
                return
            ok, msg = delete_user(name)
            self._serve_json({"success": ok, "message": msg})
            return
        self.send_error(404, "Not found")

    def _handle_register(self):
        data = self._read_body()
        username = data.get("username", "").strip()
        password = data.get("password", "")
        if not username or not password:
            self._serve_json({"success": False, "error": "用户名和密码不能为空"})
            return
        if has_users():
            self._serve_json({"success": False, "error": "已存在用户，请联系管理员开通账号"})
            return
        ok, msg = create_user(username, password, role="admin")
        if ok:
            token = create_session(username, "admin")
            self._serve_json({"success": True, "session": token, "username": username, "role": "admin"})
        else:
            self._serve_json({"success": False, "error": msg})

    def _handle_login(self):
        data = self._read_body()
        username = data.get("username", "").strip()
        password = data.get("password", "")
        ok, result = verify_user(username, password)
        if ok:
            token = create_session(username, result["role"])
            self._serve_json({"success": True, "session": token, "username": username, "role": result["role"]})
        else:
            self._serve_json({"success": False, "error": result})

    def _handle_add_user(self):
        data = self._read_body()
        username = data.get("username", "").strip()
        password = data.get("password", "")
        role = data.get("role", "user")
        if role not in ("admin", "user"):
            role = "user"
        if not username or not password:
            self._serve_json({"success": False, "error": "用户名和密码不能为空"})
            return
        ok, msg = create_user(username, password, role)
        self._serve_json({"success": ok, "message": msg})

    def _handle_fetch_url(self):
        if _fetch_status.get("active"):
            self._serve_json({"success": False, "error": "已有下载任务进行中"})
            return
        data = self._read_body()
        url = (data.get("url") or "").strip()
        name = (data.get("name") or "").strip() or None
        if not url or not re.match(r'^https?://', url):
            self._serve_json({"success": False, "error": "请输入有效的 http(s) 下载地址"})
            return
        threading.Thread(target=fetch_remote_file, args=(url, name), daemon=True).start()
        self._serve_json({"success": True, "message": "下载已开始"})

    def _handle_upload(self):
        try:
            ctype = self.headers.get('Content-Type', '')
            if 'multipart/form-data' not in ctype:
                self._serve_json({"success": False, "error": "需要文件上传"})
                return
            boundary = ctype.split('boundary=')[1].encode()
            remaining = int(self.headers.get('Content-Length', 0))
            if remaining > MAX_UPLOAD_SIZE + 64 * 1024:
                self._serve_json({"success": False, "error": "文件太大（最大 500MB）"})
                return
            body_data = self.rfile.read(remaining)
            parts = body_data.split(b'--' + boundary)
            filename = None
            file_data = None
            for part in parts:
                if b'Content-Disposition' in part and b'filename=' in part:
                    disp_match = re.search(rb'filename="([^"]+)"', part)
                    if disp_match:
                        filename = disp_match.group(1).decode('utf-8', errors='replace')
                    idx = part.find(b'\r\n\r\n')
                    if idx >= 0:
                        file_data = part[idx + 4:]
                        if file_data.endswith(b'\r\n'):
                            file_data = file_data[:-2]
            if not filename or file_data is None:
                self._serve_json({"success": False, "error": "未找到文件"})
                return
            os.makedirs(UPLOAD_DIR, exist_ok=True)
            safe_name = os.path.basename(filename.replace("\\", "/"))
            if not safe_name:
                safe_name = "upload.bin"
            save_path = os.path.join(UPLOAD_DIR, safe_name)
            base, ext = os.path.splitext(safe_name)
            i = 1
            while os.path.exists(save_path):
                save_path = os.path.join(UPLOAD_DIR, f"{base}({i}){ext}")
                i += 1
            with open(save_path, 'wb') as f:
                f.write(file_data)
            refresh_library_async()  # make it visible immediately
            self._serve_json({"success": True, "message": "上传成功", "filename": os.path.basename(save_path)})
        except Exception as e:
            self._serve_json({"success": False, "error": str(e)})

    def _handle_admin_software(self):
        try:
            data = self._read_body()
            path = data.get("path")
            if not path:
                self._serve_json({"success": False, "error": "path is required"})
                return
            config = load_json(CONFIG_FILE, default_config())
            if "software" not in config:
                config["software"] = {}
            if path not in config["software"]:
                config["software"][path] = {}
            sw_cfg = config["software"][path]
            for key in ("category", "icon", "desc", "official", "customOfficial", "showOfficial"):
                if key in data:
                    sw_cfg[key] = data[key]
            save_json(CONFIG_FILE, config)
            self._serve_json({"success": True, "message": "已更新"})
        except Exception as e:
            self._serve_json({"success": False, "error": str(e)})

    def _handle_admin_delete(self, path):
        config = load_json(CONFIG_FILE, default_config())
        if path in config.get("software", {}):
            del config["software"][path]
            save_json(CONFIG_FILE, config)
            self._serve_json({"success": True, "message": "已删除"})
        else:
            self._serve_json({"success": False, "error": "未找到"})

    def _serve_file(self, filepath, content_type):
        try:
            with open(filepath, 'rb') as f:
                content = f.read()
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(content)))
            self.send_header('Cache-Control', 'no-cache')
            self.end_headers()
            self.wfile.write(content)
        except FileNotFoundError:
            self.send_error(404, "File not found")

    def _serve_download(self, filepath):
        try:
            filesize = os.path.getsize(filepath)
            filename = os.path.basename(filepath)
            quoted = urllib.parse.quote(filename)
            self.send_response(200)
            self.send_header('Content-Type', 'application/octet-stream')
            self.send_header('Content-Length', str(filesize))
            self.send_header('Content-Disposition', f"attachment; filename*=UTF-8''{quoted}")
            self.end_headers()
            with open(filepath, 'rb') as f:
                while True:
                    chunk = f.read(65536)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
        except FileNotFoundError:
            self.send_error(404, "File not found")
        except Exception as e:
            self.send_error(500, str(e))

    def _serve_json(self, data):
        content = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(content)))
        self.send_header('Cache-Control', 'no-cache')
        self.end_headers()
        self.wfile.write(content)

    def _read_body(self):
        length = int(self.headers.get('Content-Length', 0))
        if length == 0:
            return {}
        body = self.rfile.read(length)
        return json.loads(body.decode('utf-8'))

    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, X-Session')
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def log_message(self, format, *args):
        log_msg = f"[{self.log_date_time_string()}] {format % args}"
        try:
            os.makedirs(LOG_DIR, exist_ok=True)
            with open(os.path.join(LOG_DIR, "server.log"), "a", encoding="utf-8") as f:
                f.write(log_msg + "\n")
        except Exception:
            pass

# ============================================================
# Main
# ============================================================

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
    print(f"\n{'=' * 55}")
    print(f"  Software Library Manager v6 Running")
    print(f"  URL: http://0.0.0.0:{port}")
    print(f"  Scan root: {ROOT_DIR}")
    print(f"  Upload dir: {UPLOAD_DIR}")
    print(f"  Data dir: {DATA_DIR}")
    print(f"  Users: {'Registered' if has_users() else 'No users yet (first visit registers admin)'}")
    print(f"{'=' * 55}\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
        httpd.shutdown()


def watch_loop(interval):
    while True:
        time.sleep(interval)
        try:
            refresh_library()
        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Rescan error: {e}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Software Library Manager")
    parser.add_argument("--scan-only", action="store_true")
    parser.add_argument("--no-scan", action="store_true")
    parser.add_argument("--port", type=int, default=PORT)
    parser.add_argument("--watch", action="store_true")
    args = parser.parse_args()
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    if not args.no_scan:
        refresh_library()
    else:
        html = generate_html()
        with open(HTML_FILE, "w", encoding="utf-8") as f:
            f.write(html)
    if args.scan_only:
        return
    if args.watch:
        t = threading.Thread(target=watch_loop, args=(WATCH_INTERVAL,), daemon=True)
        t.start()
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Auto-rescan enabled (every {WATCH_INTERVAL}s)")
    run_server(args.port)


if __name__ == "__main__":
    main()
