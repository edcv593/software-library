import json
import unittest
from unittest.mock import patch
import urllib.parse
import updates


class OfficialAdapters(unittest.TestCase):
    def test_uu_page_resolves_only_the_pc_download(self):
        page='var android_link = "https://example.com/android.apk"; var pc_link = "https://api.nrd.nie.163.com/api/v1/release/dl/1?channel=gwqd";'
        with patch('updates._read_official',return_value=page):
            result=updates.prepare_download(updates.UU_PAGE)
        self.assertEqual(result['provider'],'uu')
        self.assertEqual(result['url'],'https://api.nrd.nie.163.com/api/v1/release/dl/1?channel=gwqd')
        with patch('updates._read_official',return_value='var pc_link = "https://example.com/file.exe";'):
            with self.assertRaises(ValueError):updates.prepare_download(updates.UU_PAGE)

    def test_fnos_old_signed_url_gets_fresh_signature_for_same_file(self):
        clean='https://iso.liveupdate.fnnas.com/x86_64/trim/fnos_Mainland-PE_x86_1.2.0505_2536.iso'
        calls=[]
        def request(url,data=None,headers=None):
            calls.append((url,json.loads(data),headers))
            return json.dumps({'url':clean+'?sign=fresh&t=9999999999'})
        with patch('updates._read_official',side_effect=request):
            result=updates.prepare_download(clean+'?sign=expired&t=1')
        self.assertEqual(calls[0][0],'https://fnnas.com/asset/download-sign')
        self.assertEqual(calls[0][1],{'url':clean})
        self.assertIn('authx',calls[0][2])
        self.assertIn('sign=fresh',result['url'])
        self.assertEqual(result['releaseVersion'],'1.2.0505')

    def test_fnos_homepage_uses_current_x86_iso_not_mobile_app(self):
        iso='https://iso.liveupdate.fnnas.com/x86_64/trim/fnos_Mainland-PE_x86_2.0.0001_9999.iso'
        html='<script>"url\\":\\"'+iso+'\\"; "https://iso.liveupdate.fnnas.com/app.apk";"'+iso+'"</script>'
        with patch('updates._read_official',return_value=html),patch('updates._fnos_signed_url',return_value=iso+'?sign=new') as signer:
            result=updates.prepare_download(updates.FNOS_PAGE)
        signer.assert_called_once_with(iso)
        self.assertEqual(result['releaseVersion'],'2.0.0001')

    def test_changed_pages_and_untrusted_signature_result_fail_closed(self):
        with patch('updates._read_official',return_value='<html>No installer</html>'):
            with self.assertRaises(ValueError):updates.prepare_download(updates.FNOS_PAGE)
            with self.assertRaises(ValueError):updates.prepare_download(updates.UU_PAGE)
        with patch('updates._read_official',return_value='{"url":"https://example.com/not-iso.exe"}'):
            with self.assertRaises(ValueError):updates.prepare_download('https://iso.liveupdate.fnnas.com/test.iso')

    def test_provider_settings_work_without_temporary_url(self):
        for kind,url in [('uu',updates.UU_PAGE),('fnos',updates.FNOS_PAGE)]:
            source=updates.settings({'kind':kind,'auto':True})
            self.assertEqual(updates.resolve(source)['url'],url)
        self.assertEqual(updates.prepare_download('https://example.com/file.exe'),{'url':'https://example.com/file.exe'})


if __name__=='__main__':unittest.main()
