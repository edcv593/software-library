import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import traffic

class TrafficTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.meter=traffic.Traffic(self.tmp.name)
        self.user={'username':'reader','role':'user'}
    def tearDown(self):self.tmp.cleanup()
    def configure(self,**values):self.meter.configure({**traffic.DEFAULTS,**values})
    def test_quota_atomic_and_persistent(self):
        self.configure(dailyMiB=1)
        ident=self.meter.start(self.user,'file.iso')
        with ThreadPoolExecutor(max_workers=8) as pool:
            amounts=list(pool.map(lambda _:self.meter.reserve(ident,self.user,65536),range(32)))
        self.assertEqual(sum(amounts),1048576)
        self.meter.finish(ident,self.user,'quota')
        restarted=traffic.Traffic(self.tmp.name)
        self.assertEqual(restarted.snapshot('reader')['used'],1048576)
        with self.assertRaises(ValueError):restarted.start(self.user,'retry.iso')
        with patch.object(restarted,'day',return_value='2099-01-01'):
            self.assertIsInstance(restarted.start(self.user,'tomorrow.iso'),int)
    def test_concurrency_and_exemption(self):
        self.configure(concurrency=1,adminExempt=True)
        ident=self.meter.start(self.user,'one')
        with self.assertRaises(ValueError):self.meter.start(self.user,'two')
        self.meter.finish(ident,self.user,'interrupted')
        self.meter.start(self.user,'retry')
        admin={'username':'admin','role':'admin'}
        self.meter.start(admin,'one');self.meter.start(admin,'two')
    def test_aggregate_pacing(self):
        self.configure(speedKiB=100)
        with patch('traffic.time.monotonic',return_value=10),patch('traffic.time.sleep') as sleep:
            self.meter.pace(10240,self.user)
            self.meter.pace(10240,{'username':'other','role':'user'})
            self.assertAlmostEqual(sleep.call_args_list[0].args[0],0.1)
            self.assertAlmostEqual(sleep.call_args_list[1].args[0],0.2)
    def test_crash_record_and_validation(self):
        self.meter.start(self.user,'interrupted.iso')
        restarted=traffic.Traffic(self.tmp.name)
        self.assertEqual(restarted.snapshot()['records'][0]['status'],'interrupted')
        for values in ({'concurrency':0},{'dailyMiB':-1},{'speedKiB':True},{'adminExempt':'yes'}):
            with self.assertRaises(ValueError):self.configure(**values)
