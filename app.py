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
import urllib.parse
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
    "mwrt": {"name":"Mwrt (四字真言)","category":"路由器/软路由","icon":"router","desc":"Mwrt 软路由固件","official":""},
    "lean code": {"name":"Lean Code 固件","category":"路由器/软路由","icon":"router","desc":"Lean Code OpenWrt 固件合集","official":""},
    "ezopwrt": {"name":"EzOpWrt","category":"路由器/软路由","icon":"router","desc":"EzOpWrt 软路由固件","official":""},
    "bleachwrt": {"name":"BleachWrt","category":"路由器/软路由","icon":"router","desc":"BleachWrt 软路由固件","official":""},
    "kwrt": {"name":"KWrt","category":"路由器/软路由","icon":"router","desc":"KWrt 软路由固件","official":""},
    "lede": {"name":"LEDE","category":"路由器/软路由","icon":"router","desc":"LEDE 软路由固件","official":""},
    "immortalwrt": {"name":"ImmortalWrt","category":"路由器/软路由","icon":"router","desc":"ImmortalWrt 软路由固件","official":"https://immortalwrt.org"},
    "docker-immortalwrt": {"name":"Docker ImmortalWrt","category":"路由器/软路由","icon":"router","desc":"带 Docker 的 ImmortalWrt 固件","official":"https://immortalwrt.org"},
    "sql server": {"name":"SQL Server","category":"数据库","icon":"database","desc":"Microsoft SQL Server 数据库","official":"https://www.microsoft.com/sql-server"},
    "sqlserver": {"name":"SQL Server","category":"数据库","icon":"database","desc":"Microsoft SQL Server 数据库","official":"https://www.microsoft.com/sql-server"},
    "mysql": {"name":"MySQL","category":"数据库","icon":"database","desc":"MySQL 数据库","official":"https://www.mysql.com"},
    "redis": {"name":"Redis","category":"数据库","icon":"database","desc":"Redis 内存数据库","official":"https://redis.io"},
    "office": {"name":"Microsoft Office","category":"办公软件","icon":"office","desc":"Microsoft Office 办公套件","official":"https://www.microsoft.com/microsoft-365"},
    "adobe": {"name":"Adobe","category":"设计/创意","icon":"adobe","desc":"Adobe 创意套件","official":"https://www.adobe.com"},
    "acrobat": {"name":"Adobe Acrobat","category":"设计/创意","icon":"pdf","desc":"Adobe Acrobat PDF 编辑器","official":"https://www.adobe.com/acrobat.html"},
    "wps": {"name":"WPS Office","category":"办公软件","icon":"office","desc":"WPS Office 办公套件","official":"https://www.wps.cn"},
    "creative cloud": {"name":"Adobe Creative Cloud","category":"设计/创意","icon":"adobe","desc":"Adobe Creative Cloud 创意套件","official":"https://www.adobe.com/creativecloud.html"},
    "git": {"name":"Git","category":"开发工具","icon":"code","desc":"Git 版本控制工具","official":"https://git-scm.com"},
    "jdk": {"name":"JDK (Java)","category":"开发工具","icon":"java","desc":"Java Development Kit","official":"https://www.oracle.com/java/technologies/downloads/"},
    "python": {"name":"Python","category":"开发工具","icon":"python","desc":"Python 编程语言","official":"https://www.python.org"},
    "pycharm": {"name":"PyCharm","category":"开发工具","icon":"code","desc":"PyCharm Python IDE","official":"https://www.jetbrains.com/pycharm/"},
    "jetbrains": {"name":"JetBrains Patch","category":"开发工具","icon":"code","desc":"JetBrains IDE 补丁","official":"https://www.jetbrains.com"},
    "navicat": {"name":"Navicat Premium","category":"数据库","icon":"database","desc":"Navicat 数据库管理工具","official":"https://www.navicat.com"},
    "mobaxterm": {"name":"MobaXterm","category":"开发工具","icon":"terminal","desc":"MobaXterm 终端工具","official":"https://mobaxterm.mobatek.net"},
    "xshell": {"name":"Xshell Plus","category":"开发工具","icon":"terminal","desc":"Xshell 终端模拟器","official":"https://www.xshell.com"},
    "sublime": {"name":"Sublime Text","category":"开发工具","icon":"code","desc":"Sublime Text 代码编辑器","official":"https://www.sublimetext.com"},
    "apifox": {"name":"Apifox","category":"开发工具","icon":"code","desc":"Apifox API 调试工具","official":"https://apifox.com"},
    "diskgenius": {"name":"DiskGenius","category":"系统工具","icon":"disk","desc":"DiskGenius 磁盘分区管理工具","official":"https://www.diskgenius.com"},
    "ultraiso": {"name":"UltraISO","category":"系统工具","icon":"disk","desc":"UltraISO 光盘镜像工具","official":"https://www.ultraiso.com"},
    "winrar": {"name":"WinRAR","category":"系统工具","icon":"archive","desc":"WinRAR 压缩解压工具","official":"https://www.rarlab.com"},
    "rufus": {"name":"Rufus","category":"系统工具","icon":"usb","desc":"Rufus USB 启动盘制作工具","official":"https://rufus.ie"},
    "balenaetcher": {"name":"balenaEtcher","category":"系统工具","icon":"usb","desc":"balenaEtcher 镜像写入工具","official":"https://etcher.balena.io"},
    "win32diskimager": {"name":"Win32 Disk Imager","category":"系统工具","icon":"usb","desc":"Win32 Disk Imager 镜像写入工具","official":"https://sourceforge.net/projects/win32diskimager/"},
    "geek": {"name":"Geek Uninstaller","category":"系统工具","icon":"trash","desc":"Geek 卸载器，强力卸载","official":"https://geekuninstaller.com"},
    "dism": {"name":"Dism++","category":"系统工具","icon":"wrench","desc":"Dism++ Windows 优化工具","official":"http://www.chuyu.me"},
    "startallback": {"name":"StartAllBack","category":"系统工具","icon":"windows","desc":"StartAllBack Win11 开始菜单工具","official":"https://www.startallback.com"},
    "easybcd": {"name":"EasyBCD","category":"系统工具","icon":"wrench","desc":"EasyBCD 引导管理工具","official":"https://neosmart.net/EasyBCD/"},
    "easyu": {"name":"EasyU","category":"系统工具","icon":"wrench","desc":"EasyU 装机维护工具","official":""},
    "iptoolbox": {"name":"IPToolBox","category":"系统工具","icon":"network","desc":"IP 工具箱","official":""},
    "clash": {"name":"Clash","category":"网络/代理","icon":"network","desc":"Clash 代理客户端","official":"https://github.com/Dreamacro/clash"},
    "clash.verge": {"name":"Clash Verge","category":"网络/代理","icon":"network","desc":"Clash Verge Rev 代理客户端","official":"https://github.com/clash-verge-rev/clash-verge-rev"},
    "bypass": {"name":"Bypass","category":"网络/代理","icon":"network","desc":"Bypass 旁路由工具","official":""},
    "rustdesk": {"name":"RustDesk","category":"远程控制","icon":"remote","desc":"RustDesk 远程桌面工具","official":"https://rustdesk.com"},
    "chrome": {"name":"Google Chrome","category":"浏览器","icon":"browser","desc":"Google Chrome 浏览器","official":"https://www.google.com/chrome/"},
    "firefox": {"name":"Firefox","category":"浏览器","icon":"browser","desc":"Mozilla Firefox 浏览器","official":"https://www.mozilla.org/firefox/"},
    "wallpaper engine": {"name":"Wallpaper Engine","category":"媒体/娱乐","icon":"media","desc":"Wallpaper Engine 动态壁纸","official":"https://www.wallpaperengine.io"},
    "potplayer": {"name":"PotPlayer","category":"媒体/娱乐","icon":"media","desc":"PotPlayer 视频播放器","official":"https://potplayer.daum.net"},
    "pot_bd": {"name":"PotPlayer","category":"媒体/娱乐","icon":"media","desc":"PotPlayer 视频播放器","official":"https://potplayer.daum.net"},
    "pixpin": {"name":"PixPin","category":"系统工具","icon":"screenshot","desc":"PixPin 截图工具","official":"https://pixpin.cn"},
    "heu": {"name":"HEU KMS Activator","category":"激活工具","icon":"key","desc":"HEU KMS 激活工具","official":"https://github.com/zbezj/HEU_KMS_Activator"},
    "lky_office": {"name":"LKY OfficeTools","category":"激活工具","icon":"key","desc":"LKY Office 一键安装激活","official":"https://github.com/OdysseusYuan/LKY_OfficeTools"},
    "asteriskpassword": {"name":"星号密码查看器","category":"系统工具","icon":"lock","desc":"AsteriskPassword 星号密码查看器","official":""},
    "virtio": {"name":"VirtIO 驱动","category":"驱动","icon":"driver","desc":"VirtIO Windows 驱动 (KVM/QEMU)","official":"https://fedoraproject.org/wiki/Windows_Virtio_Drivers"},
    "一盘走天下": {"name":"一盘走天下","category":"PE/维护","icon":"wrench","desc":"一盘走天下 PE 维护合集","official":""},
    "fuint": {"name":"Fuint 会员系统","category":"其他","icon":"box","desc":"Fuint 会员营销系统","official":"https://www.fuint.cn"},
    "公文排版": {"name":"公文排版工具","category":"办公软件","icon":"office","desc":"公文排版工具","official":""},
    "vm workstation": {"name":"VM Workstation (Linux)","category":"虚拟化","icon":"vmware","desc":"VMware Workstation for Linux","official":"https://www.vmware.com"},
}


