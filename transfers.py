"""Bounded-memory uploads and a persistent, sequential download queue."""
import email.policy
from email.parser import BytesParser
from email.message import Message
import hashlib
import json
import os
import re
import threading
import time
import urllib.parse
import urllib.request
import uuid
import updates


def safe_filename(name, extensions):
    if not isinstance(name, str):
        raise ValueError('文件名无效')
    name = os.path.basename(name.replace('\\', '/')).strip().rstrip('.')
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name)
    if not name or name.startswith('.') or len(name.encode('utf-8')) > 220:
        raise ValueError('文件名为空、过长或以点开头')
    if not any(name.lower().endswith(ext) for ext in extensions):
        raise ValueError('不支持此文件类型，请上传安装包、镜像或压缩包')
    if name.split('.')[0].upper() in {'CON','PRN','AUX','NUL',*(f'COM{i}' for i in range(1,10)),*(f'LPT{i}' for i in range(1,10))}:
        name = '_' + name
    return name


def publish(part, directory, filename):
    """Link a complete file into place without overwriting an existing package."""
    stem, ext = os.path.splitext(filename)
    for i in range(10000):
        target = os.path.join(directory, filename if not i else f'{stem}({i}){ext}')
        try:
            os.link(part, target)
            os.unlink(part)
            return os.path.basename(target)
        except FileExistsError:
            continue
    raise ValueError('同名文件过多，请重命名后重试')


class BodyReader:
    def __init__(self, stream, length):
        self.stream, self.remaining, self.buffer = stream, length, b''

    def fill(self):
        if not self.remaining:
            return False
        chunk = self.stream.read(min(65536, self.remaining))
        if not chunk:
            raise ValueError('上传连接中断，文件未保存，请重试')
        self.remaining -= len(chunk)
        self.buffer += chunk
        return True

    def header(self, marker, limit=16384):
        while marker not in self.buffer:
            if len(self.buffer) > limit or not self.fill():
                raise ValueError('上传表单格式不正确')
        value, self.buffer = self.buffer.split(marker, 1)
        if len(value) > limit:
            raise ValueError('上传表单头过长')
        return value

    def payload(self, boundary):
        marker = b'\r\n--' + boundary
        while True:
            index = self.buffer.find(marker)
            if index >= 0:
                required = index + len(marker) + 2
                while len(self.buffer) < required and self.fill():
                    pass
                suffix = self.buffer[index + len(marker):required]
                if suffix == b'--':
                    while len(self.buffer) < required + 2 and self.fill():
                        pass
                    if self.buffer[required:required+2] not in (b'', b'\r\n'):
                        suffix = b'invalid'
                if suffix in (b'--', b'\r\n'):
                    yield self.buffer[:index]
                    self.buffer = self.buffer[index + len(marker):]
                    return
                # A boundary-like byte sequence inside a binary file is ordinary data.
                yield self.buffer[:index+2]
                self.buffer = self.buffer[index+2:]
                continue
            keep = len(marker) + 2
            if len(self.buffer) > keep:
                yield self.buffer[:-keep]
                self.buffer = self.buffer[-keep:]
            if not self.fill():
                raise ValueError('上传表单不完整，文件未保存')


