import copy
import unittest
import catalog


class BackupPreviewTests(unittest.TestCase):
    def sample(self):
        return catalog.export_data({'categories':[], 'software':{}, 'versions':{}},
            [{'name':'tool','versions':[{'path':'tool.exe','size':10}]}], '11.15.0', 'today')

    def test_diff_counts_ignore_untrusted_count_fields(self):
        current=self.sample();backup=copy.deepcopy(current)
        backup['counts']={'files':999}
        backup['inventory'][0]['versions'][0]['size']=20
        backup['inventory'][0]['versions'].append({'path':'old.exe','size':1})
        backup['catalog']['software']['tool']={'notes':'old'}
        before=copy.deepcopy(backup)
        result=catalog.compare_export(backup,current)
        self.assertEqual(result['counts']['files'],2)
        self.assertEqual(result['files']['changed']['items'],['tool.exe'])
        self.assertEqual(result['files']['backupOnly']['items'],['old.exe'])
        self.assertEqual(result['software']['backupOnly']['count'],1)
        self.assertEqual(backup,before)

    def test_reject_bad_structures(self):
        current=self.sample()
        for edit in [lambda b:b.update(schemaVersion=True),lambda b:b.update(inventory={}),
                     lambda b:b['inventory'][0]['versions'].append({'path':'tool.exe','size':10}),
                     lambda b:b['inventory'][0]['versions'][0].update(size=-1),
                     lambda b:b['catalog'].update(categories=[{'id':'a','name':'a','parentId':'a'}]),
                     lambda b:b['catalog'].update(categories=[{'id':'a','name':'a','parentId':'missing'}])]:
            backup=copy.deepcopy(current);edit(backup)
            with self.assertRaises(ValueError):catalog.compare_export(backup,current)

    def test_large_diffs_are_capped(self):
        backup=self.sample();current=self.sample()
        backup['inventory'][0]['versions']=[{'path':str(i),'size':1} for i in range(105)]
        result=catalog.compare_export(backup,current)
        self.assertEqual(result['files']['backupOnly']['count'],105)
        self.assertEqual(len(result['files']['backupOnly']['items']),100)
