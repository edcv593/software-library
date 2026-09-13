import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
import traffic
import versions

class CloudTests(unittest.TestCase):
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
