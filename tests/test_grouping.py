import copy
import unittest
import grouping

class GroupingTests(unittest.TestCase):
    def setUp(self):
        self.software=[{'name':'Tool 1.2','versions':[{'path':'one.exe'}]}, {'name':'Tool 2.0','versions':[{'path':'two.exe'}]}]
        self.scan=[{'path':'one.exe','name':'Tool 1.2'},{'path':'two.exe','name':'Tool 2.0'}]
    def test_conservative_suggestions(self):
        values=self.software+[{'name':'Tool Pro 2.0','versions':[{'path':'pro.exe'}]},{'name':'Tool Server 2.0','versions':[{'path':'server.exe'}]}]
        self.assertEqual(grouping.suggestions(values)[0]['names'],['Tool 1.2','Tool 2.0'])
        self.assertEqual(len(grouping.suggestions(values)),1)
    def test_merge_preserves_target_and_version_notes(self):
        cfg={'software':{'Tool 1.2':{'notes':'source'},'Tool 2.0':{'notes':'target'}},'versions':{'one.exe':{'notes':'release notes','recommended':True},'two.exe':{'recommended':True}}}
        grouping.merge(cfg,self.scan,self.software,{'names':['Tool 1.2','Tool 2.0'],'target':'Tool 2.0','paths':['one.exe']})
        self.assertEqual(cfg['software']['Tool 2.0']['notes'],'target')
        self.assertTrue(cfg['versions']['two.exe']['recommended'])
        self.assertFalse(cfg['versions']['one.exe']['recommended'])
        self.assertEqual(cfg['versions']['one.exe']['notes'],'release notes')
        self.assertEqual(cfg['versions']['one.exe']['software'],'Tool 2.0')
    def test_stale_confirmation_no_mutation(self):
        cfg={'software':{}}
        before=copy.deepcopy(cfg)
        with self.assertRaises(ValueError):grouping.merge(cfg,self.scan,self.software,{'names':['Tool 1.2','Tool 2.0'],'target':'Tool 2.0','paths':['missing']})
        self.assertEqual(cfg,before)
