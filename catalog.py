"""Persistent virtual categories and software metadata; never moves source files."""
import hashlib
import uuid


def export_data(config, software, app_version, created):
    """Export library metadata only; exclude unrelated site and account settings."""
    software_keys = {'category', 'categoryId', 'icon', 'desc', 'official', 'showOfficial',
                     'customOfficial', 'downloadUrl', 'displayName', 'notes', 'tags',
                     'customFields', 'updateSource', 'mergedInto'}
    version_keys = {'software', 'version', 'platform', 'arch', 'channel', 'notes',
                    'recommended', 'reviewState', 'sha256', 'cloudUrl', 'cloudCode'}
    def select(mapping, keys):
        return {name: {k: v for k, v in settings.items() if k in keys}
                for name, settings in mapping.items() if isinstance(settings, dict)}
    return {
        'format': 'software-library-catalog', 'schemaVersion': 1,
        'appVersion': app_version, 'createdAt': created,
        'catalog': {'categories': categories(config, software),
                    'software': select(config.get('software', {}), software_keys),
                    'versions': select(config.get('versions', {}), version_keys),
                    'order': config.get('order', [])},
        'inventory': software,
        'counts': {'categories': len(config['categories']), 'software': len(software),
                   'files': sum(len(s.get('versions', [])) for s in software)},
    }


def categories(config, software):
    if "categories" not in config:
        names = sorted({s.get("category", "其他") for s in software})
        config["categories"] = [
            {"id": "legacy-" + hashlib.sha256(n.encode()).hexdigest()[:16],
             "name": n, "parentId": ""} for n in names]
    return config["categories"]


def compare_export(backup, current):
    """Read-only structural validation and comparison, never applies imported data."""
    if not isinstance(backup, dict) or backup.get('format') != 'software-library-catalog':
        raise ValueError('不是软件库资料备份文件')
    if type(backup.get('schemaVersion')) is not int or backup['schemaVersion'] != 1:
        raise ValueError('暂不支持此备份格式版本')
    saved = backup.get('catalog')
    if not isinstance(saved, dict) or not isinstance(saved.get('categories'), list):
        raise ValueError('备份缺少有效分类资料')
    if len(saved['categories']) > 5000: raise ValueError('备份分类数量过多')
    nodes = {}
    for node in saved['categories']:
        if not isinstance(node, dict): raise ValueError('分类格式无效')
        for key in ('id', 'name', 'parentId'):
            if not isinstance(node.get(key), str) or len(node[key]) > 200: raise ValueError('分类字段无效')
        if not node['id'] or not node['name'] or node['id'] in nodes: raise ValueError('分类标识为空或重复')
        nodes[node['id']] = node
    checked = set()
    for node_id in nodes:
        chain = set()
        while node_id and node_id not in checked:
            if node_id in chain or node_id not in nodes: raise ValueError('分类存在循环或缺失的上级')
            chain.add(node_id); node_id = nodes[node_id]['parentId']
        checked.update(chain)
    for key in ('software', 'versions'):
        values = saved.get(key)
        if not isinstance(values, dict) or len(values) > 50000: raise ValueError('备份资料格式或数量无效')
        if any(not isinstance(k, str) or not k or len(k)>4096 or not isinstance(v, dict) for k,v in values.items()):
            raise ValueError('软件或版本设置格式无效')
    inventory = backup.get('inventory')
    if not isinstance(inventory, list) or len(inventory)>20000: raise ValueError('备份文件清单无效')
    names, paths = set(), {}
    for sw in inventory:
        if not isinstance(sw, dict) or not isinstance(sw.get('name'), str) or not sw['name'] or len(sw['name'])>4096 or sw['name'] in names:
            raise ValueError('软件清单名称无效或重复')
        names.add(sw['name'])
        if not isinstance(sw.get('versions'), list): raise ValueError('版本清单无效')
        for version in sw['versions']:
            if not isinstance(version, dict) or not isinstance(version.get('path'), str) or not version['path'] or len(version['path'])>4096:
                raise ValueError('版本路径无效')
            if version['path'] in paths: raise ValueError('备份含重复版本路径')
            if type(version.get('size')) is not int or version['size']<0: raise ValueError('版本文件大小无效')
            paths[version['path']] = version.get('size')
            if len(paths)>50000: raise ValueError('备份文件数量过多')
    def diff(old, new):
        groups = {'backupOnly':sorted(set(old)-set(new)), 'currentOnly':sorted(set(new)-set(old)),
                  'changed':sorted(k for k in set(old)&set(new) if old[k]!=new[k])}
        return {key:{'count':len(items), 'items':items[:100]} for key,items in groups.items()}
    live = current['catalog']
    live_paths = {v['path']:v.get('size') for s in current['inventory'] for v in s['versions']}
    return {'createdAt':str(backup.get('createdAt',''))[:80], 'appVersion':str(backup.get('appVersion',''))[:80],
            'counts':{'categories':len(nodes),'software':len(names),'files':len(paths)},
            'currentCounts':current['counts'],
            'categories':diff(nodes,{n['id']:n for n in live['categories']}),
            'software':diff(saved['software'],live['software']),
            'versions':diff(saved['versions'],live['versions']),
            'files':diff(paths,live_paths)}


