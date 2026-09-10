"""Explicit official update sources: latest direct URLs or GitHub release assets."""
import fnmatch
import json
import re
import urllib.parse
import urllib.request
from catalog import text


def settings(data):
    if not isinstance(data,dict):
        raise ValueError('更新设置格式不正确')
    kind=data.get('kind','direct')
    if kind not in ('direct','github'):
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
    if result['auto'] and not result['repo' if kind=='github' else 'url']:
        raise ValueError('启用自动更新前请填写更新源')
    return result


def resolve(source):
    if source['kind']=='direct':
        return {'url':source['url'],'filename':source.get('filename','')}
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
