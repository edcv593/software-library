"""Password compatibility and bounded login throttling."""
import hashlib
import hmac
import secrets
import threading
import time

ITERATIONS=300000

def hash_password(password):
    salt=secrets.token_hex(16)
    digest=hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(salt),ITERATIONS).hex()
    return f'pbkdf2_sha256${ITERATIONS}${salt}${digest}'

def check_password(password,encoded):
    if not isinstance(password,str) or len(password)>1024:return False
    try:
        if encoded.startswith('pbkdf2_sha256$'):
            _,count,salt,digest=encoded.split('$')
            count=int(count)
            if not 10000<=count<=2000000:return False
            actual=hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(salt),count).hex()
        else:actual=hashlib.sha256(password.encode()).hexdigest();digest=encoded
        return hmac.compare_digest(actual,digest)
    except (ValueError,TypeError,AttributeError):return False

def validate_password(password):
    if not isinstance(password,str) or not 8<=len(password)<=128:
        raise ValueError('新密码长度需为 8–128 个字符')

class LoginGuard:
    def __init__(self):self.lock=threading.Lock();self.entries={}
    def attempt(self,username,address):
        with self.lock:
            now=time.monotonic()
            self.entries={k:v for k,v in self.entries.items() if v[1]>now}
            keys=[('user',username),('ip',address)]
            for key,limit in zip(keys,[5,30]):
                if self.entries.get(key,(0,0))[0]>=limit:return False
            if len(self.entries)>10000:return False
            for key in keys:
                count,end=self.entries.get(key,(0,now+300))
                self.entries[key]=(count+1,end)
            return True
    def success(self,username,address):
        with self.lock:
            self.entries.pop(('user',username),None)
            key=('ip',address)
            if key in self.entries:
                count,end=self.entries[key]
                self.entries[key]=(max(0,count-1),end)
