#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Software Library Manager v4
==========================
Scans NAS directory for software files, provides a searchable web UI
with user authentication, admin panel, file upload, and download system.

Environment variables:
  LIB_ROOT_DIR       Root directory to scan (default: /data)
  LIB_PORT           Web server port (default: 8899)
  LIB_DATA_DIR       Generated files directory (default: /app/data)
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
import cgi
from datetime import datetime

# ============================================================
# Configuration
# ============================================================

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

MAX_UPLOAD_SIZE = 500 * 1024 * 1024  # 500MB

# ============================================================
# Software knowledge base
# ============================================================

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
    "immortalwrt": {"name":"ImmortalWrt","category":"路由器/软路由","icon":"router","desc":"ImmortalWrt 软路由固件","official":"https://immortalwrt.org"},
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
    "linux":'<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 2C9 2 8 4 8 6c0 1-1 2-1.5 3.5C6 11 6 12 7 13c.5.5 1 2 1 3 0 1.5-1 2-1 3 0 .5.5 1 1.5 1s2-1 3.5-1 2.5 1 3.5 1 1.5-.5 1.5-1c0-1-1-1.5-1-3 0-1 .5-2.5 1-3 1-1 1-2-.5-3.5C15 8 14 7 14 6c0-2-1-4-2-4z"/></svg>',
    "router":'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="14" width="20" height="7" rx="1"/><line x1="6" y1="17.5" x2="6.01" y2="17.5"/><line x1="10" y1="17.5" x2="10.01" y2="17.5"/><path d="M12 14V8M8 8a4 4 0 018 0"/></svg>',
    "database":'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5v6c0 1.7 4 3 9 3s9-1.3 9-3V5"/><path d="M3 11v6c0 1.7 4 3 9 3s9-1.3 9-3v-6"/></svg>',
    "office":'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><line x1="3" y1="9" x2="21" y2="9"/><line x1="9" y1="21" x2="9" y2="9"/></svg>',
    "adobe":'<svg viewBox="0 0 24 24" fill="currentColor"><path d="M3 3h5l4 8 4-8h5v18h-5v-8l-4 8-4-8v8H3z" opacity="0.9"/></svg>',
    "pdf":'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><path d="M14 2v6h6"/></svg>',
    "code":'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>',
    "java":'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M8 18c-2 0-3-1-3-2 0-1 1-2 4-2v2c0 1 .5 2 1 2z"/><path d="M11 15c-4-1-5-3-5-5 0-2 3-3 6-3v2c-2 0-3 .5-3 1.5S10 12 13 13"/><path d="M14 12c4-1 5-3 5-5 0-2-3-3-6-3v2c2 0 3 .5 3 1.5S16 9 13 10"/></svg>',
    "python":'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2c-3 0-5 1-5 3v2h5v1H5c-2 0-3 2-3 4s1 4 3 4h2v-2c0-2 2-3 4-3h3c2 0 3-1 3-3V5c0-2-2-3-5-3z"/><circle cx="9" cy="4.5" r="0.5" fill="currentColor"/></svg>',
    "terminal":'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/></svg>',
    "disk":'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="3"/></svg>',
    "archive":'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="21 8 21 21 3 21 3 8"/><rect x="1" y="3" width="22" height="5"/><line x1="10" y1="12" x2="14" y2="12"/></svg>',
    "usb":'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="4" r="2"/><path d="M12 6v6"/><path d="M9 12h6"/><path d="M12 12v8a2 2 0 002 2 2 2 0 002-2"/></svg>',
    "trash":'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/></svg>',
    "wrench":'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14.7 6.3a4 4 0 00-5.4 5.4L3 18l3 3 6.3-6.3a4 4 0 005.4-5.4l-2.5 2.5-2.5-.5-.5-2.5 2.5-2.5z"/></svg>',
    "network":'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15 15 0 010 20M12 2a15 15 0 000 20"/></svg>',
    "remote":'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="4" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="18" x2="12" y2="21"/></svg>',
    "browser":'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15 15 0 010 20M12 2a15 15 0 000 20"/></svg>',
    "media":'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="23 7 16 12 23 17 23 7"/><rect x="1" y="5" width="15" height="14" rx="2"/></svg>',
    "screenshot":'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M23 19a2 2 0 01-2 2H3a2 2 0 01-2-2V8a2 2 0 012-2h4l2-3h6l2 3h4a2 2 0 012 2z"/><circle cx="12" cy="13" r="4"/></svg>',
    "key":'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 2l-2 2m-7.5 7.5a5 5 0 11-7 7 5 5 0 017-7zm0 0L21 2m-9.5 9.5l5 5"/></svg>',
    "lock":'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0110 0v4"/></svg>',
    "driver":'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="6" width="20" height="12" rx="2"/><line x1="6" y1="10" x2="6" y2="10"/><line x1="6" y1="14" x2="6" y2="14"/><line x1="10" y1="10" x2="18" y2="10"/><line x1="10" y1="14" x2="18" y2="14"/></svg>',
    "box":'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 8l-9-5-9 5v8l9 5 9-5V8z"/><path d="M3 8l9 5 9-5M12 13v8"/></svg>',
    "download":'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>',
    "upload":'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>',
    "link":'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10 13a5 5 0 007 0l3-3a5 5 0 00-7-7l-1 1"/><path d="M14 11a5 5 0 00-7 0l-3 3a5 5 0 007 7l1-1"/></svg>',
    "copy":'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/></svg>',
    "refresh":'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15"/></svg>',
    "folder":'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z"/></svg>',
    "file":'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M13 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V9z"/><polyline points="13 2 13 9 20 9"/></svg>',
    "search":'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>',
    "package":'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="16.5" y1="5.5" x2="7.5" y2="14.5"/><polygon points="21 8 21 21 3 21 3 8 12 1 21 8"/><polyline points="3 8 12 13 21 8"/></svg>',
    "edit":'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>',
    "plus":'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>',
    "back":'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/></svg>',
    "external":'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>',
    "chevron":'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"/></svg>',
    "layers":'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/></svg>',
    "settings":'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-2 2 2 2 0 01-2-2v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83 0 2 2 0 010-2.83l.06-.06a1.65 1.65 0 00.33-1.82 1.65 1.65 0 00-1.51-1H3a2 2 0 01-2-2 2 2 0 012-2h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 010-2.83 2 2 0 012.83 0l.06.06a1.65 1.65 0 001.82.33H9a1.65 1.65 0 001-1.51V3a2 2 0 012-2 2 2 0 012 2v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 0 2 2 0 010 2.83l-.06.06a1.65 1.65 0 00-.33 1.82V9a1.65 1.65 0 001.51 1H21a2 2 0 012 2 2 2 0 01-2 2h-.09a1.65 1.65 0 00-1.51 1z"/></svg>',
    "user":'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>',
    "users":'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 00-3-3.87M16 3.13a4 4 0 010 7.75"/></svg>',
    "logout":'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>',
    "save":'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 21H5a2 2 0 01-2-2V5a2 2 0 012-2h11l5 5v11a2 2 0 01-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/></svg>',
    "close":'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>',
}

