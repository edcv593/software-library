import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
import traffic
import versions

class CloudTests(unittest.TestCase):
    def test_pasted_share_text_and_markdown(self):
        samples = [
            'https://115cdn.com/s/swsa3523n8q?password=h884#搜狗输入法.exe访问码：h884复制这段内容，可在115APP中直接打开！',
            '[下载](https://115.com/s/swsa3523n8q) 提取码：h884',
        ]
        for sample in samples:
            self.assertEqual(versions.parse_cloud_share(sample), ('https://115cdn.com/s/swsa3523n8q?password=h884', 'h884'))

    def test_ambiguous_and_invalid_shares_rejected(self):
        for sample in ['https://115.com.evil.test/s/test', 'https://115.com/s/test/other',
                       'https://115.com/s/one https://115.com/s/two',
                       'https://115.com/s/one?password=abcd 访问码：efgh']:
            with self.assertRaises(ValueError): versions.parse_cloud_share(sample)

    def test_share_code_override_and_saved_normalization(self):
        cfg = {}; scan = [{'path':'file.exe','name':'tool'}]
        versions.manage(cfg, scan, {'paths':['file.exe'], 'cloudShare':'https://115.com/s/test?password=old 访问码：other', 'cloudCode':'new'})
        self.assertEqual(cfg['versions']['file.exe']['cloudUrl'], 'https://115cdn.com/s/test?password=new')
        self.assertEqual(cfg['versions']['file.exe']['cloudCode'], 'new')

    def test_claims_are_atomic_and_never_partially_charged(self):
        with tempfile.TemporaryDirectory() as d:
            meter=traffic.Traffic(d);meter.configure({**traffic.DEFAULTS,'dailyMiB':1})
            user={'username':'reader','role':'user'}
            def claim(_):
                try:meter.claim_cloud(user,'file.iso',700000);return True
                except ValueError:return False
            with ThreadPoolExecutor(max_workers=2) as pool:self.assertEqual(sum(pool.map(claim,range(2))),1)
            snap=meter.snapshot();self.assertEqual(snap['usage'][0]['bytes'],700000);self.assertEqual(snap['usage'][0]['cloudClaims'],1)
            self.assertEqual(snap['records'][0]['status'],'cloud_link')
    def test_retry_same_claim_is_not_charged_twice(self):
        with tempfile.TemporaryDirectory() as d:
            meter=traffic.Traffic(d);user={'username':'reader','role':'user'}
            meter.claim_cloud(user,'file.exe',100,'same-request')
            meter.claim_cloud(user,'file.exe',100,'same-request')
            self.assertEqual(meter.snapshot('reader')['used'],100)
            self.assertEqual(meter.snapshot()['usage'][0]['cloudClaims'],1)
            with self.assertRaises(ValueError):meter.claim_cloud(user,'file.exe',100,'same-request','other/file.exe')
    def test_source_validation_and_switch_back(self):
        scan=[{'path':'file.exe','name':'tool'}];cfg={}
        for url in ['http://115.com/s/test','https://evil.example/s/test','https://115.com.evil.example/s/test','https://user@115.com/s/test']:
            with self.assertRaises(ValueError):versions.manage(cfg,scan,{'paths':['file.exe'],'cloudUrl':url})
        versions.manage(cfg,scan,{'paths':['file.exe'],'cloudUrl':'https://115.com/s/example','cloudCode':'abc'})
        self.assertEqual(cfg['versions']['file.exe']['cloudCode'],'abc')
        versions.manage(cfg,scan,{'paths':['file.exe'],'cloudUrl':'','cloudCode':''})
        self.assertEqual(cfg['versions']['file.exe']['cloudUrl'],'')