def text(value, label, limit=200):
    if not isinstance(value, str) or len(value) > limit:
        raise ValueError(label + "格式不正确或过长")
    return value.strip()


def descendants(nodes, node_id):
    result = {node_id}
    while True:
        added = {n["id"] for n in nodes if n["parentId"] in result} - result
        if not added:
            return result
        result.update(added)


def mutate(config, software, data):
    if not isinstance(data, dict):
        raise ValueError("请求必须为对象")
    nodes = categories(config, software)
    by_id = {n["id"]: n for n in nodes}
    action = data.get("action")
    node_id = text(data.get("id", ""), "分类标识")
    if action in ("create", "update"):
        name = text(data.get("name"), "分类名称", 80)
        parent = text(data.get("parentId", ""), "父分类")
        if not name:
            raise ValueError("分类名称不能为空")
        if parent and parent not in by_id:
            raise ValueError("父分类不存在")
        if action == "update" and node_id not in by_id:
            raise ValueError("分类不存在")
        if action == "update" and parent in descendants(nodes, node_id):
            raise ValueError("不能将分类放入自身或子分类")
        if any(n["name"] == name and n["parentId"] == parent and n["id"] != node_id for n in nodes):
            raise ValueError("同级分类名称不能重复")
        if action == "create":
            nodes.append({"id": uuid.uuid4().hex, "name": name, "parentId": parent})
        else:
            by_id[node_id].update(name=name, parentId=parent)
    elif action == "delete":
        if node_id not in by_id:
            raise ValueError("分类不存在")
        removed = descendants(nodes, node_id)
        target = text(data.get("targetId", ""), "目标分类")
        if target in removed or (target and target not in by_id):
            raise ValueError("请选择被删除分支以外的目标分类")
        for sw in software:
            if sw.get("categoryId") in removed:
                config.setdefault("software", {}).setdefault(sw["name"], {})["categoryId"] = target
        config["categories"] = [n for n in nodes if n["id"] not in removed]
    elif action in ("move", "metadata"):
        names = data.get("names")
        known = {s["name"] for s in software}
        if not isinstance(names, list) or not names or any(not isinstance(n, str) or n not in known for n in names):
            raise ValueError("请选择有效的软件")
        changes = {}
        if "categoryId" in data:
            target = text(data["categoryId"], "目标分类")
            if target and target not in by_id:
                raise ValueError("目标分类不存在")
            changes["categoryId"] = target
        elif action == "move":
            raise ValueError("缺少目标分类")
        if action == "metadata":
            for key in ("displayName", "desc", "notes"):
                if key in data:
                    changes[key] = text(data[key], key, 5000 if key != "displayName" else 200)
            tags = data.get("tags", [])
            if not isinstance(tags, list) or len(tags) > 30:
                raise ValueError("最多设置 30 个标签")
            changes["tags"] = list(dict.fromkeys(text(t, "标签", 60) for t in tags if t))
            fields = data.get("customFields", {})
            if not isinstance(fields, dict) or len(fields) > 30:
                raise ValueError("最多设置 30 个自定义字段")
            changes["customFields"] = {text(k, "字段名", 80): text(v, "字段内容", 2000) for k, v in fields.items()}
            if "" in changes["customFields"]:
                raise ValueError("字段名不能为空")
        for name in names:
            config.setdefault("software", {}).setdefault(name, {}).update(changes)
    else:
        raise ValueError("不支持的操作")
    return config