# ============================================================
# SVG Icon System - replaces emoji with reliable SVG icons
# ============================================================

SVG_ICONS = {
    "vmware": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5M2 12l10 5 10-5"/></svg>',
    "server": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="3" width="20" height="6" rx="1"/><rect x="2" y="15" width="20" height="6" rx="1"/><line x1="6" y1="6" x2="6.01" y2="6"/><line x1="6" y1="18" x2="6.01" y2="18"/></svg>',
    "nas": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="4" width="18" height="16" rx="2"/><line x1="7" y1="8" x2="7" y2="8"/><line x1="7" y1="12" x2="7" y2="12"/><line x1="7" y1="16" x2="7" y2="16"/><line x1="11" y1="8" x2="17" y2="8"/><line x1="11" y1="12" x2="17" y2="12"/><line x1="11" y1="16" x2="17" y2="16"/></svg>',
    "windows": '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M3 5.5l8.5-1.2v8.2H3V5.5zm0 13l8.5 1.2v-8.2H3v7zm9.5 1.3L21 21V13h-8.5v6.8zm0-15.6V11H21V3l-8.5 1.2z"/></svg>',
    "linux": '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 2C9 2 8 4 8 6c0 1-1 2-1.5 3.5C6 11 6 12 7 13c.5.5 1 2 1 3 0 1.5-1 2-1 3 0 .5.5 1 1.5 1s2-1 3.5-1 2.5 1 3.5 1 1.5-.5 1.5-1c0-1-1-1.5-1-3 0-1 .5-2.5 1-3 1-1 1-2-.5-3.5C15 8 14 7 14 6c0-2-1-4-2-4z"/></svg>',
    "router": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="14" width="20" height="7" rx="1"/><line x1="6" y1="17.5" x2="6.01" y2="17.5"/><line x1="10" y1="17.5" x2="10.01" y2="17.5"/><path d="M12 14V8M8 8a4 4 0 018 0"/><path d="M16 8a4 4 0 018 0" opacity="0.4"/><path d="M4 8a4 4 0 018 0" opacity="0.4"/></svg>',
    "database": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5v6c0 1.7 4 3 9 3s9-1.3 9-3V5"/><path d="M3 11v6c0 1.7 4 3 9 3s9-1.3 9-3v-6"/></svg>',
    "office": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><line x1="3" y1="9" x2="21" y2="9"/><line x1="9" y1="21" x2="9" y2="9"/></svg>',
    "adobe": '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M3 3h5l4 8 4-8h5v18h-5v-8l-4 8-4-8v8H3z" opacity="0.9"/></svg>',
    "pdf": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><path d="M14 2v6h6"/><path d="M9 15h1.5a1.5 1.5 0 010 3H9v-3zm0 0v6"/></svg>',
    "code": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>',
    "java": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M8 18c-2 0-3-1-3-2 0-1 1-2 4-2v2c0 1 .5 2 1 2z"/><path d="M11 15c-4-1-5-3-5-5 0-2 3-3 6-3v2c-2 0-3 .5-3 1.5S10 12 13 13"/><path d="M14 12c4-1 5-3 5-5 0-2-3-3-6-3v2c2 0 3 .5 3 1.5S16 9 13 10"/><path d="M5 21h14"/><path d="M8 18v3M11 17v4M14 18v3M17 18v3"/></svg>',
    "python": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2c-3 0-5 1-5 3v2h5v1H5c-2 0-3 2-3 4s1 4 3 4h2v-2c0-2 2-3 4-3h3c2 0 3-1 3-3V5c0-2-2-3-5-3z"/><circle cx="9" cy="4.5" r="0.5" fill="currentColor"/></svg>',
    "terminal": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/></svg>',
    "disk": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="3"/></svg>',
    "archive": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="21 8 21 21 3 21 3 8"/><rect x="1" y="3" width="22" height="5"/><line x1="10" y1="12" x2="14" y2="12"/></svg>',
    "usb": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="4" r="2"/><path d="M12 6v6"/><path d="M9 12h6"/><path d="M12 12v8a2 2 0 002 2 2 2 0 002-2"/><path d="M9 8l-1 4h2"/><path d="M15 8l1 4h-2"/></svg>',
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
    "link": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10 13a5 5 0 007 0l3-3a5 5 0 00-7-7l-1 1"/><path d="M14 11a5 5 0 00-7 0l-3 3a5 5 0 007 7l1-1"/></svg>',
    "copy": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/></svg>',
    "refresh": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15"/></svg>',
    "folder": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z"/></svg>',
    "file": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M13 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V9z"/><polyline points="13 2 13 9 20 9"/></svg>',
    "search": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>',
    "package": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="16.5" y1="5.5" x2="7.5" y2="14.5"/><polygon points="21 8 21 21 3 21 3 8 12 1 21 8"/><polyline points="3 8 12 13 21 8"/></svg>',
}