def get_svg(name):
    return SVG_ICONS.get(name, SVG_ICONS["box"])

# ============================================================
# User authentication
# ============================================================

def hash_password(password):
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

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

def get_session_token():
    return uuid.uuid4().hex

# Simple in-memory session store: token -> {username, role}
_sessions = {}

def create_session(username, role):
    token = get_session_token()
    _sessions[token] = {"username": username, "role": role, "time": time.time()}
    return token

def get_session(token):
    if not token:
        return None
    s = _sessions.get(token)
    if not s:
        return None
    # Session expires after 24 hours
    if time.time() - s["time"] > 86400:
        del _sessions[token]
        return None
    return s

def destroy_session(token):
    if token in _sessions:
        del _sessions[token]

# ============================================================
# Software matching
# ============================================================

def match_software(filename, dirpath):
    lower = filename.lower()
    parent_dir = os.path.basename(dirpath).lower()
    search_str = lower + " " + parent_dir

    for key, info in SOFTWARE_DB.items():
        if key in search_str:
            return info["name"], info["category"], info["icon"], info["desc"], info.get("official","")
    if "tools" in search_str and ("vmware" in search_str or "vm" in parent_dir):
        return "VMware Tools", "虚拟化", "vmware", "VMware Tools 驱动包", ""
    if "keygen" in lower or "注册" in lower:
        return "注册机/工具", "激活工具", "key", "注册/激活工具", ""
    if "补丁" in lower or "patch" in lower:
        return "补丁工具", "激活工具", "key", "软件补丁", ""
    ext = os.path.splitext(filename)[1].lower()
    ext_icons = {".exe":"box",".msi":"box",".iso":"disk",".img":"disk",".zip":"archive",
                  ".7z":"archive",".rar":"archive",".gz":"archive",".apk":"box",
                  ".dmg":"disk",".vmdk":"disk",".ova":"box",".ovf":"box",".wim":"disk"}
    icon_name = ext_icons.get(ext, "file")
    # Just use the filename (without extension) as the display name
    display_name = os.path.splitext(filename)[0]
    return display_name, "其他", icon_name, "软件文件", ""

def format_size(size_bytes):
    if size_bytes == 0: return "0 B"
    size = float(size_bytes)
    for unit in ["B","KB","MB","GB","TB"]:
        if size < 1024:
            if unit == "B": return f"{int(size)} {unit}"
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

def scan_directory(root_dir):
    items = []
    exts = set(SUPPORTED_EXTENSIONS.keys())
    compound_exts = [".tar.gz", ".tar.xz"]
    seen_files = {}
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
            dedup_key = filename.lower() + "|" + str(size)
            if dedup_key in seen_files:
                continue
            seen_files[dedup_key] = True
            relpath = os.path.relpath(fullpath, root_dir)
            webpath = relpath.replace("\\", "/")
            name, category, icon, desc, official = match_software(filename, dirpath)
            items.append({
                "name": name, "filename": filename, "category": category,
                "icon": icon, "desc": desc, "official": official,
                "size": size, "sizeText": format_size(size),
                "ext": matched_ext, "fileType": SUPPORTED_EXTENSIONS.get(matched_ext, "FILE"),
                "date": get_file_date(fullpath), "path": webpath,
            })
    items.sort(key=lambda x: (x["category"], x["name"].lower(), x["filename"].lower()))
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
    return {"software": {}, "order": [], "version": 1}

def run_scan():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Scanning: {ROOT_DIR}")
    items = scan_directory(ROOT_DIR)
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

def build_software_list():
    scan_data = load_json(SCAN_FILE, {"items": []})
    config = load_json(CONFIG_FILE, default_config())
    scan_items = scan_data.get("items", [])
    overrides = config.get("software", {})

    grouped = {}
    for item in scan_items:
        name = item["name"]
        if name not in grouped:
            grouped[name] = {
                "name": name,
                "category": item["category"],
                "icon": item["icon"],
                "desc": item["desc"],
                "official": item["official"],
                "versions": [],
                "showOfficial": False,
            }
        grouped[name]["versions"].append({
            "filename": item["filename"],
            "size": item["size"],
            "sizeText": item["sizeText"],
            "fileType": item["fileType"],
            "date": item["date"],
            "path": item["path"],
        })

    for sw_name, cfg in overrides.items():
        if sw_name in grouped:
            if "category" in cfg: grouped[sw_name]["category"] = cfg["category"]
            if "icon" in cfg: grouped[sw_name]["icon"] = cfg["icon"]
            if "desc" in cfg: grouped[sw_name]["desc"] = cfg["desc"]
            if "official" in cfg: grouped[sw_name]["official"] = cfg["official"]
            if "showOfficial" in cfg: grouped[sw_name]["showOfficial"] = cfg["showOfficial"]
        else:
            grouped[sw_name] = {
                "name": sw_name,
                "category": cfg.get("category", "其他"),
                "icon": cfg.get("icon", "box"),
                "desc": cfg.get("desc", ""),
                "official": cfg.get("official", ""),
                "versions": [],
                "showOfficial": cfg.get("showOfficial", False),
            }

    sw_list = list(grouped.values())
    sw_list.sort(key=lambda s: s["name"].lower())
    # Sort versions by filename
    for sw in sw_list:
        sw["versions"].sort(key=lambda v: v.get("filename",""), reverse=True)
    return sw_list

# ============================================================
# HTML generator (SPA)
# ============================================================