def receive_upload(stream, headers, directory, limit, extensions):
    length = int(headers.get('Content-Length', '0'))
    if length <= 0:
        raise ValueError('上传内容为空或缺少 Content-Length')
    if length > limit + 65536:
        raise ValueError(f'文件超过上传限制（{limit // 1024 // 1024} MB）')
    os.makedirs(directory, exist_ok=True)
    part = os.path.join(directory, '.upload-' + uuid.uuid4().hex + '.part')
    digest, count = hashlib.sha256(), 0
    reader = BodyReader(stream, length)
    def write(chunks, output):
        nonlocal count
        for chunk in chunks:
            count += len(chunk)
            if count > limit:
                raise ValueError('文件超过上传大小限制')
            output.write(chunk)
            digest.update(chunk)
    try:
        ctype = Message(); ctype['Content-Type'] = headers.get('Content-Type', '')
        with open(part, 'xb') as output:
            if ctype.get_content_type() == 'application/octet-stream':
                filename = safe_filename(urllib.parse.unquote(headers.get('X-Filename','')), extensions)
                def chunks():
                    while reader.fill():
                        chunk, reader.buffer = reader.buffer, b''
                        yield chunk
                write(chunks(), output)
            elif ctype.get_content_type() == 'multipart/form-data':
                boundary = ctype.get_param('boundary')
                if not boundary or len(boundary) > 200:
                    raise ValueError('上传表单缺少有效 boundary')
                boundary = boundary.encode('ascii')
                if reader.header(b'\r\n') != b'--' + boundary:
                    raise ValueError('上传表单格式不正确')
                filename = None
                while True:
                    info = BytesParser(policy=email.policy.default).parsebytes(reader.header(b'\r\n\r\n') + b'\r\n\r\n')
                    current = info.get_filename()
                    chunks = reader.payload(boundary)
                    if current:
                        if filename:
                            raise ValueError('每个上传请求只能包含一个文件')
                        filename = safe_filename(current, extensions)
                        write(chunks, output)
                    else:
                        skipped = 0
                        for chunk in chunks:
                            skipped += len(chunk)
                            if skipped > 65536:
                                raise ValueError('上传表单字段过大')
                    if reader.buffer.startswith(b'--'):
                        break
                    reader.buffer = reader.buffer[2:]  # CRLF before next part headers
                if not filename:
                    raise ValueError('未找到上传文件')
                # Drain and validate the final boundary, including its optional CRLF.
                while reader.fill():
                    if len(reader.buffer) > 65536:
                        raise ValueError('上传表单尾部过长')
                if reader.buffer not in (b'--', b'--\r\n'):
                    raise ValueError('上传表单结束标记不正确')
            else:
                raise ValueError('需要文件上传')
        if not count:
            raise ValueError('不能上传空文件')
        saved = publish(part, directory, filename)
        return {'filename':saved, 'size':count, 'sha256':digest.hexdigest()}
    finally:
        if os.path.exists(part):
            os.unlink(part)


