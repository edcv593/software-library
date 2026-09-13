import importlib
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor

import app


class CatalogIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        app.ROOT_DIR = str(root / 'library')
        app.DATA_DIR = str(root / 'data')
        app.UPLOAD_DIR = str(root / 'uploads')
        app.CONFIG_FILE = str(root / 'data/config.json')
        app.SCAN_FILE = str(root / 'data/scan_result.json')
        app.USERS_FILE = str(root / 'data/users.json')
        app.HTML_FILE = str(root / 'data/index.html')
        app.LOG_DIR = str(root / 'data/logs')
        Path(app.ROOT_DIR).mkdir()
        (Path(app.ROOT_DIR) / 'windows.iso').write_bytes(b'windows test')
        (Path(app.ROOT_DIR) / 'python.exe').write_bytes(b'python test')
        app.run_scan()
        self.server = app.http.server.ThreadingHTTPServer(('127.0.0.1', 0), app.SoftwareHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = 'http://127.0.0.1:' + str(self.server.server_port)
        app.create_user('test-admin', 'test-password', 'admin')
        self.token = app.create_session('test-admin', 'admin')

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.tmp.cleanup()

    def request(self, data=None, token=None):
        path = '/api/software' if data is None else '/api/admin/catalog'
        req = urllib.request.Request(self.url + path,
            data=None if data is None else json.dumps(data).encode(),
            headers={'Content-Type': 'application/json', 'X-Session': token or self.token})
        with urllib.request.urlopen(req) as response:
            return json.load(response)

    def fetch_status(self, path, token='', method='GET', body=None):
        req = urllib.request.Request(self.url + path, method=method,
            headers={'Cookie': 'session=' + token, 'Content-Type': 'application/json'},
            data=None if body is None else json.dumps(body).encode())
        try:
            response = urllib.request.urlopen(req)
        except urllib.error.HTTPError as exc:
            response = exc
        with response:
            return response.status, response.read()

    def test_download_access_and_revocation(self):
        self.assertEqual(self.fetch_status('/download/windows.iso')[0], 401)
        app.create_user('reader', 'secret')
        token = app.create_session('reader', 'user')
        self.assertEqual(self.fetch_status('/download/windows.iso', token), (200, b'windows test'))
        status, body = self.fetch_status('/api/users/reader', self.token, 'PUT', {'canDownload': False})
        self.assertTrue(json.loads(body)['success'])
        self.assertEqual(self.fetch_status('/download/windows.iso', token)[0], 403)
        self.fetch_status('/api/users/reader', self.token, 'PUT', {'canDownload': True})
        self.assertEqual(self.fetch_status('/download/windows.iso', token)[0], 200)
        app.delete_user('reader')
        app.create_user('reader', 'new-password')
        self.assertEqual(self.fetch_status('/download/windows.iso', token)[0], 401)

    def test_download_bypass_and_concurrency(self):
        Path(app.UPLOAD_DIR).mkdir(exist_ok=True)
        (Path(app.UPLOAD_DIR) / 'private.exe').write_bytes(b'private')
        for path in ('/users.json', '/uploads/private.exe', '/logs/', '/config.json'):
            self.assertEqual(self.fetch_status(path)[0], 404)
            self.assertEqual(self.fetch_status(path, method='HEAD')[0], 405)
        self.assertEqual(self.fetch_status('/download/uploads/private.exe')[0], 401)
        app.get_traffic().active['test-admin'] = 2
        try:
            self.assertEqual(self.fetch_status('/download/windows.iso', self.token)[0], 429)
        finally:
            app.get_traffic().active.clear()
        self.assertEqual(self.fetch_status('/download/windows.iso', self.token)[0], 200)
        self.assertEqual(self.fetch_status('/download/uploads/private.exe', self.token)[0], 200)

    def test_software_merge_persists_and_keeps_files(self):
        data=self.request()['data']
        target,source=data[0],data[1]
        req={'action':'merge','names':[target['name'],source['name']],'target':target['name'],'paths':[v['path'] for v in source['versions']]}
        _,body=self.fetch_status('/api/admin/versions',self.token,'POST',req)
        self.assertTrue(json.loads(body)['success'])
        app.run_scan()
        merged=self.request()['data']
        self.assertEqual(len(merged),1)
        self.assertEqual(len(merged[0]['versions']),2)
        self.assertEqual(len(list(Path(app.ROOT_DIR).iterdir())),2)
        _,body=self.fetch_status('/api/admin/versions',self.token,'POST',req)
        self.assertFalse(json.loads(body)['success'])

    def test_pending_approval_rollback_and_public_access(self):
        import hashlib
        app.create_user('reader','secret')
        reader=app.create_session('reader','user')
        name=app.build_software_list()[0]['name']
        old=app.build_software_list()[0]['versions'][0]['path']
        Path(app.UPLOAD_DIR).mkdir()
        (Path(app.UPLOAD_DIR)/'candidate.exe').write_bytes(b'candidate')
        app.index_transfer('candidate.exe',name,hashlib.sha256(b'candidate').hexdigest(),{'sync':True})
        _,public=self.fetch_status('/api/software',reader)
        self.assertFalse(any(v['filename']=='candidate.exe' for sw in json.loads(public)['data'] for v in sw['versions']))
        self.assertEqual(self.fetch_status('/download/uploads/candidate.exe',reader)[0],403)
        self.assertEqual(self.fetch_status('/download/uploads/./candidate.exe',reader)[0],403)
        self.assertEqual(self.fetch_status('/download/uploads/candidate.exe',self.token)[0],200)
        action={'action':'approve','paths':['uploads/candidate.exe']}
        _,denied=self.fetch_status('/api/admin/versions',reader,'POST',action)
        self.assertFalse(json.loads(denied)['success'])
        _,approved=self.fetch_status('/api/admin/versions',self.token,'POST',action)
        self.assertTrue(json.loads(approved)['success'])
        self.assertEqual(self.fetch_status('/download/uploads/candidate.exe',reader)[0],200)
        _,stale=self.fetch_status('/api/admin/versions',self.token,'POST',action)
        self.assertFalse(json.loads(stale)['success'])
        _,rolled=self.fetch_status('/api/admin/versions',self.token,'POST',{'action':'rollback','paths':[old]})
        self.assertTrue(json.loads(rolled)['success'])
        sw=next(s for s in app.build_software_list() if s['name']==name)
        self.assertEqual(next(v for v in sw['versions'] if v['recommended'])['path'],old)
        self.assertTrue((Path(app.UPLOAD_DIR)/'candidate.exe').exists())

    def test_disable_reset_and_self_password(self):
        app.create_user('reader','old-password')
        token=app.create_session('reader','user')
        _,body=self.fetch_status('/api/users/reader',self.token,'PUT',{'disabled':True})
        self.assertTrue(json.loads(body)['success'])
        self.assertIsNone(app.get_session(token))
        self.assertFalse(app.verify_user('reader','old-password')[0])
        self.fetch_status('/api/users/reader',self.token,'PUT',{'disabled':False})
        self.assertIsNone(app.get_session(token))
        token=app.create_session('reader','user')
        _,body=self.fetch_status('/api/users/reader',self.token,'PUT',{'password':'reset-password'})
        self.assertFalse(json.loads(body)['success'])
        _,body=self.fetch_status('/api/password',token,'POST',{'currentPassword':'old-password','password':'my-new-password'})
        self.assertFalse(json.loads(body)['success'])
        _,body=self.fetch_status('/api/users/test-admin',self.token,'PUT',{'disabled':True})
        self.assertFalse(json.loads(body)['success'])

    def test_legacy_password_migrates_after_success(self):
        import hashlib
        users=app.load_users()
        users['users'][0]['password']=hashlib.sha256(b'old').hexdigest()
        app.save_users(users)
        self.assertFalse(app.verify_user('test-admin','wrong')[0])
        self.assertTrue(app.verify_user('test-admin','old')[0])
        self.assertTrue(app.find_user('test-admin')['password'].startswith('pbkdf2_sha256$'))

    def test_email_signup_binding_and_password_reset(self):
        from unittest.mock import patch
        service=app.get_email_signup()
        service.configure({'enabled':True,'username':'sender@qq.com','sender':'sender@qq.com','password':'test-secret'})
        with patch.object(service,'deliver') as send:
            self.fetch_status('/api/signup-code',method='POST',body={'email':'new@qq.com'})
            code=send.call_args.args[2]
            _,body=self.fetch_status('/api/signup',method='POST',body={'email':'new@qq.com','code':code,'password':'new-password'})
            result=json.loads(body)
            self.assertTrue(result['success']);self.assertFalse(result['pending'])
            token=result['session']
            self.assertEqual(app.get_session(token)['role'],'user')
            self.fetch_status('/api/reset-code',method='POST',body={'email':'new@qq.com'})
            code=send.call_args.args[2]
            _,body=self.fetch_status('/api/reset-password',method='POST',body={'email':'new@qq.com','code':code,'password':'reset-password'})
            self.assertTrue(json.loads(body)['success']);self.assertIsNone(app.get_session(token))
            self.assertTrue(app.verify_user('new@qq.com','reset-password')[0])
            self.fetch_status('/api/bind-code',self.token,'POST',{'email':'owner@qq.com'})
            code=send.call_args.args[2]
            _,body=self.fetch_status('/api/bind-email',self.token,'POST',{'email':'owner@qq.com','code':code})
            self.assertTrue(json.loads(body)['success'])
            _,body=self.fetch_status('/api/login',method='POST',body={'username':'owner@qq.com','password':'test-password'})
            self.assertEqual(json.loads(body)['username'],'test-admin')
            self.assertTrue(app.find_user('owner@qq.com')['emailVerified'])
        _,body=self.fetch_status('/api/admin/email-settings',self.token)
        self.assertNotIn('password',json.loads(body)['settings'])
        self.assertEqual(self.fetch_status('/mail-settings.json')[0],404)
        _,body=self.fetch_status('/api/admin/email-settings')
        self.assertFalse(json.loads(body)['success'])

    def test_cloud_source_claim_is_private_and_blocks_local_fallback(self):
        path='windows.iso';url='https://115cdn.com/s/example'
        _,body=self.fetch_status('/api/admin/versions',self.token,'POST',{'paths':[path],'cloudUrl':url,'cloudCode':'abcd'})
        self.assertTrue(json.loads(body)['success'])
        app.create_user('reader','test-password');reader=app.create_session('reader','user')
        _,body=self.fetch_status('/api/software',reader)
        version=next(v for sw in json.loads(body)['data'] for v in sw['versions'] if v['path']==path)
        self.assertEqual(version['cloudProvider'],'115');self.assertNotIn('cloudUrl',version)
        self.assertEqual(self.fetch_status('/download/windows.iso',reader)[0],403)
        _,body=self.fetch_status('/api/cloud-download',reader,'POST',{'path':path})
        result=json.loads(body);self.assertTrue(result['success']);self.assertEqual(result['url'],url)
        self.assertEqual(app.get_traffic().snapshot('reader')['used'],len(b'windows test'))
        self.fetch_status('/api/users/reader',self.token,'PUT',{'canDownload':False})
        _,body=self.fetch_status('/api/cloud-download',reader,'POST',{'path':path})
        self.assertFalse(json.loads(body)['success'])
        self.fetch_status('/api/admin/versions',self.token,'POST',{'paths':[path],'cloudUrl':''})
        self.assertEqual(self.fetch_status('/download/windows.iso',self.token)[0],200)

    def test_traffic_settings_and_download_meter(self):
        app.create_user('reader', 'secret')
        token = app.create_session('reader', 'user')
        settings = {'speedKiB':100, 'dailyMiB':1, 'concurrency':1, 'adminExempt':False}
        _, denied = self.fetch_status('/api/admin/traffic', token, 'PUT', settings)
        self.assertFalse(json.loads(denied)['success'])
        _, saved = self.fetch_status('/api/admin/traffic', self.token, 'PUT', settings)
        self.assertTrue(json.loads(saved)['success'])
        self.assertEqual(self.fetch_status('/download/windows.iso', token), (200,b'windows test'))
        _, usage = self.fetch_status('/api/my-traffic', token)
        self.assertEqual(json.loads(usage)['used'],len(b'windows test'))
        meter=app.get_traffic()
        user=app.get_session(token)
        # Consume the remaining allowance without sending a large test fixture.
        meter.reserve(0,user,1048576)
        self.assertEqual(self.fetch_status('/download/windows.iso', token)[0],429)
        _, logs = self.fetch_status('/api/admin/traffic', self.token)
        self.assertEqual(json.loads(logs)['records'][0]['filename'],'windows.iso')
        _, version = self.fetch_status('/api/version')
        self.assertEqual(json.loads(version)['version'],'11.6.0')

    def test_reader_cannot_grant_download_permission(self):
        app.create_user('reader', 'secret')
        token = app.create_session('reader', 'user')
        _, body = self.fetch_status('/api/users/reader', token, 'PUT', {'canDownload': True})
        self.assertFalse(json.loads(body)['success'])

    def create(self, name, parent=''):
        self.assertTrue(self.request({'action':'create','name':name,'parentId':parent})['success'])
        return next(n['id'] for n in self.request()['categories'] if n['name'] == name)

    def test_migration_move_metadata_rescan_restart_and_delete(self):
        initial = self.request()
        self.assertEqual(len(initial['categories']), 2)
        parent = self.create('我的软件')
        child = self.create('常用工具', parent)
        names = [s['name'] for s in initial['data']]
        self.assertTrue(self.request({'action':'move','names':names,'categoryId':child})['success'])
        metadata = {'action':'metadata','names':[names[0]],'displayName':'个人工具',
            'notes':'第一行\n第二行','desc':'自定义简介','tags':['常用','常用'],
            'customFields':{'许可证':'个人版','危险字符':'<script>"&'}}
        self.assertTrue(self.request(metadata)['success'])
        self.assertTrue(self.request({'action':'update','id':parent,'name':'收藏','parentId':''})['success'])
        app.run_scan()
        # Reload the module to simulate a process restart with the same persistent paths.
        paths = {key:getattr(app,key) for key in ('ROOT_DIR','DATA_DIR','UPLOAD_DIR','CONFIG_FILE','SCAN_FILE','USERS_FILE','HTML_FILE','LOG_DIR')}
        importlib.reload(app)
        for key,value in paths.items(): setattr(app,key,value)
        app.create_user('test-admin', 'test-password', 'admin')
        self.token = app.create_session('test-admin','admin')
        data = self.request()['data']
        self.assertTrue(all(s['categoryId'] == child for s in data))
        edited = next(s for s in data if s['name'] == names[0])
        self.assertEqual(edited['displayName'], '个人工具')
        self.assertEqual(edited['tags'], ['常用'])
        self.assertEqual(edited['customFields'], metadata['customFields'])
        target = self.create('保留')
        self.assertTrue(self.request({'action':'delete','id':parent,'targetId':target})['success'])
        self.assertTrue(all(s['categoryId'] == target for s in self.request()['data']))
        self.assertEqual(len(list(Path(app.ROOT_DIR).iterdir())), 2)

    def test_invalid_operations_are_atomic(self):
        parent = self.create('分类')
        child = self.create('子分类', parent)
        before = Path(app.CONFIG_FILE).read_bytes()
        for bad in [
            {'action':'update','id':parent,'name':'循环','parentId':child},
            {'action':'create','name':'分类'},
            {'action':'delete','id':parent,'targetId':child},
            {'action':'move','names':['missing'],'categoryId':child},
            {'action':'move','names':[self.request()['data'][0]['name']],'categoryId':'missing'},
            {'action':'metadata','names':[self.request()['data'][0]['name']],'customFields':{'x':[]}},
            {'action':'create','name':''},
            [],
        ]:
            self.assertFalse(self.request(bad)['success'], bad)
            self.assertEqual(Path(app.CONFIG_FILE).read_bytes(), before)

    def test_permissions(self):
        for token in ('invalid', app.create_session('reader','user')):
            response = self.request({'action':'create','name':'Forbidden'},token)
            self.assertFalse(response['success'])
            self.assertIn(response['error'],('未登录','权限不足'))
        self.assertFalse(Path(app.CONFIG_FILE).exists())

    def test_parallel_updates_and_empty_categories(self):
        self.create('空分类')
        with ThreadPoolExecutor(max_workers=5) as pool:
            results = list(pool.map(lambda i:self.request({'action':'create','name':str(i)}),range(10)))
        self.assertTrue(all(r['success'] for r in results))
        self.assertEqual(len(self.request()['categories']),13)

    def test_legacy_slash_category_and_html(self):
        data = app.load_json(app.SCAN_FILE,{})
        data['items'][0]['category'] = 'NAS/存储'
        app.save_json(app.SCAN_FILE,data)
        nodes = self.request()['categories']
        self.assertEqual(next(n for n in nodes if n['name']=='NAS/存储')['parentId'],'')
        html = app.generate_html()
        self.assertIn('function renderTree()',html)
        self.assertIn('library-layout',html)
        self.assertNotIn('__ICONS_JSON__',html)


if __name__ == '__main__':
    unittest.main()