def generate_html():
    sw_list = build_software_list()
    categories = {}
    for sw in sw_list:
        cat = sw["category"]
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(sw)

    total_files = sum(len(sw["versions"]) for sw in sw_list)
    total_size = sum(v["size"] for sw in sw_list for v in sw["versions"])
    total_size_text = format_size(total_size)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    has_registered_users = has_users()

    cat_icons = json.dumps(CAT_ICON_MAP, ensure_ascii=False)
    all_icons = {}
    for name in set(get_svg(n) and n for n in list(CAT_ICON_MAP.values()) + [sw["icon"] for sw in sw_list] + ["download","upload","link","copy","refresh","search","package","edit","plus","back","external","chevron","settings","file","folder","layers","user","users","logout","save","close","lock","box"]):
        all_icons[name] = SVG_ICONS.get(name, SVG_ICONS["box"])

    icons_json = json.dumps(all_icons, ensure_ascii=False)
    cat_icons_json = cat_icons

    # ---- CSS ----
    css = """<style>
:root{
--bg:#f5f6f8;--bg-card:#fff;--bg-search:#eef0f3;--text:#1a1d28;--text-dim:#6b7280;
--text-bright:#111827;--accent:#4f7cff;--accent-glow:rgba(79,124,255,0.15);
--accent-soft:rgba(79,124,255,0.06);--border:#e0e3eb;--border-bright:#c8ccd6;
--radius:12px;--green:#16a34a;--orange:#d97706;--red:#dc2626;
--shadow:0 2px 12px rgba(0,0,0,0.06);--shadow-lg:0 4px 24px rgba(0,0,0,0.08);
--purple:#534AB7;--purple-soft:#EEEDFE;
}
*{margin:0;padding:0;box-sizing:border-box;}
body{font-family:-apple-system,'Segoe UI','Microsoft YaHei',sans-serif;background:var(--bg);color:var(--text);line-height:1.6;min-height:100vh;}
.header{position:sticky;top:0;z-index:100;background:rgba(255,255,255,0.92);backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px);border-bottom:1px solid var(--border);padding:14px 0;}
.header-inner{max-width:1400px;margin:0 auto;padding:0 24px;display:flex;align-items:center;gap:20px;flex-wrap:wrap;}
.logo{display:flex;align-items:center;gap:12px;flex-shrink:0;cursor:pointer;}
.logo-icon{width:42px;height:42px;border-radius:10px;background:linear-gradient(135deg,var(--accent),#6b5cff);display:flex;align-items:center;justify-content:center;box-shadow:var(--shadow);}
.logo-icon svg{width:22px;height:22px;color:#fff;}
.logo-text h1{font-size:18px;color:var(--text-bright);font-weight:700;display:flex;align-items:center;gap:8px;}
.logo-text span{font-size:11px;color:var(--text-dim);}
.search-box{flex:1;min-width:200px;position:relative;}
.search-box input{width:100%;padding:10px 16px 10px 42px;background:var(--bg-search);border:1px solid var(--border);border-radius:10px;color:var(--text);font-size:14px;transition:all 0.2s;}
.search-box input:focus{outline:none;border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-glow);}
.search-box .search-icon{position:absolute;left:14px;top:50%;transform:translateY(-50%);color:var(--text-dim);width:16px;height:16px;display:flex;align-items:center;}
.search-box .search-icon svg{width:16px;height:16px;}
.stats{display:flex;gap:20px;flex-shrink:0;}
.stat-item{text-align:center;}
.stat-item .num{font-size:18px;font-weight:700;color:var(--accent);}
.stat-item .label{font-size:11px;color:var(--text-dim);}
.header-btns{display:flex;gap:8px;flex-shrink:0;}
.header-btn{display:inline-flex;align-items:center;gap:5px;padding:8px 14px;border-radius:8px;font-size:13px;font-weight:500;cursor:pointer;background:var(--bg-card);border:1px solid var(--border-bright);color:var(--text-dim);transition:all 0.15s;text-decoration:none;}
.header-btn:hover{border-color:var(--accent);color:var(--accent);}
.header-btn svg{width:14px;height:14px;}
.header-btn.admin-btn{background:var(--purple-soft);border-color:var(--purple);color:var(--purple);}
.header-btn.danger{color:var(--red);border-color:var(--red);}
.cat-select{display:flex;align-items:center;gap:8px;padding:8px 0;flex-wrap:wrap;}
.cat-select select{padding:7px 14px;border-radius:8px;border:1px solid var(--border);background:var(--bg-card);color:var(--text);font-size:13px;cursor:pointer;outline:none;}
.cat-select select:focus{border-color:var(--accent);}
.container{max-width:1400px;margin:0 auto;padding:24px;}
.section{margin-bottom:32px;}
.section-header{display:flex;align-items:center;gap:10px;margin-bottom:16px;padding-bottom:8px;border-bottom:1px solid var(--border);}
.section-header h2{font-size:17px;color:var(--text-bright);}
.section-header .cat-icon{width:22px;height:22px;color:var(--accent);}
.section-header .cat-icon svg{width:22px;height:22px;}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:14px;}
.card{background:var(--bg-card);border:1px solid var(--border);border-radius:var(--radius);padding:16px;transition:all 0.2s;display:flex;flex-direction:column;gap:10px;box-shadow:var(--shadow);cursor:pointer;}
.card:hover{border-color:var(--border-bright);box-shadow:var(--shadow-lg);transform:translateY(-1px);}
.card-top{display:flex;align-items:flex-start;gap:12px;}
.card-icon{width:48px;height:48px;border-radius:10px;background:var(--bg-search);display:flex;align-items:center;justify-content:center;flex-shrink:0;color:var(--accent);}
.card-icon svg{width:26px;height:26px;}
.card-info{flex:1;min-width:0;}
.card-title{font-size:14px;font-weight:600;color:var(--text-bright);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
.card-desc{font-size:12px;color:var(--text-dim);margin-top:3px;overflow:hidden;text-overflow:ellipsis;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;}
.card-meta{display:flex;flex-wrap:wrap;gap:8px;font-size:11px;}
.meta-tag{display:inline-flex;align-items:center;gap:3px;padding:2px 8px;border-radius:4px;background:rgba(0,0,0,0.03);}
.meta-tag.type{color:var(--orange);}
.meta-tag.size{color:var(--green);}
.meta-tag.date{color:var(--text-dim);}
.card-footer{display:flex;align-items:center;justify-content:space-between;margin-top:4px;}
.card-versions-count{font-size:12px;color:var(--text-dim);display:inline-flex;align-items:center;gap:4px;}
.card-versions-count svg{width:14px;height:14px;}
.card-chevron{color:var(--text-dim);}
.card-chevron svg{width:16px;height:16px;}
.official-badge{display:inline-flex;align-items:center;gap:3px;font-size:10px;color:var(--green);background:rgba(22,163,74,0.08);padding:2px 6px;border-radius:4px;}
.official-badge svg{width:11px;height:11px;}
.no-results{text-align:center;padding:60px 20px;color:var(--text-dim);}
.footer{text-align:center;padding:24px;color:var(--text-dim);font-size:12px;border-top:1px solid var(--border);margin-top:40px;}
.version-list{display:flex;flex-direction:column;gap:10px;}
.version-item{display:flex;align-items:center;gap:16px;padding:14px 16px;background:var(--bg-card);border:1px solid var(--border);border-radius:var(--radius);transition:all 0.2s;}
.version-item:hover{border-color:var(--border-bright);box-shadow:var(--shadow);}
.version-info{flex:1;min-width:0;}
.version-number{font-size:15px;font-weight:600;color:var(--text-bright);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
.version-meta{font-size:12px;color:var(--text-dim);margin-top:2px;}
.btn{display:inline-flex;align-items:center;justify-content:center;gap:4px;padding:8px 18px;border-radius:8px;font-size:13px;font-weight:500;cursor:pointer;text-decoration:none;transition:all 0.15s;border:none;}
.btn svg{width:14px;height:14px;}
.btn-download{background:var(--accent);color:#fff;}
.btn-download:hover{background:#3a6aff;}
.btn-official{background:transparent;border:1px solid var(--green);color:var(--green);}
.btn-official:hover{background:rgba(22,163,74,0.08);}
.btn-back{background:transparent;border:1px solid var(--border-bright);color:var(--text-dim);}
.btn-back:hover{border-color:var(--accent);color:var(--accent);}
.btn-primary{background:var(--accent);color:#fff;}
.btn-primary:hover{background:#3a6aff;}
.btn-danger{background:transparent;border:1px solid var(--red);color:var(--red);}
.btn-danger:hover{background:rgba(220,38,38,0.08);}
.btn-sm{padding:5px 10px;font-size:12px;}
.breadcrumb{display:flex;align-items:center;gap:8px;margin-bottom:20px;font-size:13px;color:var(--text-dim);}
.breadcrumb a{cursor:pointer;color:var(--text-dim);text-decoration:none;}
.breadcrumb a:hover{color:var(--accent);}
.breadcrumb svg{width:14px;height:14px;}
.scan-badge{display:inline-flex;align-items:center;gap:4px;font-size:11px;color:var(--text-dim);}
.scan-badge .dot{width:8px;height:8px;border-radius:50%;background:var(--green);display:inline-block;animation:pulse 2s infinite;}
@keyframes pulse{0%,100%{opacity:1;}50%{opacity:0.4;}}
@keyframes fadeIn{from{opacity:0;transform:translateY(8px);}to{opacity:1;transform:translateY(0);}}
.card{animation:fadeIn 0.3s ease-out;}
@keyframes spin{from{transform:rotate(0deg);}to{transform:rotate(360deg);}}
.spinning svg{animation:spin 1s linear infinite;}
@media(max-width:768px){.header-inner{flex-direction:column;align-items:stretch;}.stats{justify-content:center;}.grid{grid-template-columns:1fr;}}
::-webkit-scrollbar{width:8px;height:8px;}
::-webkit-scrollbar-track{background:transparent;}
::-webkit-scrollbar-thumb{background:var(--border-bright);border-radius:4px;}
::-webkit-scrollbar-thumb:hover{background:#a8acb8;}
.toast{position:fixed;bottom:30px;left:50%;transform:translateX(-50%);background:#1a1d28;color:#fff;padding:10px 24px;border-radius:8px;font-size:13px;z-index:9999;opacity:0;transition:opacity 0.3s;box-shadow:0 4px 12px rgba(0,0,0,0.2);}
.toast.show{opacity:1;}
/* Auth modal */
.modal-overlay{position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.4);z-index:2000;display:flex;align-items:center;justify-content:center;}
.modal{background:var(--bg-card);border-radius:16px;padding:32px;max-width:400px;width:90%;box-shadow:var(--shadow-lg);}
.modal h2{font-size:20px;color:var(--text-bright);margin-bottom:20px;display:flex;align-items:center;gap:8px;}
.modal h2 svg{width:22px;height:22px;color:var(--accent);}
.form-group{margin-bottom:16px;}
.form-group label{display:block;font-size:13px;color:var(--text-dim);margin-bottom:6px;}
.form-group input{width:100%;padding:10px 14px;border:1px solid var(--border);border-radius:8px;font-size:14px;color:var(--text);outline:none;transition:all 0.2s;}
.form-group input:focus{border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-glow);}
.modal-btns{display:flex;gap:10px;margin-top:20px;}
.modal-error{color:var(--red);font-size:13px;margin-bottom:10px;display:none;}
/* Admin panels */
.admin-section{background:var(--bg-card);border:1px solid var(--border);border-radius:var(--radius);padding:20px;margin-bottom:20px;}
.admin-section h3{font-size:15px;color:var(--text-bright);margin-bottom:14px;display:flex;align-items:center;gap:8px;}
.admin-section h3 svg{width:18px;height:18px;color:var(--purple);}
.edit-row{display:flex;align-items:center;gap:10px;padding:10px 0;border-bottom:1px solid var(--border);}
.edit-row:last-child{border-bottom:none;}
.edit-row input{flex:1;padding:6px 10px;border:1px solid var(--border);border-radius:6px;font-size:13px;outline:none;}
.edit-row input:focus{border-color:var(--accent);}
.edit-row label{font-size:12px;color:var(--text-dim);min-width:80px;}
.upload-area{border:2px dashed var(--border-bright);border-radius:12px;padding:40px;text-align:center;cursor:pointer;transition:all 0.2s;}
.upload-area:hover{border-color:var(--accent);background:var(--accent-soft);}
.upload-area svg{width:40px;height:40px;color:var(--text-dim);margin-bottom:10px;}
.upload-area p{color:var(--text-dim);font-size:14px;}
.upload-progress{margin-top:12px;}
.progress-bar{width:100%;height:6px;background:var(--bg-search);border-radius:3px;overflow:hidden;}
.progress-fill{height:100%;background:var(--accent);transition:width 0.3s;}
.user-row{display:flex;align-items:center;gap:12px;padding:10px 0;border-bottom:1px solid var(--border);}
.user-row:last-child{border-bottom:none;}
.user-row .user-info{flex:1;}
.user-row .user-name{font-size:14px;font-weight:500;color:var(--text-bright);}
.user-row .user-role{font-size:12px;color:var(--text-dim);}
.role-badge{display:inline-block;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:500;}
.role-badge.admin{background:var(--purple-soft);color:var(--purple);}
.role-badge.user{background:var(--accent-soft);color:var(--accent);}
</style>"""

    # ---- HTML body ----
    body = f"""</head>
<body>
<div class="header"><div class="header-inner">
  <div class="logo" onclick="goHome()"><div class="logo-icon">{get_svg("package")}</div><div class="logo-text"><h1>软件库 <span class="scan-badge"><span class="dot"></span> Live</span></h1><span>Software Library</span></div></div>
  <div class="search-box"><span class="search-icon">{get_svg("search")}</span><input type="text" id="searchInput" placeholder="搜索软件名..." autocomplete="off" oninput="onSearch(this.value)"></div>
  <div class="stats"><div class="stat-item"><div class="num" id="statCount">{total_files}</div><div class="label">文件</div></div><div class="stat-item"><div class="num">{len(categories)}</div><div class="label">分类</div></div><div class="stat-item"><div class="num">{total_size_text}</div><div class="label">总量</div></div></div>
  <div class="header-btns" id="headerBtns"></div>
</div></div>
<div class="container" id="container"></div>
<div class="footer"><p>软件库 · 共 {total_files} 个文件 · 总计 {total_size_text}</p><p style="margin-top:4px;">最后更新: {now_str}</p></div>
<div id="modalContainer"></div>
"""

    # ---- JS ----
    js = """<script>
const ICONS=__ICONS_JSON__;
const CAT_ICONS=__CAT_ICONS_JSON__;
const HAS_USERS=__HAS_USERS__;
let SESSION=null;
let ALL_DATA=[];
let currentView='home',currentSoftware=null,searchTerm='',currentCat='all';

function svg(n,s){const v=ICONS[n]||ICONS['box'];return '<span style="width:'+(s||26)+'px;height:'+(s||26)+'px;display:inline-flex;align-items:center;justify-content:center">'+v+'</span>';}
function esc(s){const d=document.createElement('div');d.textContent=s||'';return d.innerHTML;}

function showToast(msg){let t=document.getElementById('toast');if(!t){t=document.createElement('div');t.id='toast';t.className='toast';document.body.appendChild(t);}t.textContent=msg;t.classList.add('show');clearTimeout(t._timer);t._timer=setTimeout(()=>t.classList.remove('show'),2500);}

function getCookie(n){const m=document.cookie.match(new RegExp('(^| )'+n+'=([^;]+)'));return m?m[2]:'';}
function setCookie(n,v,d){const e=new Date();e.setTime(e.getTime()+d*86400000);document.cookie=n+'='+v+';expires='+e.toUTCString()+';path=/';}
function delCookie(n){document.cookie=n+'=;expires=Thu,01 Jan 1970 00:00:00 UTC;path=/';}

async function api(url,opts){
  opts=opts||{};
  opts.headers=opts.headers||{};
  if(SESSION)opts.headers['X-Session']=SESSION;
  if(opts.body&&typeof opts.body==='object'){opts.headers['Content-Type']='application/json';opts.body=JSON.stringify(opts.body);}
  const r=await fetch(url,opts);
  return r.json();
}

function renderHeaderBtns(){
  const c=document.getElementById('headerBtns');
  if(!SESSION){
    if(HAS_USERS){
      c.innerHTML='<button class="header-btn" onclick="showLogin()">'+svg('lock',14)+' 登录</button>';
    }else{
      c.innerHTML='<button class="header-btn" onclick="showRegister()">'+svg('plus',14)+' 注册管理员</button>';
    }
  }else{
    let h='<button class="header-btn" onclick="doUpload()">'+svg('upload',14)+' 上传</button>';
    if(SESSION.role==='admin')h+='<button class="header-btn admin-btn" onclick="goAdmin()">'+svg('settings',14)+' 管理</button>';
    h+='<button class="header-btn" onclick="goHome()">'+svg('package',14)+' 首页</button>';
    h+='<button class="header-btn danger" onclick="doLogout()">'+svg('logout',14)+' 退出</button>';
    c.innerHTML=h;
  }
}

function showLogin(){
  const mc=document.getElementById('modalContainer');
  mc.innerHTML='<div class="modal-overlay" onclick="if(event.target===this)closeModal()"><div class="modal"><h2>'+svg('lock',22)+' 登录</h2><div class="modal-error" id="loginErr"></div><div class="form-group"><label>用户名</label><input type="text" id="loginUser" placeholder="输入用户名" autocomplete="username"></div><div class="form-group"><label>密码</label><input type="password" id="loginPass" placeholder="输入密码" autocomplete="current-password" onkeydown="if(event.key===\\'Enter\\')doLogin()"></div><div class="modal-btns"><button class="btn btn-primary" style="flex:1" onclick="doLogin()">'+svg('lock',14)+' 登录</button><button class="btn btn-back" onclick="closeModal()">取消</button></div></div></div>';
  setTimeout(()=>document.getElementById('loginUser').focus(),100);
}
function showRegister(){
  const mc=document.getElementById('modalContainer');
  mc.innerHTML='<div class="modal-overlay" onclick="if(event.target===this)closeModal()"><div class="modal"><h2>'+svg('user',22)+' 注册管理员</h2><p style="font-size:13px;color:var(--text-dim);margin-bottom:16px">首次使用，请创建管理员账号。此账号可管理用户和软件。</p><div class="modal-error" id="regErr"></div><div class="form-group"><label>用户名</label><input type="text" id="regUser" placeholder="创建用户名"></div><div class="form-group"><label>密码</label><input type="password" id="regPass" placeholder="创建密码"></div><div class="form-group"><label>确认密码</label><input type="password" id="regPass2" placeholder="再次输入密码" onkeydown="if(event.key===\\'Enter\\')doRegister()"></div><div class="modal-btns"><button class="btn btn-primary" style="flex:1" onclick="doRegister()">'+svg('plus',14)+' 注册</button></div></div></div>';
  setTimeout(()=>document.getElementById('regUser').focus(),100);
}
function closeModal(){document.getElementById('modalContainer').innerHTML='';}

async function doLogin(){
  const u=document.getElementById('loginUser').value.trim();
  const p=document.getElementById('loginPass').value;
  if(!u||!p){document.getElementById('loginErr').style.display='block';document.getElementById('loginErr').textContent='请填写用户名和密码';return;}
  const r=await api('/api/login',{method:'POST',body:{username:u,password:p}});
  if(r.success){SESSION=r.session;setCookie('session',r.session,1);closeModal();renderHeaderBtns();render();showToast('登录成功');}
  else{document.getElementById('loginErr').style.display='block';document.getElementById('loginErr').textContent=r.error||'登录失败';}
}
async function doRegister(){
  const u=document.getElementById('regUser').value.trim();
  const p=document.getElementById('regPass').value;
  const p2=document.getElementById('regPass2').value;
  if(!u||!p){document.getElementById('regErr').style.display='block';document.getElementById('regErr').textContent='请填写用户名和密码';return;}
  if(p!==p2){document.getElementById('regErr').style.display='block';document.getElementById('regErr').textContent='两次密码不一致';return;}
  const r=await api('/api/register',{method:'POST',body:{username:u,password:p}});
  if(r.success){SESSION=r.session;setCookie('session',r.session,1);closeModal();renderHeaderBtns();render();showToast('注册成功，欢迎！');}
  else{document.getElementById('regErr').style.display='block';document.getElementById('regErr').textContent=r.error||'注册失败';}
}
function doLogout(){delCookie('session');SESSION=null;renderHeaderBtns();render();showToast('已退出');}

function goHome(){currentView='home';currentSoftware=null;render();}
function goAdmin(){if(!SESSION||SESSION.role!=='admin')return;currentView='admin';render();}
function goVersion(name){currentView='version';currentSoftware=name;render();}
function onSearch(v){searchTerm=v.toLowerCase().trim();if(currentView!=='home')goHome();render();}
function selectCategory(cat){currentCat=cat;render();}

function getFiltered(){let d=ALL_DATA;if(currentCat!=='all')d=d.filter(s=>s.category===currentCat);if(searchTerm)d=d.filter(s=>(s.name+' '+s.desc+' '+s.category).toLowerCase().includes(searchTerm));return d;}

function renderCatSelect(){
  const cats=['all',...new Set(ALL_DATA.map(s=>s.category))];
  let opts='<option value="all">全部分类 ('+ALL_DATA.length+')</option>';
  for(const c of cats){if(c==='all')continue;const n=ALL_DATA.filter(s=>s.category===c).length;opts+='<option value="'+esc(c)+'"'+(currentCat===c?' selected':'')+'>'+esc(c)+' ('+n+')</option>';}
  return '<div class="cat-select"><select onchange="selectCategory(this.value)">'+opts+'</select></div>';
}

function render(){
  const c=document.getElementById('container');
  if(currentView==='home')renderHome(c);
  else if(currentView==='version')renderVersionPage(c);
  else if(currentView==='admin')renderAdmin(c);
}

function renderHome(c){
  let h=renderCatSelect();
  const d=getFiltered();
  document.getElementById('statCount').textContent=d.reduce((a,s)=>a+s.versions.length,0);
  if(d.length===0){h+='<div class="no-results">'+svg('search',48)+'<p style="margin-top:16px">没有找到匹配的文件</p></div>';c.innerHTML=h;return;}
  const grouped={};d.forEach(s=>{if(!grouped[s.category])grouped[s.category]=[];grouped[s.category].push(s);});
  for(const cat of Object.keys(grouped).sort()){
    const items=grouped[cat];
    h+='<div class="section"><div class="section-header">'+svg(CAT_ICONS[cat]||'box',22)+'<h2>'+esc(cat)+' ('+items.length+')</h2></div><div class="grid">';
    for(const sw of items){
      const vc=sw.versions.length;const latest=sw.versions[0]||{};
      h+='<div class="card" onclick="goVersion(\\''+esc(sw.name).replace(/'/g,"\\\\'")+'\\')"><div class="card-top"><div class="card-icon">'+svg(sw.icon,26)+'</div><div class="card-info"><div class="card-title">'+esc(sw.name)+'</div><div class="card-desc">'+esc(sw.desc)+'</div></div></div><div class="card-meta"><span class="meta-tag type">'+(latest.fileType||'')+'</span><span class="meta-tag size">'+(latest.sizeText||'')+'</span>';
      if(latest.date)h+='<span class="meta-tag date">'+latest.date+'</span>';
      h+='</div><div class="card-footer">';
      if(sw.showOfficial&&sw.official)h+='<span class="official-badge">'+svg('external',11)+' 官网下载</span>';
      h+='<span class="card-versions-count">'+svg('layers',14)+vc+' 个版本</span><span class="card-chevron">'+svg('chevron',16)+'</span></div></div>';
    }
    h+='</div></div>';
  }
  c.innerHTML=h;
}

function renderVersionPage(c){
  const sw=ALL_DATA.find(s=>s.name===currentSoftware);
  if(!sw){goHome();return;}
  let h='<div class="breadcrumb"><a onclick="goHome()">'+svg('back',14)+' 首页</a> / <span>'+esc(sw.name)+'</span></div>';
  h+='<div class="section"><div class="section-header">'+svg(sw.icon,22)+'<h2>'+esc(sw.name)+'</h2>';
  if(sw.showOfficial&&sw.official)h+='<a class="btn btn-official" href="'+esc(sw.official)+'" target="_blank">'+svg('external',14)+' 去官网下载最新版</a>';
  h+='</div><div style="font-size:13px;color:var(--text-dim);margin-bottom:16px">'+esc(sw.desc)+'</div><div class="version-list">';
  for(const v of sw.versions){
    const dlUrl='/download/'+encodeURIComponent(v.path);
    h+='<div class="version-item"><div class="card-icon" style="width:40px;height:40px">'+svg(sw.icon,20)+'</div><div class="version-info"><div class="version-number">'+esc(v.filename)+'</div><div class="version-meta">'+esc(v.fileType)+' · '+v.sizeText+(v.date?(' · '+v.date):'')+'</div></div><a class="btn btn-download" href="'+dlUrl+'" download="'+esc(v.filename)+'">'+svg('download',14)+' 下载</a></div>';
  }
  h+='</div></div>';
  c.innerHTML=h;
}

function renderAdmin(c){
  if(!SESSION||SESSION.role!=='admin'){c.innerHTML='<div class="no-results">'+svg('lock',48)+'<p style="margin-top:16px">需要管理员权限</p></div>';return;}
  let h='';
  // Software management
  h+='<div class="admin-section"><h3>'+svg('package',18)+' 软件管理</h3>';
  h+='<p style="color:var(--text-dim);font-size:13px;margin-bottom:14px">编辑软件的官网下载地址和显示设置。扫描结果自动生成，此处的编辑会覆盖默认值。</p>';
  for(const sw of ALL_DATA){
    h+='<div class="edit-row"><label>'+esc(sw.name)+'</label><input type="text" id="official_'+sw.name.replace(/[^a-zA-Z0-9]/g,'_')+'" value="'+esc(sw.official||'')+'" placeholder="官网下载地址">';
    h+='<button class="btn btn-sm '+(sw.showOfficial?'btn-danger':'btn-primary')+'" onclick="toggleOfficial(\\''+esc(sw.name).replace(/'/g,"\\\\'")+'\\')">'+(sw.showOfficial?'取消官网':'标记官网')+'</button>';
    h+='<button class="btn btn-sm btn-primary" onclick="saveOfficial(\\''+esc(sw.name).replace(/'/g,"\\\\'")+'\\')">'+svg('save',14)+'</button></div>';
  }
  h+='</div>';
  // User management
  h+='<div class="admin-section"><h3>'+svg('users',18)+' 用户管理</h3><div id="userList">加载中...</div>';
  h+='<div class="edit-row" style="margin-top:12px"><input type="text" id="newUser" placeholder="新用户名" style="flex:1"><input type="password" id="newPass" placeholder="密码" style="flex:1"><select id="newRole" style="padding:6px;border:1px solid var(--border);border-radius:6px;font-size:13px"><option value="user">普通用户</option><option value="admin">管理员</option></select><button class="btn btn-sm btn-primary" onclick="addUser()">'+svg('plus',14)+' 添加</button></div>';
  h+='</div>';
  // Rescan
  h+='<div class="admin-section"><h3>'+svg('refresh',18)+' 扫描管理</h3><button class="btn btn-primary" id="rescanBtn2" onclick="doRescan()">'+svg('refresh',14)+' 立即重新扫描</button></div>';
  c.innerHTML=h;
  loadUserList();
}

async function loadUserList(){
  const r=await api('/api/users');
  if(!r.success)return;
  let h='';
  for(const u of r.users){
    h+='<div class="user-row"><div class="user-info"><div class="user-name">'+esc(u.username)+'</div><div class="user-role">'+esc(u.created)+'</div></div><span class="role-badge '+u.role+'">'+(u.role==='admin'?'管理员':'普通用户')+'</span>';
    if(u.username!==SESSION.username)h+='<button class="btn btn-sm btn-danger" onclick="delUser(\\''+esc(u.username).replace(/'/g,"\\\\'")+'\\')">删除</button>';
    h+='</div>';
  }
  document.getElementById('userList').innerHTML=h||'<p style="color:var(--text-dim);font-size:13px">暂无其他用户</p>';
}

async function addUser(){
  const u=document.getElementById('newUser').value.trim();
  const p=document.getElementById('newPass').value;
  const r2=document.getElementById('newRole').value;
  if(!u||!p){showToast('请填写用户名和密码');return;}
  const r=await api('/api/users',{method:'POST',body:{username:u,password:p,role:r2}});
  if(r.success){showToast('用户已添加');loadUserList();document.getElementById('newUser').value='';document.getElementById('newPass').value='';}
  else{showToast(r.error||'添加失败');}
}
async function delUser(name){
  if(!confirm('确认删除用户 '+name+'？'))return;
  const r=await api('/api/users/'+encodeURIComponent(name),{method:'DELETE'});
  if(r.success){showToast('已删除');loadUserList();}
  else{showToast(r.error||'删除失败');}
}

async function toggleOfficial(name){
  const sw=ALL_DATA.find(s=>s.name===name);if(!sw)return;
  const newVal=!sw.showOfficial;
  const r=await api('/api/admin/software',{method:'PUT',body:{name:name,showOfficial:newVal}});
  if(r.success){sw.showOfficial=newVal;renderAdmin(document.getElementById('container'));showToast(newVal?'已显示官网下载':'已隐藏官网下载');}
  else{showToast(r.error||'操作失败');}
}
async function saveOfficial(name){
  const inp=document.getElementById('official_'+name.replace(/[^a-zA-Z0-9]/g,'_'));
  const url=inp?inp.value.trim():'';
  const r=await api('/api/admin/software',{method:'PUT',body:{name:name,official:url,showOfficial:true}});
  if(r.success){const sw=ALL_DATA.find(s=>s.name===name);if(sw){sw.official=url;sw.showOfficial=true;}showToast('已保存官网地址');}
  else{showToast(r.error||'保存失败');}
}

function doUpload(){
  if(!SESSION){showToast('请先登录');return;}
  const mc=document.getElementById('modalContainer');
  mc.innerHTML='<div class="modal-overlay" onclick="if(event.target===this)closeModal()"><div class="modal" style="max-width:500px"><h2>'+svg('upload',22)+' 上传文件</h2><div class="upload-area" id="uploadArea" onclick="document.getElementById(\\'fileInput\\').click()">'+svg('upload',40)+'<p>点击或拖拽文件到此处上传</p></div><input type="file" id="fileInput" style="display:none" onchange="handleFile(this.files[0])"><div id="uploadProgress" style="display:none"><div class="upload-progress"><div class="progress-bar"><div class="progress-fill" id="progressFill" style="width:0%"></div></div><p style="text-align:center;margin-top:8px;font-size:13px;color:var(--text-dim)" id="uploadStatus">上传中...</p></div></div><div class="modal-btns"><button class="btn btn-back" onclick="closeModal()">关闭</button></div></div></div>';
  const area=document.getElementById('uploadArea');
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
  xhr.addEventListener('load',function(){const r=JSON.parse(xhr.responseText);if(r.success){showToast('上传成功');closeModal();setTimeout(()=>location.reload(),1000);}else{showToast(r.error||'上传失败');document.getElementById('uploadProgress').style.display='none';document.getElementById('uploadArea').style.display='block';}});
  xhr.addEventListener('error',function(){showToast('上传失败');document.getElementById('uploadProgress').style.display='none';document.getElementById('uploadArea').style.display='block';});
  xhr.open('POST','/api/upload');
  if(SESSION)xhr.setRequestHeader('X-Session',SESSION);
  xhr.send(formData);
}

async function doRescan(){
  const btn=document.getElementById('rescanBtn2')||document.getElementById('rescanBtn');
  if(!btn)return;
  btn.classList.add('spinning');btn.innerHTML=svg('refresh',14)+' 扫描中';
  try{
    const r=await api('/api/rescan',{method:'POST'});
    if(r.success){showToast('扫描完成: '+r.totalFiles+' 个文件');setTimeout(()=>location.reload(),1500);}
    else{showToast('扫描失败');btn.classList.remove('spinning');btn.innerHTML=svg('refresh',14)+' 重新扫描';}
  }catch(e){showToast('请求失败');btn.classList.remove('spinning');btn.innerHTML=svg('refresh',14)+' 重新扫描';}
}

async function loadData(){
  const r=await fetch('/api/software');
  const d=await r.json();
  if(d.success)ALL_DATA=d.data;
}

async function init(){
  const token=getCookie('session');
  if(token){
    const r=await api('/api/session');
    if(r.success){SESSION={username:r.username,role:r.role};}
  }
  await loadData();
  renderHeaderBtns();
  if(!SESSION&&!HAS_USERS){showRegister();}
  else if(!SESSION&&HAS_USERS){showLogin();}
  render();
}
init();
</script>
</body>
</html>"""

    js = js.replace("__ICONS_JSON__", icons_json)
    js = js.replace("__CAT_ICONS_JSON__", cat_icons_json)
    js = js.replace("__HAS_USERS__", "true" if has_registered_users else "false")

    html = "<!DOCTYPE html>\n<html lang=\"zh-CN\">\n<head>\n<meta charset=\"UTF-8\">\n<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">\n<title>软件库 | Software Library</title>\n" + css + "\n" + body + js
    return html

