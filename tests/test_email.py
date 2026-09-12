import tempfile
import unittest
from unittest.mock import patch
import email_signup

class EmailTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.service=email_signup.EmailSignup(self.tmp.name)
        self.service.configure({'enabled':True,'username':'sender@qq.com','sender':'sender@qq.com','password':'test-authorization'})
    def tearDown(self):self.tmp.cleanup()
    def test_purpose_single_use_and_secret_redaction(self):
        with patch.object(self.service,'deliver') as send:
            self.service.request_code('reader@qq.com','ip','reset');code=send.call_args.args[2]
        with self.assertRaises(ValueError):self.service.verify_code('reader@qq.com',code,'signup')
        self.service.verify_code('reader@qq.com',code,'reset')
        with self.assertRaises(ValueError):self.service.verify_code('reader@qq.com',code,'reset')
        self.assertNotIn('password',self.service.public_settings())
        self.service.configure({'password':''})
        self.assertEqual(self.service.settings()['password'],'test-authorization')
    def test_attempts_cooldown_and_persistence(self):
        with patch.object(self.service,'deliver') as send:
            self.service.request_code('reader@qq.com','ip');code=send.call_args.args[2]
            with self.assertRaises(ValueError):self.service.request_code('reader@qq.com','ip')
        service=email_signup.EmailSignup(self.tmp.name)
        wrong='000000' if code!='000000' else '111111'
        for _ in range(5):
            with self.assertRaises(ValueError):service.verify_code('reader@qq.com',wrong)
        with self.assertRaises(ValueError):service.verify_code('reader@qq.com',code)
    def test_closed_signup_still_allows_password_recovery(self):
        self.service.configure({'enabled':False})
        with patch.object(self.service,'deliver'):
            with self.assertRaises(ValueError):self.service.request_code('reader@qq.com','ip')
            self.service.request_code('reader@qq.com','ip','reset')
    def test_mail_failure_never_leaves_usable_code(self):
        with patch.object(self.service,'deliver',side_effect=OSError('sensitive error')):
            with self.assertRaisesRegex(ValueError,'邮件发送失败'):self.service.request_code('reader@qq.com','ip')
        with self.service.db() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM codes').fetchone()[0],0)
