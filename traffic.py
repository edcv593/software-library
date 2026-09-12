"""Persistent download budgets and aggregate pacing (one application process)."""
from contextlib import contextmanager
import json
import os
import sqlite3
import threading
import time
from datetime import datetime, timezone, timedelta

DEFAULTS = {'speedKiB': 0, 'dailyMiB': 0, 'concurrency': 2, 'adminExempt': False}

class Traffic:
    def __init__(self, directory):
        os.makedirs(directory, exist_ok=True)
        self.path = os.path.join(directory, 'traffic.sqlite3')
        self.lock = threading.RLock()
        self.pace_lock = threading.Lock()
        self.next_slot = 0
        self.active = {}
        with self.db() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS settings (id INTEGER PRIMARY KEY, value TEXT);
                CREATE TABLE IF NOT EXISTS usage (day TEXT, username TEXT, bytes INTEGER, PRIMARY KEY(day,username));
                CREATE TABLE IF NOT EXISTS downloads (id INTEGER PRIMARY KEY, username TEXT, filename TEXT, started REAL, finished REAL, bytes INTEGER DEFAULT 0, status TEXT);
                UPDATE downloads SET status='interrupted', finished=strftime('%s','now') WHERE status='active';
            ''')

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def day():
        return datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d')

    def settings(self):
        with self.db() as db:
            row = db.execute('SELECT value FROM settings WHERE id=1').fetchone()
            return {**DEFAULTS, **(json.loads(row[0]) if row else {})}

    def configure(self, data):
        result = {}
        for key, maximum in [('speedKiB', 1048576), ('dailyMiB', 1073741824), ('concurrency', 32)]:
            value = data.get(key)
            if type(value) is not int or not (1 if key == 'concurrency' else 0) <= value <= maximum:
                raise ValueError('请填写有效的带宽、每日额度和并发数（1–32）')
            result[key] = value
        if type(data.get('adminExempt')) is not bool:
            raise ValueError('管理员豁免必须为开关值')
        result['adminExempt'] = data['adminExempt']
        with self.db() as db:
            db.execute('INSERT OR REPLACE INTO settings VALUES (1,?)', (json.dumps(result),))
        return result

    def exempt(self, user, settings):
        return user['role'] == 'admin' and settings['adminExempt']

    def quota(self, user, settings):
        return 0 if self.exempt(user, settings) else settings['dailyMiB'] * 1048576

    def start(self, user, filename):
        with self.lock:
            settings = self.settings()
            name = user['username']
            if not self.exempt(user, settings) and self.active.get(name, 0) >= settings['concurrency']:
                raise ValueError('同时下载数量已达上限，请等待已有下载完成')
            with self.db() as db:
                used = db.execute('SELECT bytes FROM usage WHERE day=? AND username=?', (self.day(), name)).fetchone()
                quota = self.quota(user, settings)
                if quota and used and used[0] >= quota:
                    raise ValueError('今日下载流量已用完，请明天再试或联系管理员')
                ident = db.execute("INSERT INTO downloads(username,filename,started,status) VALUES (?,?,?,'active')", (name, filename, time.time())).lastrowid
            self.active[name] = self.active.get(name, 0) + 1
            return ident

    def reserve(self, ident, user, size):
        # Reserve before sending: concurrent requests and process restarts cannot bypass quota.
        with self.lock, self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            day = self.day()
            quota = self.quota(user, self.settings())
            row = db.execute('SELECT bytes FROM usage WHERE day=? AND username=?', (day,user['username'])).fetchone()
            used = row[0] if row else 0
            amount = min(size, max(0, quota-used)) if quota else size
            db.execute('INSERT INTO usage VALUES (?,?,?) ON CONFLICT(day,username) DO UPDATE SET bytes=bytes+excluded.bytes', (day,user['username'],amount))
            db.execute('UPDATE downloads SET bytes=bytes+? WHERE id=?',(amount,ident))
            return amount

    def pace(self, size, user):
        settings = self.settings()
        rate = settings['speedKiB'] * 1024
        if not rate or self.exempt(user, settings):
            return
        with self.pace_lock:
            now = time.monotonic()
            self.next_slot = max(now, self.next_slot) + size / rate
            delay = self.next_slot - now
        # Small chunks keep this below one second at the configured rate.
        if delay > 0:
            time.sleep(delay)

    def chunk_size(self, user):
        settings = self.settings()
        rate = settings['speedKiB'] * 1024
        return min(65536, max(1, rate // 10)) if rate and not self.exempt(user, settings) else 65536

    def finish(self, ident, user, status):
        with self.lock:
            self.active[user['username']] = max(0, self.active.get(user['username'],1)-1)
            with self.db() as db:
                db.execute('UPDATE downloads SET status=?,finished=? WHERE id=?',(status,time.time(),ident))
                db.execute("DELETE FROM downloads WHERE status!='active' AND id NOT IN (SELECT id FROM downloads ORDER BY id DESC LIMIT 1000)")
                db.execute("DELETE FROM usage WHERE day < ?", ((datetime.now(timezone(timedelta(hours=8)))-timedelta(days=90)).strftime('%Y-%m-%d'),))

    def snapshot(self, username=None):
        with self.db() as db:
            usage = [dict(row) for row in db.execute('SELECT username,bytes FROM usage WHERE day=? ORDER BY bytes DESC', (self.day(),))]
            if username is not None:
                return {'day': self.day(), 'used': next((r['bytes'] for r in usage if r['username']==username),0), 'settings':self.settings()}
            records = [dict(row) for row in db.execute('SELECT * FROM downloads ORDER BY id DESC LIMIT 100')]
            return {'day':self.day(), 'settings':self.settings(), 'usage':usage, 'records':records}