# ============================================================
# HTTP Handler
# ============================================================

_scan_lock = threading.Lock()
_last_scan_time = ""

class SoftwareHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DATA_DIR, **kwargs)

    def _get_session(self):
        token = self.headers.get('X-Session', '')
        if not token:
            # Also check cookie
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
            self._serve_json({"success": False, "error": "权限不足"})
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
            safe_path = os.path.normpath(os.path.join(ROOT_DIR, rel_path))
            if not safe_path.startswith(os.path.normpath(ROOT_DIR)):
                self.send_error(403, "Forbidden")
                return
            if os.path.isfile(safe_path):
                self._serve_download(safe_path)
            else:
                self.send_error(404, "File not found")
            return

        if path == '/api/software':
            sw_list = build_software_list()
            self._serve_json({"success": True, "data": sw_list})
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
            if not s: return
            users = load_users()
            safe_users = [{"username": u["username"], "role": u["role"], "created": u.get("created","")} for u in users.get("users",[])]
            self._serve_json({"success": True, "users": safe_users})
            return

        if path == '/api/scan-status':
            self._serve_json({"scanning": _scan_lock.locked(), "lastScan": _last_scan_time})
            return

        if path == '/api/config':
            config = load_json(CONFIG_FILE, default_config())
            self._serve_json(config)
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
            s = self._require_auth()
            if not s: return
            self._handle_rescan()
            return

        if path == '/api/admin/software':
            s = self._require_auth()
            if not s: return
            self._handle_admin_software()
            return

        if path == '/api/upload':
            s = self._require_auth()
            if not s: return
            self._handle_upload()
            return

        if path == '/api/users':
            s = self._require_auth('admin')
            if not s: return
            self._handle_add_user()
            return

        self.send_error(404, "Not found")

    def do_PUT(self):
        parsed = urllib.parse.urlparse(self.path)
        path = urllib.parse.unquote(parsed.path)
        if path == '/api/admin/software':
            s = self._require_auth()
            if not s: return
            self._handle_admin_software()
            return
        self.send_error(404, "Not found")

    def do_DELETE(self):
        parsed = urllib.parse.urlparse(self.path)
        path = urllib.parse.unquote(parsed.path)
        if path.startswith('/api/admin/software/'):
            s = self._require_auth()
            if not s: return
            name = urllib.parse.unquote(path[len('/api/admin/software/'):])
            self._handle_admin_delete(name)
            return
        if path.startswith('/api/users/'):
            s = self._require_auth('admin')
            if not s: return
            name = urllib.parse.unquote(path[len('/api/users/'):])
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
            self._serve_json({"success": False, "error": "已存在用户，请联系管理员"})
            return
        ok, msg = create_user(username, password, role="admin")
        if ok:
            token = create_session(username, "admin")
            self._serve_json({"success": True, "session": token, "role": "admin"})
        else:
            self._serve_json({"success": False, "error": msg})

    def _handle_login(self):
        data = self._read_body()
        username = data.get("username", "").strip()
        password = data.get("password", "")
        ok, result = verify_user(username, password)
        if ok:
            token = create_session(username, result["role"])
            self._serve_json({"success": True, "session": token, "role": result["role"]})
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

    def _handle_upload(self):
        try:
            ctype = self.headers.get('Content-Type', '')
            # Parse multipart form data
            if 'multipart/form-data' not in ctype:
                self._serve_json({"success": False, "error": "需要文件上传"})
                return
            # Simple multipart parser
            boundary = ctype.split('boundary=')[1].encode()
            remaining = int(self.headers.get('Content-Length', 0))
            if remaining > MAX_UPLOAD_SIZE:
                self._serve_json({"success": False, "error": "文件太大"})
                return
            body_data = self.rfile.read(remaining)
            parts = body_data.split(b'--' + boundary)
            filename = None
            file_data = None
            for part in parts:
                if b'Content-Disposition' in part and b'filename=' in part:
                    # Extract filename
                    disp_match = re.search(rb'filename="([^"]+)"', part)
                    if disp_match:
                        filename = disp_match.group(1).decode('utf-8', errors='replace')
                    # Extract file data (after double newline)
                    idx = part.find(b'\r\n\r\n')
                    if idx >= 0:
                        file_data = part[idx+4:]
                        # Strip trailing \r\n
                        if file_data.endswith(b'\r\n'):
                            file_data = file_data[:-2]
            if not filename or file_data is None:
                self._serve_json({"success": False, "error": "未找到文件"})
                return
            os.makedirs(UPLOAD_DIR, exist_ok=True)
            safe_name = os.path.basename(filename)
            save_path = os.path.join(UPLOAD_DIR, safe_name)
            with open(save_path, 'wb') as f:
                f.write(file_data)
            self._serve_json({"success": True, "message": "上传成功", "filename": safe_name})
        except Exception as e:
            self._serve_json({"success": False, "error": str(e)})

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

    def _handle_rescan(self):
        global _last_scan_time
        if _scan_lock.locked():
            self._serve_json({"success": False, "error": "扫描正在进行中"})
            return
        def do_scan():
            global _last_scan_time
            with _scan_lock:
                try:
                    items = run_scan()
                    _last_scan_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    html = generate_html()
                    with open(HTML_FILE, 'w', encoding='utf-8') as f:
                        f.write(html)
                except Exception as e:
                    print(f"Rescan error: {e}")
        t = threading.Thread(target=do_scan, daemon=True)
        t.start()
        scan_data = load_json(SCAN_FILE, {"totalFiles": 0})
        self._serve_json({"success": True, "message": "扫描已启动", "totalFiles": scan_data.get("totalFiles", 0)})

    def _handle_admin_software(self):
        try:
            data = self._read_body()
            name = data.get("name")
            if not name:
                self._serve_json({"success": False, "error": "name is required"})
                return
            config = load_json(CONFIG_FILE, default_config())
            if "software" not in config:
                config["software"] = {}
            if name not in config["software"]:
                config["software"][name] = {}
            sw_cfg = config["software"][name]
            for key in ["category", "icon", "desc", "official", "showOfficial", "customOrder"]:
                if key in data:
                    sw_cfg[key] = data[key]
            save_json(CONFIG_FILE, config)
            self._serve_json({"success": True, "message": "已更新"})
        except Exception as e:
            self._serve_json({"success": False, "error": str(e)})

    def _handle_admin_delete(self, name):
        config = load_json(CONFIG_FILE, default_config())
        if name in config.get("software", {}):
            del config["software"][name]
            save_json(CONFIG_FILE, config)
            self._serve_json({"success": True, "message": "已删除"})
        else:
            self._serve_json({"success": False, "error": "未找到"})

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
    print(f"\n{'='*55}")
    print(f"  Software Library Manager v4 Running")
    print(f"  URL: http://0.0.0.0:{port}")
    print(f"  Root: {ROOT_DIR}")
    print(f"  Data: {DATA_DIR}")
    print(f"  Users: {'Registered' if has_users() else 'No users yet (will register on first visit)'}")
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
            html = generate_html()
            with open(HTML_FILE, 'w', encoding='utf-8') as f:
                f.write(html)
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
        run_scan()
    html = generate_html()
    with open(HTML_FILE, 'w', encoding='utf-8') as f:
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