CAT_ICON_MAP = {
    "操作系统":"windows","虚拟化":"vmware","NAS/存储":"nas","路由器/软路由":"router",
    "数据库":"database","开发工具":"code","系统工具":"wrench","网络/代理":"network",
    "浏览器":"browser","办公软件":"office","设计/创意":"adobe","媒体/娱乐":"media",
    "远程控制":"remote","激活工具":"key","PE/维护":"wrench","驱动":"driver","其他":"box",
}

def get_icon_svg(icon_name, size=26):
    svg = SVG_ICONS.get(icon_name, SVG_ICONS["box"])
    return f'<span class="svg-icon" style="width:{size}px;height:{size}px;display:inline-flex;align-items:center;justify-content:center">{svg}</span>'


def match_software(filename, dirpath):
    lower = (filename + " " + dirpath).lower()
    for key, info in SOFTWARE_DB.items():
        if key in lower:
            return info["name"], info["category"], info["icon"], info["desc"], info.get("official","")
    if "vm" in lower and "bios" in lower:
        return "VMware BIOS/EFI", "虚拟化", "vmware", "VMware BIOS/EFI 文件", ""
    if "tools" in lower and ("vmware" in lower or "vm" in lower):
        return "VMware Tools", "虚拟化", "vmware", "VMware Tools 驱动包", ""
    if "keygen" in lower or "注册" in lower:
        return "注册机/工具", "激活工具", "key", "注册/激活工具", ""
    if "补丁" in lower or "patch" in lower:
        return "补丁工具", "激活工具", "key", "软件补丁", ""
    if "virtualprinter" in lower:
        return "Virtual Printer", "虚拟化", "vmware", "VMware 虚拟打印机", ""
    if "darwin" in lower:
        return "VMware Tools (macOS)", "虚拟化", "vmware", "macOS VMware Tools", ""
    if "solaris" in lower:
        return "Solaris Tools", "虚拟化", "vmware", "Solaris VMware Tools", ""
    if "freebsd" in lower:
        return "FreeBSD Tools", "虚拟化", "linux", "FreeBSD VMware Tools", ""
    if "netware" in lower:
        return "NetWare Tools", "虚拟化", "box", "NetWare VMware Tools", ""
    if "winpre" in lower:
        return "Windows Tools (旧版)", "虚拟化", "windows", "旧版 Windows VMware Tools", ""
    if "tweaker" in lower:
        return "VM Tweaker", "虚拟化", "wrench", "VMware 调整工具", ""
    if "懒人" in lower or "去虚拟化" in lower:
        return "VMware 去虚拟化工具", "虚拟化", "wrench", "VMware 去虚拟化工具", ""
    if "adobe genp" in lower:
        return "Adobe GenP", "设计/创意", "adobe", "Adobe 通用补丁工具", ""
    if "enableloopback" in lower:
        return "EnableLoopback", "网络/代理", "network", "UWP 环回代理工具", ""
    if "sysproxy" in lower:
        return "sysproxy", "网络/代理", "network", "系统代理设置工具", ""
    if "tapinstall" in lower or ("tap" in lower and "install" in lower):
        return "TAP Driver", "网络/代理", "network", "TAP 网卡驱动安装", ""
    if "go-tun2socks" in lower:
        return "go-tun2socks", "网络/代理", "network", "TUN 转 SOCKS 工具", ""
    if "clash-core" in lower or "clash-win" in lower:
        return "Clash Core", "网络/代理", "network", "Clash 核心程序", ""
    if "unins" in lower:
        return "卸载程序", "系统工具", "trash", "软件卸载程序", ""
    if "dgfileviewer" in lower:
        return "DG FileViewer", "系统工具", "disk", "DiskGenius 文件查看器", ""
    if "offlinereg" in lower:
        return "OfflineReg", "系统工具", "wrench", "离线注册表编辑器", ""
    if "redis-desktop" in lower:
        return "Redis Desktop Manager", "数据库", "database", "Redis 可视化管理工具", "https://redisdesktop.com"
    if "tar.xz" in lower:
        return "压缩包", "其他", "archive", "压缩文件", ""
    if "vmdk" in lower:
        return "虚拟磁盘 (VMDK)", "虚拟化", "disk", "VMware 虚拟磁盘文件", ""
    if "ova" in lower or "ovf" in lower:
        return "虚拟设备 (OVF/OVA)", "虚拟化", "box", "虚拟机导入设备文件", ""
    if "wim" in lower:
        return "WIM 镜像", "操作系统", "windows", "Windows 映像文件", ""
    # Determine icon by extension
    ext = os.path.splitext(filename)[1].lower()
    ext_icons = {".exe":"box",".msi":"box",".iso":"disk",".img":"disk",".zip":"archive",".7z":"archive",".rar":"archive",".gz":"archive",".apk":"box",".dmg":"disk",".vmdk":"disk",".ova":"box",".ovf":"box",".wim":"disk"}
    icon_name = ext_icons.get(ext, "file")
    return os.path.splitext(filename)[0], "其他", icon_name, "软件文件", ""


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

    cat_icons = CAT_ICON_MAP

    json_data = json.dumps(items, ensure_ascii=False)
    total_size = sum(i["size"] for i in items)
    total_size_text = format_size(total_size)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Collect all SVG icon definitions
    all_icons = {}
    for icon_name in set(i["icon"] for i in items) | set(cat_icons.values()) | {"download","link","copy","refresh","search","package"}:
        all_icons[icon_name] = SVG_ICONS.get(icon_name, SVG_ICONS["box"])

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
.logo-icon {{ width:42px; height:42px; border-radius:10px; background:linear-gradient(135deg,var(--accent),#6b5cff); display:flex; align-items:center; justify-content:center; box-shadow:var(--shadow); }}
.logo-icon svg {{ width:22px; height:22px; color:#fff; }}
.logo-text h1 {{ font-size:18px; color:var(--text-bright); font-weight:700; display:flex; align-items:center; gap:8px; }}
.logo-text span {{ font-size:11px; color:var(--text-dim); }}
.search-box {{ flex:1; min-width:200px; position:relative; }}
.search-box input {{ width:100%; padding:10px 16px 10px 42px; background:var(--bg-search); border:1px solid var(--border); border-radius:10px; color:var(--text); font-size:14px; transition:all 0.2s; }}
.search-box input:focus {{ outline:none; border-color:var(--accent); box-shadow:0 0 0 3px var(--accent-glow); }}
.search-box .search-icon {{ position:absolute; left:14px; top:50%; transform:translateY(-50%); color:var(--text-dim); width:16px; height:16px; }}
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
.cat-chip svg {{ width:14px; height:14px; }}
.container {{ max-width:1400px; margin:0 auto; padding:24px; }}
.section {{ margin-bottom:32px; }}
.section-header {{ display:flex; align-items:center; gap:10px; margin-bottom:16px; padding-bottom:8px; border-bottom:1px solid var(--border); }}
.section-header h2 {{ font-size:17px; color:var(--text-bright); }}
.section-header .cat-icon {{ width:22px; height:22px; color:var(--accent); }}
.grid {{ display:grid; grid-template-columns:repeat(auto-fill, minmax(330px, 1fr)); gap:14px; }}
.card {{ background:var(--bg-card); border:1px solid var(--border); border-radius:var(--radius); padding:16px; transition:all 0.2s; display:flex; flex-direction:column; gap:10px; box-shadow:var(--shadow); }}
.card:hover {{ border-color:var(--border-bright); box-shadow:var(--shadow-lg); transform:translateY(-1px); }}
.card-top {{ display:flex; align-items:flex-start; gap:12px; }}
.card-icon {{ width:48px; height:48px; border-radius:10px; background:var(--bg-search); display:flex; align-items:center; justify-content:center; flex-shrink:0; color:var(--accent); }}
.card-icon svg {{ width:26px; height:26px; }}
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
.btn {{ display:inline-flex; align-items:center; justify-content:center; gap:4px; padding:6px 14px; border-radius:8px; font-size:12px; font-weight:500; cursor:pointer; text-decoration:none; transition:all 0.15s; border:none; }}
.btn svg {{ width:14px; height:14px; }}
.btn-download {{ background:var(--accent); color:#fff; flex:1; }}
.btn-download:hover {{ background:#3a6aff; }}
.btn-official {{ background:transparent; border:1px solid var(--border-bright); color:var(--text-dim); padding:6px 12px; }}
.btn-official:hover {{ border-color:var(--accent); color:var(--accent); }}
.btn-copy {{ background:transparent; border:1px solid var(--border-bright); color:var(--text-dim); padding:6px 10px; }}
.btn-copy:hover {{ border-color:var(--green); color:var(--green); }}
.card-path {{ font-size:11px; color:var(--text-dim); opacity:0.6; font-family:'Cascadia Code','Consolas',monospace; word-break:break-all; cursor:pointer; transition:opacity 0.15s; }}
.card-path:hover {{ opacity:1; }}
.no-results {{ text-align:center; padding:60px 20px; color:var(--text-dim); }}
.no-results .icon {{ font-size:48px; margin-bottom:16px; }}
.footer {{ text-align:center; padding:24px; color:var(--text-dim); font-size:12px; border-top:1px solid var(--border); margin-top:40px; }}
.toolbar {{ max-width:1400px; margin:0 auto; padding:0 24px; display:flex; justify-content:flex-end; gap:8px; margin-bottom:12px; }}
.btn-rescan {{ display:inline-flex; align-items:center; gap:5px; padding:6px 16px; border-radius:8px; font-size:12px; font-weight:500; cursor:pointer; background:var(--bg-card); border:1px solid var(--border-bright); color:var(--text-dim); transition:all 0.15s; }}
.btn-rescan:hover {{ border-color:var(--accent); color:var(--accent); }}
.btn-rescan svg {{ width:14px; height:14px; }}
.btn-rescan.scanning {{ pointer-events:none; opacity:0.6; }}
.btn-rescan.scanning svg {{ animation:spin 1s linear infinite; }}
@keyframes spin {{ from {{ transform:rotate(0deg); }} to {{ transform:rotate(360deg); }} }}
@media (max-width:768px) {{ .header-inner {{ flex-direction:column; align-items:stretch; }} .stats {{ justify-content:center; }} .grid {{ grid-template-columns:1fr; }} .cat-bar {{ top:120px; }} }}
::-webkit-scrollbar {{ width:8px; height:8px; }}
::-webkit-scrollbar-track {{ background:transparent; }}
::-webkit-scrollbar-thumb {{ background:var(--border-bright); border-radius:4px; }}
::-webkit-scrollbar-thumb:hover {{ background:#a8acb8; }}
@keyframes fadeIn {{ from {{ opacity:0; transform:translateY(8px); }} to {{ opacity:1; transform:translateY(0); }} }}
.card {{ animation:fadeIn 0.3s ease-out; }}
.scan-badge {{ display:inline-flex; align-items:center; gap:4px; font-size:11px; color:var(--text-dim); }}
.scan-badge .dot {{ width:8px; height:8px; border-radius:50%; background:var(--green); display:inline-block; animation:pulse 2s infinite; }}
@keyframes pulse {{ 0%,100% {{ opacity:1; }} 50% {{ opacity:0.4; }} }}
</style>
</head>
<body>
<div class="header"><div class="header-inner">
  <div class="logo"><div class="logo-icon">{SVG_ICONS["package"]}</div><div class="logo-text"><h1>软件库 <span class="scan-badge"><span class="dot"></span> Live</span></h1><span>Software Library</span></div></div>
  <div class="search-box"><span class="search-icon">{SVG_ICONS["search"]}</span><input type="text" id="searchInput" placeholder="搜索软件名、版本、类型..." autocomplete="off"></div>
  <div class="stats"><div class="stat-item"><div class="num" id="statCount">{len(items)}</div><div class="label">文件</div></div><div class="stat-item"><div class="num">{len(categories)}</div><div class="label">分类</div></div><div class="stat-item"><div class="num">{total_size_text}</div><div class="label">总量</div></div></div>
</div></div>
<div class="cat-bar"><div class="cat-bar-inner" id="catBar"><div class="cat-chip active" data-cat="all">{SVG_ICONS["package"]} 全部 <span class="count">({len(items)})</span></div></div></div>
<div class="toolbar"><button class="btn-rescan" id="rescanBtn" onclick="doRescan()">{SVG_ICONS["refresh"]} 重新扫描</button></div>
<div class="container" id="container"></div>
<div class="footer"><p>软件库自动扫描生成 · 共 {len(items)} 个文件 · 总计 {total_size_text}</p><p style="margin-top:4px;">最后更新: {now_str}</p></div>
<script>
const ICONS = {json.dumps(all_icons, ensure_ascii=False)};
const ALL_DATA = {json_data};
const CAT_ICONS = {json.dumps(cat_icons, ensure_ascii=False)};
function iconSVG(name, size) {{
  const svg = ICONS[name] || ICONS['box'];
  return '<span class="svg-icon" style="width:' + (size||26) + 'px;height:' + (size||26) + 'px;display:inline-flex;align-items:center;justify-content:center">' + svg + '</span>';
}}
const categories = [...new Set(ALL_DATA.map(i => i.category))];
const catBar = document.getElementById('catBar');
categories.forEach(cat => {{ const count = ALL_DATA.filter(i => i.category === cat).length; const iconName = CAT_ICONS[cat] || 'box'; const chip = document.createElement('div'); chip.className = 'cat-chip'; chip.dataset.cat = cat; chip.innerHTML = iconSVG(iconName, 14) + ' ' + cat + ' <span class="count">(' + count + ')</span>'; chip.onclick = () => selectCategory(cat); catBar.appendChild(chip); }});
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
  if (filtered.length === 0) {{ container.innerHTML = '<div class="no-results"><div style="font-size:48px;margin-bottom:16px;">' + iconSVG('search', 48) + '</div><p>没有找到匹配的文件</p></div>'; return; }}
  const grouped = {{}};
  filtered.forEach(i => {{ if (!grouped[i.category]) grouped[i.category] = []; grouped[i.category].push(i); }});
  let html = '';
  for (const cat of Object.keys(grouped).sort()) {{
    const items = grouped[cat]; const iconName = CAT_ICONS[cat] || 'box';
    html += '<div class="section"><div class="section-header">' + iconSVG(iconName, 22) + '<h2>' + cat + ' (' + items.length + ')</h2></div><div class="grid">';
    for (const item of items) {{
      const dlUrl = '/download/' + encodeURIComponent(item.path);
      const enc = encodePath(item.path);
      html += '<div class="card"><div class="card-top"><div class="card-icon">' + iconSVG(item.icon, 26) + '</div><div class="card-info"><div class="card-title">' + escapeHtml(item.name);
      if (item.version) html += '<span class="card-version">v' + escapeHtml(item.version) + '</span>';
      html += '</div><div class="card-desc">' + escapeHtml(item.desc) + '</div></div></div><div class="card-meta">';
      html += '<span class="meta-tag type">' + item.fileType + '</span><span class="meta-tag size">' + item.sizeText + '</span>';
      if (item.date) html += '<span class="meta-tag date">📅 ' + item.date + '</span>';
      html += '</div>';
      html += '<div class="card-path" title="点击复制路径" onclick="copyPath(\\'' + enc + '\\')">' + escapeHtml(item.relativeDir || '/') + '</div>';
      html += '<div class="card-actions"><a class="btn btn-download" href="' + dlUrl + '" download="' + escapeHtml(item.filename) + '">' + ICON_SVG_DOWNLOAD + ' 下载</a>';
      if (item.official) html += '<a class="btn btn-official" href="' + item.official + '" target="_blank">' + ICON_SVG_LINK + ' 官网</a>';
      html += '<button class="btn btn-copy" onclick="copyPath(\\'' + enc + '\\')">' + ICON_SVG_COPY + ' 路径</button></div></div>';
    }}
    html += '</div></div>';
  }}
  container.innerHTML = html;
}}
const ICON_SVG_DOWNLOAD = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:14px;height:14px"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>';
const ICON_SVG_LINK = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:14px;height:14px"><path d="M10 13a5 5 0 007 0l3-3a5 5 0 00-7-7l-1 1"/><path d="M14 11a5 5 0 00-7 0l-3 3a5 5 0 007 7l1-1"/></svg>';
const ICON_SVG_COPY = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:14px;height:14px"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/></svg>';
function copyPath(encoded) {{
  const path = decodeURIComponent(escape(atob(encoded)));
  navigator.clipboard.writeText(path).then(() => showToast('路径已复制: ' + path)).catch(() => {{ const ta = document.createElement('textarea'); ta.value = path; document.body.appendChild(ta); ta.select(); try {{ document.execCommand('copy'); showToast('路径已复制'); }} catch(e) {{ showToast('复制失败'); }} document.body.removeChild(ta); }});
}}
function showToast(msg) {{
  let toast = document.getElementById('toast');
  if (!toast) {{ toast = document.createElement('div'); toast.id = 'toast'; toast.style.cssText = 'position:fixed;bottom:30px;left:50%;transform:translateX(-50%);background:#1a1d28;color:#fff;padding:10px 24px;border-radius:8px;font-size:13px;z-index:9999;opacity:0;transition:opacity 0.3s;box-shadow:0 4px 12px rgba(0,0,0,0.2);'; document.body.appendChild(toast); }}
  toast.textContent = msg; toast.style.opacity = '1'; clearTimeout(toast._timer); toast._timer = setTimeout(() => {{ toast.style.opacity = '0'; }}, 2500);
}}
async function doRescan() {{
  const btn = document.getElementById('rescanBtn');
  btn.classList.add('scanning');
  btn.innerHTML = ICONS['refresh'] + ' 扫描中...';
  try {{
    const resp = await fetch('/api/rescan', {{ method: 'POST' }});
    const data = await resp.json();
    if (data.success) {{
      showToast('扫描完成: ' + data.totalFiles + ' 个文件');
      setTimeout(() => location.reload(), 1000);
    }} else {{
      showToast('扫描失败: ' + (data.error || '未知错误'));
      btn.classList.remove('scanning');
      btn.innerHTML = ICONS['refresh'] + ' 重新扫描';
    }}
  }} catch(e) {{
    showToast('请求失败: ' + e.message);
    btn.classList.remove('scanning');
    btn.innerHTML = ICONS['refresh'] + ' 重新扫描';
  }}
}}
render();
</script>
</body>
</html>"""
    return html


# ============================================================
# Custom HTTP Handler - serves index.html from /app/data and
# files from ROOT_DIR via /download/<path> endpoint
# ============================================================

class SoftwareHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DATA_DIR, **kwargs)

    def do_GET(self):
        # Parse URL
        parsed = urllib.parse.urlparse(self.path)
        path = urllib.parse.unquote(parsed.path)

        # Serve index.html at root
        if path == '/' or path == '/index.html':
            self._serve_file(HTML_FILE, 'text/html')
            return

        # Download endpoint: /download/<relative_path>
        if path.startswith('/download/'):
            rel_path = path[len('/download/'):]
            # Prevent directory traversal
            safe_path = os.path.normpath(os.path.join(ROOT_DIR, rel_path))
            if not safe_path.startswith(os.path.normpath(ROOT_DIR)):
                self.send_error(403, "Forbidden")
                return
            if os.path.isfile(safe_path):
                self._serve_download(safe_path)
            else:
                self.send_error(404, "File not found")
            return

        # API endpoint: rescan
        if path == '/api/scan-status':
            self._serve_json({"scanning": _scan_in_progress, "lastScan": _last_scan_time})
            return

        # Fallback: serve from DATA_DIR (for JSON file etc)
        super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = urllib.parse.unquote(parsed.path)

        if path == '/api/rescan':
            self._handle_rescan()
            return

        self.send_error(404, "Not found")

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
        except Exception as e:
            self.send_error(500, str(e))

    def _serve_download(self, filepath):
        try:
            filesize = os.path.getsize(filepath)
            filename = os.path.basename(filepath)
            # URL-encode filename for Content-Disposition header
            quoted_filename = urllib.parse.quote(filename)
            self.send_response(200)
            self.send_header('Content-Type', 'application/octet-stream')
            self.send_header('Content-Length', str(filesize))
            self.send_header('Content-Disposition', f"attachment; filename*=UTF-8''{quoted_filename}")
            self.send_header('Access-Control-Allow-Origin', '*')
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

    def _handle_rescan(self):
        global _scan_in_progress, _last_scan_time
        if _scan_in_progress:
            self._serve_json({"success": False, "error": "扫描正在进行中"})
            return
        # Run scan in background thread
        def do_scan():
            global _scan_in_progress, _last_scan_time
            _scan_in_progress = True
            try:
                run_scan()
                _last_scan_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            except Exception as e:
                print(f"Rescan error: {e}")
            finally:
                _scan_in_progress = False
        t = threading.Thread(target=do_scan, daemon=True)
        t.start()
        self._serve_json({"success": True, "message": "扫描已启动"})

    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        super().end_headers()

    def log_message(self, format, *args):
        log_msg = f"[{self.log_date_time_string()}] {format % args}"
        try:
            os.makedirs(LOG_DIR, exist_ok=True)
            with open(os.path.join(LOG_DIR, "server.log"), "a", encoding="utf-8") as f:
                f.write(log_msg + "\n")
        except Exception:
            pass


# Global scan state
_scan_in_progress = False
_last_scan_time = ""


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
