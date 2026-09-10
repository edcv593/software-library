import hashlib
import http.server
import io
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import urllib.request
import urllib.parse

import app
import transfers
import updates
import test_catalog


class UploadTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def upload(self,body,ctype='application/octet-stream',filename='工具.exe',limit=1024*1024,length=None):
        class BoundedStream(io.BytesIO):
            def read(self,size=-1):
                if size<0 or size>65536:
                    raise AssertionError('Unbounded upload read')
                return super().read(size)
        headers={'Content-Type':ctype,'Content-Length':str(len(body) if length is None else length),
                 'X-Filename':urllib.parse.quote(filename)}
        return transfers.receive_upload(BoundedStream(body),headers,str(self.root),limit,{'.exe','.zip','.iso'})

    def test_raw_upload_checksum_and_duplicate_names(self):
        content=b'\x00\xffbinary\r\n'*20000
        first=self.upload(content)
        second=self.upload(content)
        self.assertNotEqual(first['filename'],second['filename'])
        self.assertEqual(first['sha256'],hashlib.sha256(content).hexdigest())
        self.assertEqual((self.root/first['filename']).read_bytes(),content)

    def test_quoted_multipart_boundary_with_binary_lookalike(self):
        payload=b'A'*65530+b'\r\n--boundary-not-a-separator\x00\xff\r\n--boundary--also-not-a-separator\r\n'
        body=(b'--boundary\r\nContent-Disposition: form-data; name="note"\r\n\r\nhello\r\n'
              b'--boundary\r\nContent-Disposition: form-data; name="file"; filename="'+ '中文.zip'.encode()+
              b'"\r\nContent-Type: application/zip\r\n\r\n'+payload+b'\r\n--boundary--\r\n')
        result=self.upload(body,'multipart/form-data; boundary="boundary"')
        self.assertEqual((self.root/result['filename']).read_bytes(),payload)
        self.assertEqual(result['filename'],'中文.zip')

    def test_invalid_partial_and_oversized_uploads_leave_no_files(self):
        for kwargs in [{'body':b'x','filename':'bad.txt'}, {'body':b'x'*100,'limit':10},
                       {'body':b'x','length':10}, {'body':b''},
                       {'body':b'--b\r\nContent-Disposition: form-data; name="file"; filename="test.exe"\r\n\r\ntruncated','ctype':'multipart/form-data; boundary=b'}]:
            with self.assertRaises(ValueError):self.upload(**kwargs)
            self.assertEqual(list(self.root.iterdir()),[])


class RemoteFixture(http.server.BaseHTTPRequestHandler):
    payload=b'package-content'*10000
    calls=[]
    gate=threading.Event()
    entered=threading.Event()

    def do_GET(self):
        type(self).calls.append(self.path)
        if self.path=='/fail.exe':
            self.send_error(503);return
        self.send_response(200)
        self.send_header('Content-Type','text/html' if self.path=='/page.exe' else 'application/octet-stream')
        self.send_header('Content-Length',str(len(self.payload)+(100 if self.path=='/partial.exe' else 0)))
        self.end_headers()
        if self.path=='/slow.exe':
            self.entered.set();self.gate.wait(5)
        try:self.wfile.write(self.payload)
        except (BrokenPipeError,ConnectionResetError):pass

    def log_message(self,*args):pass


class QueueTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        RemoteFixture.calls=[];RemoteFixture.gate.clear();RemoteFixture.entered.clear()
        self.server=http.server.ThreadingHTTPServer(('127.0.0.1',0),RemoteFixture)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.url='http://127.0.0.1:'+str(self.server.server_port)
        self.completed=[]
        self.queue=self.new_queue()

    def new_queue(self):
        return transfers.DownloadQueue(str(self.root/'data'),str(self.root/'uploads'),1024*1024,{'.exe'},lambda *args:self.completed.append(args))

    def tearDown(self):
        RemoteFixture.gate.set();self.queue.stop();self.server.shutdown();self.server.server_close();self.thread.join();self.tmp.cleanup()

    def wait_status(self,task,status):
        deadline=time.monotonic()+8
        while time.monotonic()<deadline:
            current=next(t for t in self.queue.snapshot() if t['id']==task['id'])
            if current['status']==status:return current
            time.sleep(.02)
        self.fail(self.queue.snapshot())

    def test_sequential_progress_cancel_and_retry(self):
        first=self.queue.enqueue(self.url+'/slow.exe')
        second=self.queue.enqueue(self.url+'/next.exe')
        self.queue.start();self.assertTrue(RemoteFixture.entered.wait(3))
        self.assertEqual(self.queue.snapshot()[1]['status'],'queued')
        self.queue.action(first['id'],'cancel');RemoteFixture.gate.set()
        self.wait_status(first,'cancelled');done=self.wait_status(second,'completed')
        self.assertEqual(done['bytes'],len(RemoteFixture.payload))
        self.assertEqual(done['sha256'],hashlib.sha256(RemoteFixture.payload).hexdigest())
        self.queue.action(first['id'],'retry');self.wait_status(first,'completed')
        self.assertEqual(len(self.completed),2)
        self.assertFalse(list((self.root/'uploads').glob('*.part')))

    def test_failures_do_not_publish_partial_or_html_files(self):
        tasks=[self.queue.enqueue(self.url+path) for path in ('/partial.exe','/page.exe','/fail.exe')]
        self.queue.start()
        for task in tasks:self.wait_status(task,'failed')
        self.assertEqual(list((self.root/'uploads').iterdir()),[])

    def test_restart_retains_queue_and_marks_interrupted_task(self):
        interrupted=self.queue.enqueue(self.url+'/old.exe')
        pending=self.queue.enqueue(self.url+'/new.exe')
        self.queue.tasks[0]['status']='downloading';self.queue._save()
        self.queue=self.new_queue();self.queue.start()
        self.wait_status(interrupted,'failed');self.wait_status(pending,'completed')
        self.assertNotIn('/old.exe',RemoteFixture.calls)

    def test_restart_finishes_indexing_without_redownload(self):
        task=self.queue.enqueue(self.url+'/saved.exe')
        self.queue.tasks[0].update(status='indexing',filename='saved.exe',sha256='known')
        self.queue._save();self.queue=self.new_queue();self.queue.start()
        self.wait_status(task,'completed')
        self.assertEqual(RemoteFixture.calls,[])
        self.assertEqual(self.completed[0][0],'saved.exe')

    def test_sync_duplicate_hash_and_integrity_mismatch(self):
        task=self.queue.enqueue(self.url+'/first.exe');self.queue.start()
        done=self.wait_status(task,'completed')
        unchanged=self.queue.enqueue(self.url+'/second.exe',context={'previousSha':done['sha256'],'previousFile':done['filename']})
        self.assertTrue(self.wait_status(unchanged,'completed')['unchanged'])
        bad=self.queue.enqueue(self.url+'/third.exe',context={'expectedSha':'0'*64})
        self.wait_status(bad,'failed')
        self.assertEqual(len(list((self.root/'uploads').iterdir())),1)


