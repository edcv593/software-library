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
    if changes.get('recommended') and any(overrides.get(p,{}).get('reviewState') in ('pending','rejected') for p in paths):
        raise ValueError('待审核或已拒绝的版本不能直接推荐，请先批准发布')
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

def review(config, scan_items, data):
    paths=data.get('paths')
    if not isinstance(paths,list) or len(paths)!=1 or not isinstance(paths[0],str):
        raise ValueError('每次请选择一个版本')
    known={item['path']:item for item in scan_items}
    path=paths[0]
    if path not in known:raise ValueError('版本文件已变化，请刷新')
    overrides=config.setdefault('versions',{})
    cfg=overrides.setdefault(path,{})
    action=data.get('action')
    state=cfg.get('reviewState','')
    if action=='reopen':
        if state!='rejected':raise ValueError('只能重新审核已拒绝的版本')
        cfg.update(reviewState='pending',recommended=False,channel='stable')
        return
    if action in ('approve','reject') and state!='pending':
        raise ValueError('此版本已不在待审核状态，请刷新')
    if action=='rollback' and (state in ('pending','rejected') or cfg.get('channel')!='archive'):
        raise ValueError('只能回退到已发布的历史版本')
    if action=='reject':
        cfg.update(reviewState='rejected',recommended=False,channel='archive')
        return
    if action not in ('approve','rollback'):raise ValueError('审核操作无效')
    target=cfg.get('software',known[path]['name'])
    for other,item in known.items():
        settings=overrides.get(other,{})
        if other!=path and settings.get('software',item['name'])==target and settings.get('reviewState') not in ('pending','rejected'):
            overrides.setdefault(other,{}).update(recommended=False,channel='archive')
    cfg.update(reviewState='approved',recommended=True,channel='stable')