class DownloadQueue:
    def __init__(self, data_dir, upload_dir, limit, extensions, on_complete):
        self.path = os.path.join(data_dir, 'download_queue.json')
        self.upload_dir, self.limit = upload_dir, limit
        self.extensions, self.on_complete = extensions, on_complete
        self.lock = threading.RLock()
        self.wake, self.stopped = threading.Event(), threading.Event()
        self.worker = None
        try:
            with open(self.path, encoding='utf-8') as f:
                self.tasks = json.load(f)
        except FileNotFoundError:
            self.tasks = []
        for task in self.tasks:
            if task['status'] in ('downloading', 'cancelling'):
                task.update(status='failed', error='服务重启中断了下载，请点击重试')
                if re.fullmatch(r'[a-f0-9]{32}', task['id']):
                    partial=os.path.join(self.upload_dir,'.queue-'+task['id']+'.part')
                    if os.path.isfile(partial):
                        os.unlink(partial)
        self._save()

    def _save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        temporary = self.path + '.tmp'
        with open(temporary, 'w', encoding='utf-8') as f:
            json.dump(self.tasks, f, ensure_ascii=False, indent=2)
        os.replace(temporary, self.path)

    def start(self):
        with self.lock:
            if self.worker is None:
                self.worker = threading.Thread(target=self._run, daemon=True)
                self.worker.start()
            self.wake.set()

    def snapshot(self):
        with self.lock:
            return [dict(t) for t in self.tasks]

    def enqueue(self, url, software='', filename='', context=None):
        if not isinstance(url, str) or len(url) > 4096:
            raise ValueError('下载地址无效')
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError('请输入不含账号密码的 HTTP/HTTPS 下载地址')
        if filename:
            filename = safe_filename(filename, self.extensions)
        with self.lock:
            if any(t['url'] == url and t['software'] == software and t['status'] in ('queued','downloading','cancelling','indexing') for t in self.tasks):
                raise ValueError('该下载任务已在队列中')
            if sum(t['status'] in ('queued','downloading','cancelling','indexing') for t in self.tasks) >= 100:
                raise ValueError('队列最多容纳 100 个未完成任务')
            task = dict(id=uuid.uuid4().hex, url=url, software=software, filename=filename,
                        status='queued', bytes=0, total=0, speed=0, attempts=0,
                        error='', created=time.time(), updated=time.time())
            if context:
                task.update(context)
            self.tasks.append(task); self._save(); self.wake.set()
            return dict(task)

    def action(self, task_id, action):
        with self.lock:
            task = next((t for t in self.tasks if t['id']==task_id), None)
            if not task:
                raise ValueError('任务不存在')
            if action == 'cancel' and task['status'] in ('queued','downloading'):
                task['status'] = 'cancelled' if task['status']=='queued' else 'cancelling'
            elif action == 'retry' and task['status'] in ('failed','cancelled'):
                task.update(status='queued', error='', bytes=0, total=0, speed=0)
            elif action == 'remove' and task['status'] in ('completed','failed','cancelled'):
                self.tasks.remove(task)
            else:
                raise ValueError('当前任务状态不支持此操作')
            task['updated'] = time.time(); self._save(); self.wake.set()

    def _update(self, task, **values):
        with self.lock:
            task.update(values, updated=time.time()); self._save()

    def _run(self):
        while not self.stopped.is_set():
            with self.lock:
                task = next((t for t in self.tasks if t['status'] in ('queued','indexing')), None)
                indexing = bool(task and task['status']=='indexing')
                if task and not indexing:
                    task.update(status='downloading', attempts=task['attempts']+1, error='')
                    self._save()
                else:
                    self.wake.clear()
            if task:
                if indexing:
                    self._index(task)
                else:
                    self._download(task)
            else:
                self.wake.wait(1)

    def _download(self, task):
        os.makedirs(self.upload_dir, exist_ok=True)
        part = os.path.join(self.upload_dir, '.queue-' + task['id'] + '.part')
        try:
            digest, done = hashlib.sha256(), 0
            start = last = time.monotonic()
            if task.get('source'):
                self._update(task, **updates.resolve(task['source']))
            req = urllib.request.Request(task['url'], headers={'User-Agent':'SoftwareLibrary/10', 'Accept-Encoding':'identity'})
            with urllib.request.urlopen(req, timeout=20) as response:
                if response.headers.get_content_type() in ('text/html','application/json'):
                    raise ValueError('下载地址返回的是网页或接口内容，请填写安装包直链')
                total = int(response.headers.get('Content-Length') or 0)
                if total > self.limit:
                    raise ValueError('远程文件超过下载大小限制')
                filename = task['filename'] or response.headers.get_filename() or urllib.parse.unquote(os.path.basename(urllib.parse.urlparse(response.url).path))
                filename = safe_filename(filename, self.extensions)
                self._update(task, total=total)
                with open(part, 'wb') as output:
                    while True:
                        with self.lock:
                            if task['status']=='cancelling' or self.stopped.is_set():
                                raise InterruptedError('下载已取消')
                        chunk = response.read(65536)
                        if not chunk:
                            break
                        done += len(chunk)
                        if done > self.limit:
                            raise ValueError('远程文件超过下载大小限制')
                        output.write(chunk); digest.update(chunk)
                        now = time.monotonic()
                        if now-last >= 0.5:
                            self._update(task, bytes=done, speed=int(done/max(now-start,0.001)))
                            last = now
                if not done or (total and done != total):
                    raise ValueError('下载文件不完整，请重试')
            with self.lock:
                if task['status']=='cancelling':
                    raise InterruptedError('下载已取消')
                if task.get('expectedSha') and task['expectedSha'].lower()!=digest.hexdigest():
                    raise ValueError('文件 SHA-256 与发布方提供的校验值不一致')
                previous=task.get('previousFile','')
                if (task.get('previousSha')==digest.hexdigest() and previous
                        and os.path.basename(previous)==previous
                        and os.path.isfile(os.path.join(self.upload_dir,previous))):
                    saved=previous
                    task['unchanged']=True
                else:
                    saved = publish(part, self.upload_dir, filename)
                task.update(status='indexing', filename=saved, bytes=done, speed=0, sha256=digest.hexdigest(), error='')
                self._save()
            self._index(task)
        except Exception as exc:
            with self.lock:
                self._update(task, status='cancelled' if task['status']=='cancelling' else 'failed', error=str(exc), speed=0)
        finally:
            if os.path.exists(part):
                os.unlink(part)

    def _index(self, task):
        try:
            self.on_complete(task['filename'], task['software'], task['sha256'], dict(task))
            self._update(task, status='completed', error='')
        except Exception as exc:
            self._update(task, status='completed', error='文件已保存，入库失败，请重新扫描：'+str(exc))

    def stop(self):
        self.stopped.set(); self.wake.set()
        if self.worker:
            self.worker.join(timeout=25)
