"""Persistent virtual categories and software metadata; never moves source files."""
import hashlib
import uuid


def categories(config, software):
    if "categories" not in config:
        names = sorted({s.get("category", "其他") for s in software})
        config["categories"] = [
            {"id": "legacy-" + hashlib.sha256(n.encode()).hexdigest()[:16],
             "name": n, "parentId": ""} for n in names]
    return config["categories"]


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
