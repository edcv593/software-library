"""Version annotations and logical grouping keyed by the original file path."""
from catalog import text


def manage(config, scan_items, data):
    if not isinstance(data, dict):
        raise ValueError('版本请求格式不正确')
    paths = data.get('paths')
    known = {s['path']:s for s in scan_items}
    if not isinstance(paths, list) or not paths or any(not isinstance(p,str) or p not in known for p in paths):
        raise ValueError('请选择存在的版本文件')
    changes = {}
    if 'software' in data:
        changes['software'] = text(data['software'], '软件名称', 200)
        if not changes['software']:
            raise ValueError('软件名称不能为空')
    for key, label, limit in [('version','版本号',80),('platform','适用系统',80),('arch','架构',80),('notes','更新说明',5000)]:
        if key in data:
            changes[key] = text(data[key],label,limit)
    if 'channel' in data:
        if data['channel'] not in ('stable','beta','archive'):
            raise ValueError('版本渠道无效')
        changes['channel'] = data['channel']
    if 'recommended' in data:
        if not isinstance(data['recommended'],bool) or (data['recommended'] and len(paths)!=1):
            raise ValueError('每次只能推荐一个版本')
        changes['recommended'] = data['recommended']
    if not changes:
        raise ValueError('未指定版本修改内容')
    overrides = config.setdefault('versions',{})
    # Moving versions clears their recommendation to avoid two recommended files in the target.
    if 'software' in changes and 'recommended' not in changes:
        changes['recommended'] = False
    for path in paths:
        overrides.setdefault(path,{}).update(changes)
    if changes.get('recommended'):
        selected = paths[0]
        target = overrides[selected].get('software',known[selected]['name'])
        for path,cfg in overrides.items():
            if path!=selected and path in known and cfg.get('software',known[path]['name'])==target:
                cfg['recommended'] = False