class VersionAndUploadApiTests(unittest.TestCase):
    setUp=test_catalog.CatalogIntegrationTests.setUp
    tearDown=test_catalog.CatalogIntegrationTests.tearDown

    def request(self,path,body=None,headers=None):
        request=urllib.request.Request(self.url+path,data=None if body is None else (json.dumps(body).encode() if isinstance(body,dict) else body),
            headers={'Content-Type':'application/json','X-Session':self.token,**(headers or {})})
        with urllib.request.urlopen(request) as response:return json.load(response)

    def test_group_split_edit_recommend_and_scan_persistence(self):
        software=app.build_software_list();paths=[s['versions'][0]['path'] for s in software]
        response=self.request('/api/admin/versions',{'paths':paths,'software':'合集'})
        self.assertTrue(response['success'])
        self.assertEqual(len(app.build_software_list()),1)
        for path in paths:
            self.assertTrue(self.request('/api/admin/versions',{'paths':[path],'version':'2.10','platform':'Windows','arch':'x64','recommended':True})['success'])
        app.run_scan();versions=app.build_software_list()[0]['versions']
        self.assertEqual(sum(v['recommended'] for v in versions),1)
        self.assertEqual(versions[0]['path'],paths[-1])
        self.assertTrue(self.request('/api/admin/versions',{'paths':[paths[0]],'software':'拆分'})['success'])
        self.assertEqual(len(app.build_software_list()),2)
        self.assertFalse(self.request('/api/admin/versions',{'paths':['missing'],'version':'x'})['success'])

    def test_upload_is_indexed_and_assigned_before_success_response(self):
        original=app.build_software_list()[0]
        name=original['name']
        result=self.request('/api/upload',b'new installer',{'Content-Type':'application/octet-stream','X-Filename':urllib.parse.quote('新版.exe'),'X-Software':urllib.parse.quote(name)})
        self.assertTrue(result['success']);self.assertTrue(result['indexed'])
        sw=next(s for s in app.build_software_list() if s['name']==name)
        self.assertEqual(len(sw['versions']),2)
        self.assertEqual(len(list(Path(app.ROOT_DIR).iterdir())),2)
        self.assertTrue(any(v['sha256'] for v in sw['versions']))
        self.assertEqual(sw['categoryId'],original['categoryId'])
        self.assertEqual(sw['desc'],original['desc'])

    def test_nested_upload_directory_is_scanned_once(self):
        app.UPLOAD_DIR=str(Path(app.ROOT_DIR)/'uploads')
        Path(app.UPLOAD_DIR).mkdir();(Path(app.UPLOAD_DIR)/'nested.exe').write_bytes(b'installer')
        app.run_scan()
        paths=[v['path'] for s in app.build_software_list() for v in s['versions']]
        self.assertEqual(paths.count('uploads/nested.exe'),1)
        self.assertEqual(len(paths),3)

    def test_official_links_and_update_settings_persist(self):
        name=app.build_software_list()[0]['name']
        data={'name':name,'customOfficial':'https://example.com','downloadUrl':'https://example.com/latest.exe','showOfficial':True,
              'updateSource':{'kind':'direct','url':'https://example.com/latest.exe','auto':True,'intervalHours':24}}
        self.assertTrue(self.request('/api/admin/software',data)['success'])
        app.run_scan();sw=next(s for s in app.build_software_list() if s['name']==name)
        self.assertEqual(sw['customOfficial'],data['customOfficial']);self.assertTrue(sw['updateSource']['auto'])
        data['customOfficial']='javascript:alert(1)'
        self.assertFalse(self.request('/api/admin/software',data)['success'])

    def test_sync_replaces_recommendation_and_keeps_original_files(self):
        name=app.build_software_list()[0]['name']
        Path(app.UPLOAD_DIR).mkdir();(Path(app.UPLOAD_DIR)/'latest.exe').write_bytes(b'latest')
        app.index_transfer('latest.exe',name,hashlib.sha256(b'latest').hexdigest(),{'sync':True,'releaseVersion':'3.0','releaseNotes':'new release'})
        sw=next(s for s in app.build_software_list() if s['name']==name)
        self.assertEqual(sw['versions'][0]['version'],'3.0');self.assertTrue(sw['versions'][0]['recommended'])
        self.assertEqual(sw['versions'][1]['channel'],'archive')
        self.assertEqual(len(list(Path(app.ROOT_DIR).iterdir())),2)

    def test_sync_scan_failure_does_not_change_existing_version(self):
        before=app.build_software_list()
        with patch('app.run_scan',side_effect=OSError('scan failed')):
            with self.assertRaises(OSError):app.index_transfer('latest.exe',before[0]['name'],'hash',{'sync':True})
        self.assertEqual(app.build_software_list(),before)

    def test_management_endpoints_reject_non_admin(self):
        for path,data in [('/api/admin/versions',{'paths':[]}),('/api/admin/fetch',{}),('/api/admin/downloads',{}),('/api/admin/update',{})]:
            self.assertFalse(self.request(path,data,{'X-Session':app.create_session('reader','user')})['success'])

    def test_automatic_updates_obey_opt_in_and_saved_interval(self):
        name=app.build_software_list()[0]['name']
        data={'name':name,'updateSource':{'kind':'direct','url':'https://example.com/latest.exe','auto':True,'intervalHours':24}}
        self.assertTrue(self.request('/api/admin/software',data)['success'])
        queue=transfers.DownloadQueue(app.DATA_DIR,app.UPLOAD_DIR,1024*1024,{'.exe'},lambda *args:None)
        with patch('app.get_download_queue',return_value=queue):
            app.check_updates_once();app.check_updates_once()
        self.assertEqual(len(queue.snapshot()),1)
        self.assertTrue(queue.snapshot()[0]['sync'])
        queue.tasks[0]['status']='completed'
        with patch('app.get_download_queue',return_value=queue):app.check_updates_once()
        self.assertEqual(len(queue.snapshot()),1)
        data['updateSource']['auto']=False
        self.assertTrue(self.request('/api/admin/software',data)['success'])
        with patch('app.get_download_queue',return_value=queue),patch('app.time.time',return_value=time.time()+90000):app.check_updates_once()
        self.assertEqual(len(queue.snapshot()),1)


class UpdateSourceTests(unittest.TestCase):
    def test_github_asset_selection_and_ambiguity(self):
        release={'tag_name':'v2.0','body':'release notes','assets':[
            {'name':'app-win-x64.exe','browser_download_url':'https://example.com/app.exe','digest':'sha256:'+'a'*64},
            {'name':'app-linux.zip','browser_download_url':'https://example.com/app.zip'}]}
        with patch('updates.urllib.request.urlopen',return_value=io.BytesIO(json.dumps(release).encode())):
            resolved=updates.resolve({'kind':'github','repo':'owner/repo','assetPattern':'*win*x64.exe'})
        self.assertEqual(resolved['releaseVersion'],'v2.0');self.assertEqual(resolved['expectedSha'],'a'*64)
        with patch('updates.urllib.request.urlopen',return_value=io.BytesIO(json.dumps(release).encode())):
            with self.assertRaises(ValueError):updates.resolve({'kind':'github','repo':'owner/repo','assetPattern':'*'})

    def test_invalid_source_and_schedule_rejected(self):
        for source in [{'kind':'other'},{'kind':'github','repo':'../bad'}, {'auto':True}, {'intervalHours':0}, {'url':'file:///etc/passwd'}]:
            with self.assertRaises(ValueError):updates.settings(source)


if __name__=='__main__':unittest.main()
