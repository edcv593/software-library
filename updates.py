"""Explicit update sources and supported UU/fnOS public download-page adapters."""
import fnmatch
import json
import re
import urllib.parse
import urllib.request
import hashlib
import secrets
import time
from catalog import text


def settings(data):
    if not isinstance(data,dict):
        raise ValueError('更新设置格式不正确')
    kind=data.get('kind','direct')
    if kind not in ('direct','github','uu','fnos'):
        raise ValueError('更新源类型无效')
    result={'kind':kind}
    for key in ('url','repo','assetPattern','filename'):
        result[key]=text(data.get(key,''),key,4096 if key=='url' else 200)
    if not isinstance(data.get('auto',False),bool):
        raise ValueError('自动更新设置无效')
    result['auto']=data.get('auto',False)
    hours=data.get('intervalHours',24)
    if isinstance(hours,bool) or not isinstance(hours,int) or hours<1 or hours>720:
        raise ValueError('检查间隔必须为 1 至 720 小时')
    result['intervalHours']=hours
    if kind=='github' and result['repo'] and not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*',result['repo']):
        raise ValueError('GitHub 仓库格式为 owner/repo')
    if kind=='direct' and result['url']:
        parsed=urllib.parse.urlparse(result['url'])
        if parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError('更新直链必须为不含账号密码的 HTTP/HTTPS 地址')
    if result['auto'] and kind in ('direct','github') and not result['repo' if kind=='github' else 'url']:
        raise ValueError('启用自动更新前请填写更新源')
    return result


UU_PAGE = 'https://adl.netease.com/d/g/uuremote/c/gw?type=pc'
FNOS_PAGE = 'https://fnnas.com/download'


def source_url(source):
    if source['kind']=='uu': return UU_PAGE
    if source['kind']=='fnos': return FNOS_PAGE
    if source['kind']=='direct': return source['url']
    return 'https://api.github.com/repos/'+source['repo']+'/releases/latest'


def _read_official(url, data=None, headers=None):
    request=urllib.request.Request(url,data=data,headers={
        'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) SoftwareLibrary/10',
        **(headers or {})})
    with urllib.request.urlopen(request,timeout=20) as response:
        raw=response.read(2*1024*1024+1)
    if len(raw)>2*1024*1024:
        raise ValueError('官网下载页面超过解析大小限制')
    return raw.decode('utf-8')


def _fnos_signed_url(url):
    # This is the public website client's request-signing protocol, not a user credential.
    # Request a fresh CDN URL through the same endpoint used by the official download button.
    body=json.dumps({'url':url},ensure_ascii=False,separators=(',',':'))
    nonce=str(secrets.randbelow(900000)+100000)
    timestamp=str(int(time.time()*1000))
    md5=lambda value:hashlib.md5(value.encode('utf-8')).hexdigest()
    signature=md5('_'.join(['NDzZTVxnRKP8Z0jXg1VAMonaG8akvh','/asset/download-sign',
                           nonce,timestamp,md5(body),'4fac7e99-ef43-4b6c-9ca8-5bbca4a4210e']))
    result=json.loads(_read_official('https://fnnas.com/asset/download-sign',body.encode('utf-8'),{
        'Content-Type':'application/json','Referer':FNOS_PAGE,
        'authx':f'nonce={nonce}&timestamp={timestamp}&sign={signature}'}))
    signed=result.get('url','')
    original=urllib.parse.urlparse(url)
    parsed=urllib.parse.urlparse(signed)
    if parsed.scheme!='https' or parsed.netloc!='iso.liveupdate.fnnas.com' or parsed.path!=original.path:
        raise ValueError('飞牛官网没有返回有效的镜像签名地址，可能需要更新解析适配')
    return signed


def prepare_download(url):
    """Resolve only supported official providers; never execute arbitrary page JavaScript."""
    parsed=urllib.parse.urlparse(url)
    if parsed.hostname=='adl.netease.com' and parsed.path.rstrip('/')=='/d/g/uuremote/c/gw':
        kind=urllib.parse.parse_qs(parsed.query).get('type',['pc'])
        if kind!=['pc']:
            raise ValueError('UU 远程适配目前支持 Windows PC 地址，请使用 type=pc')
        page=_read_official(url)
        match=re.search(r'\bvar\s+pc_link\s*=\s*("(?:[^"\\]|\\.)*"|\'[^\']*\')\s*;',page)
        if not match:
            raise ValueError('UU 官网下载入口已变化，未找到 Windows 安装包地址')
        value=match.group(1)
        target=json.loads(value) if value.startswith('"') else value[1:-1]
        dest=urllib.parse.urlparse(target)
        if dest.scheme!='https' or dest.netloc!='api.nrd.nie.163.com' or not dest.path.startswith('/api/v1/release/dl/'):
            raise ValueError('UU 官网返回的下载接口不在受支持范围内')
        return {'url':target,'provider':'uu'}
    if parsed.hostname in ('fnnas.com','www.fnnas.com') and parsed.path.rstrip('/')=='/download':
        page=_read_official(FNOS_PAGE)
        urls=set(re.findall(r'https://iso\.liveupdate\.fnnas\.com/x86_64/trim/[^"\\\s<>]+\.iso',page))
        if len(urls)!=1:
            raise ValueError('飞牛官网未提供唯一的 x86 ISO 地址，请检查官网或更新解析适配')
        url=urls.pop()
        parsed=urllib.parse.urlparse(url)
    if parsed.hostname=='iso.liveupdate.fnnas.com' and parsed.path.lower().endswith('.iso'):
        clean=urllib.parse.urlunparse(('https','iso.liveupdate.fnnas.com',parsed.path,'','',''))
        signed=_fnos_signed_url(clean)
        version=re.search(r'_x86_([^_/]+)_\d+\.iso$',parsed.path)
        return {'url':signed,'provider':'fnos','releaseVersion':version.group(1) if version else ''}
    return {'url':url}


def resolve(source):
    if source['kind']!='github':
        return {'url':source_url(source),'filename':source.get('filename','') if source['kind']=='direct' else ''}
    url='https://api.github.com/repos/'+source['repo']+'/releases/latest'
    req=urllib.request.Request(url,headers={'User-Agent':'SoftwareLibrary/10','Accept':'application/vnd.github+json'})
    with urllib.request.urlopen(req,timeout=20) as response:
        raw=response.read(2*1024*1024+1)
        if len(raw)>2*1024*1024:
            raise ValueError('GitHub 发布信息过大')
        release=json.loads(raw)
    pattern=source.get('assetPattern') or '*'
    assets=[a for a in release.get('assets',[]) if fnmatch.fnmatchcase(a['name'],pattern)]
    if len(assets)!=1:
        raise ValueError(f'更新文件规则匹配到 {len(assets)} 个文件，请设置唯一匹配的文件名规则（例如 *windows*x64*.exe）')
    asset=assets[0]
    return {'url':asset['browser_download_url'],'filename':asset['name'],
            'releaseVersion':str(release.get('tag_name',''))[:80],
            'releaseNotes':str(release.get('body') or '')[:5000],
            'expectedSha':(asset.get('digest') or '').removeprefix('sha256:') if (asset.get('digest') or '').startswith('sha256:') else ''}
