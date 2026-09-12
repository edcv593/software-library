"""Conservative duplicate suggestions and administrator-confirmed logical merging."""
import re
import unicodedata
import versions

def key(name):
    name=unicodedata.normalize('NFKC', name).casefold().strip()
    name=re.sub(r'\.(exe|msi|zip|7z|iso|dmg|apk)$','',name)
    name=re.sub(r'[ _-]+(?:v?\d+(?:\.\d+){1,}(?:[ _-]+(?:x64|x86|arm64|win64|win32))?)$','',name)
    return re.sub(r'[\s_-]+',' ',name).strip()

def suggestions(software):
    groups={}
    for sw in software:
        normalized=key(sw.get('displayName') or sw['name'])
        if len(normalized)>=3 and sw['versions']:
            groups.setdefault(normalized,[]).append(sw)
    return [{'key':k,'names':[s['name'] for s in items], 'files':sum(len(s['versions']) for s in items)} for k,items in groups.items() if len(items)>1]

def merge(config, scan, software, data):
    names=data.get('names');target=data.get('target')
    if not isinstance(names,list) or len(names)<2 or any(not isinstance(n,str) for n in names) or len(set(names))!=len(names):
        raise ValueError('请至少选择两个不同的软件')
    known={s['name']:s for s in software}
    if any(n not in known for n in names) or target not in names:
        raise ValueError('软件列表已变化，请刷新后重新选择')
    if any(not known[n]['versions'] for n in names):
        raise ValueError('只支持合并包含本地版本的软件')
    paths=[v['path'] for n in names if n!=target for v in known[n]['versions']]
    expected=data.get('paths')
    if not isinstance(expected,list) or set(expected)!=set(paths):
        raise ValueError('版本列表已变化，请重新确认合并')
    versions.manage(config,scan,{'paths':paths,'software':target})
    for name in names:
        if name!=target:
            config.setdefault('software',{}).setdefault(name,{})['mergedInto']=target
    return len(paths)
