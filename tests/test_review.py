import unittest
import versions

class ReviewTests(unittest.TestCase):
    def test_rejection_never_changes_existing_recommendation(self):
        scan=[{'name':'Tool','path':'old.exe'},{'name':'Tool','path':'new.exe'}]
        cfg={'versions':{'old.exe':{'recommended':True},'new.exe':{'reviewState':'pending'}}}
        versions.review(cfg,scan,{'action':'reject','paths':['new.exe']})
        self.assertTrue(cfg['versions']['old.exe']['recommended'])
        self.assertEqual(cfg['versions']['new.exe']['reviewState'],'rejected')
        with self.assertRaises(ValueError):versions.manage(cfg,scan,{'paths':['new.exe'],'recommended':True})
        with self.assertRaises(ValueError):versions.review(cfg,scan,{'action':'rollback','paths':['new.exe']})
        versions.review(cfg,scan,{'action':'reopen','paths':['new.exe']})
        self.assertEqual(cfg['versions']['new.exe']['reviewState'],'pending')
    def test_other_pending_versions_are_not_published_by_approval(self):
        scan=[{'name':'Tool','path':p} for p in ['old.exe','new.exe','other.exe']]
        cfg={'versions':{'old.exe':{'recommended':True},'new.exe':{'reviewState':'pending'},'other.exe':{'reviewState':'pending'}}}
        versions.review(cfg,scan,{'action':'approve','paths':['new.exe']})
        self.assertEqual(cfg['versions']['other.exe']['reviewState'],'pending')
        self.assertEqual(cfg['versions']['old.exe']['channel'],'archive')
        self.assertTrue(cfg['versions']['new.exe']['recommended'])
