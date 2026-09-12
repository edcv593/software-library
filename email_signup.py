"""Email signup verification with persisted cooldowns; SMTP is configured by admins."""
import hashlib
import json
import re
import secrets
import smtplib
import sqlite3
import ssl
import time
from email.message import EmailMessage
from pathlib import Path
from contextlib import contextmanager

DEFAULTS={'enabled':False,'approval':False,'host':'smtp.qq.com','port':465,'security':'ssl','username':'','sender':'','password':''}

def email_address(value):
    if not isinstance(value,str):raise ValueError('请填写有效邮箱')
    value=value.strip().lower()
    if len(value)>254 or not re.fullmatch(r'[a-z0-9.!#$%&\x27*+/=?^_`{|}~-]+@[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?\.[a-z]{2,63}',value):raise ValueError('请填写有效邮箱')
    return value

class EmailSignup:
    def __init__(self,directory):
        self.root=Path(directory);self.root.mkdir(parents=True,exist_ok=True)
        self.settings_file=self.root/'mail-settings.json'
        with self.db() as db:
            db.executescript('CREATE TABLE IF NOT EXISTS codes(email TEXT PRIMARY KEY,digest TEXT,expires REAL,attempts INTEGER,sent REAL); CREATE TABLE IF NOT EXISTS sends(ip TEXT,at REAL);')
    @contextmanager
    def db(self):
        db=sqlite3.connect(self.root/'email-signup.sqlite3',timeout=15)
        try:
            with db:yield db
        finally:db.close()
    def settings(self):
        if self.settings_file.exists():return {**DEFAULTS,**json.loads(self.settings_file.read_text(encoding='utf-8'))}
        return dict(DEFAULTS)
    def public_settings(self):
        settings=self.settings();return {k:v for k,v in settings.items() if k!='password'}|{'passwordSet':bool(settings['password'])}
    def configure(self,data):
        if not isinstance(data,dict):raise ValueError('邮件设置格式无效')
        current=self.settings()
        result={**current,**{k:v for k,v in data.items() if k in DEFAULTS and k!='password'}}
        if data.get('password'):result['password']=data['password']
        if type(result['enabled']) is not bool or type(result['approval']) is not bool:raise ValueError('注册设置无效')
        if type(result['port']) is not int or not 1<=result['port']<=65535:raise ValueError('SMTP 端口无效')
        if result['security'] not in ('ssl','starttls'):raise ValueError('SMTP 必须使用加密连接')
        for key in ('host','username','sender','password'):
            if not isinstance(result[key],str) or len(result[key])>1024 or '\n' in result[key] or '\r' in result[key]:raise ValueError('邮件设置格式无效')
        if result['enabled']:
            if not result['host'] or not result['username'] or not result['password']:raise ValueError('请先配置 SMTP 服务器、账号和授权码')
            result['sender']=email_address(result['sender'])
        temp=self.settings_file.with_suffix('.tmp')
        temp.write_text(json.dumps(result),encoding='utf-8');temp.replace(self.settings_file)
        return self.public_settings()
    def request_code(self,email,ip,purpose="signup"):
        key=purpose+":"+email_address(email)
        email=email_address(email);settings=self.settings()
        if purpose=='signup' and not settings['enabled']:raise ValueError('暂未开放邮箱注册，请联系管理员')
        if not settings['host'] or not settings['username'] or not settings['password'] or not settings['sender']:raise ValueError('管理员尚未配置发件邮箱')
        code=f'{secrets.randbelow(1000000):06d}'
        salt=secrets.token_hex(16)
        digest=salt+'$'+hashlib.sha256((salt+code).encode()).hexdigest()
        now=time.time()
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('DELETE FROM sends WHERE at<?',(now-3600,))
            db.execute('DELETE FROM codes WHERE expires<?',(now,))
            recent=db.execute('SELECT sent FROM codes WHERE email=?',(key,)).fetchone()
            if recent and now-recent[0]<60:raise ValueError('请等待 60 秒后再发送验证码')
            if db.execute('SELECT COUNT(*) FROM sends WHERE ip=?',(ip,)).fetchone()[0]>=5:raise ValueError('当前来源发送次数过多，请一小时后重试')
            if db.execute('SELECT COUNT(*) FROM sends').fetchone()[0]>=100:raise ValueError('发送请求较多，请稍后重试')
            db.execute('INSERT OR REPLACE INTO codes VALUES (?,?,?,0,?)',(key,digest,now+600,now))
            db.execute('INSERT INTO sends VALUES (?,?)',(ip,now))
        try:self.deliver(settings,email,code,purpose)
        except Exception:
            with self.db() as db:db.execute('DELETE FROM codes WHERE email=? AND digest=?',(key,digest))
            raise ValueError('邮件发送失败，请联系管理员检查 SMTP 设置') from None
    @staticmethod
    def deliver(settings,email,code,purpose="signup"):
        message=EmailMessage();message['Subject']='软件库邮箱验证码';message['From']=settings['sender'];message['To']=email
        label='注册账号' if purpose=='signup' else '重置密码' if purpose=='reset' else '绑定邮箱'
        message.set_content(f'你正在进行{label}，验证码：{code}\n验证码 10 分钟内有效。若非本人操作，请忽略此邮件。')
        context=ssl.create_default_context()
        if settings['security']=='ssl':client=smtplib.SMTP_SSL(settings['host'],settings['port'],timeout=15,context=context)
        else:
            client=smtplib.SMTP(settings['host'],settings['port'],timeout=15)
        with client:
            if settings['security']=='starttls':client.ehlo();client.starttls(context=context);client.ehlo()
            client.login(settings['username'],settings['password']);client.send_message(message)
    def verify_code(self,email,code,purpose="signup"):
        email=email_address(email);key=purpose+":"+email
        if not isinstance(code,str) or not re.fullmatch(r'\d{6}',code):raise ValueError('请输入 6 位验证码')
        valid=False
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT digest,expires,attempts FROM codes WHERE email=?',(key,)).fetchone()
            if row and row[1]>time.time() and row[2]<5:
                salt,digest=row[0].split('$')
                valid=secrets.compare_digest(hashlib.sha256((salt+code).encode()).hexdigest(),digest)
                if valid:db.execute('DELETE FROM codes WHERE email=?',(key,))
                else:db.execute('UPDATE codes SET attempts=attempts+1 WHERE email=?',(key,))
        if not valid:raise ValueError('验证码无效、已过期或尝试次数过多，请重新获取')
        return email
