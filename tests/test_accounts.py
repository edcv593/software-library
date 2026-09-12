import hashlib
import unittest
from unittest.mock import patch
import accounts

class AccountSecurityTests(unittest.TestCase):
    def test_salted_hash_and_legacy_password(self):
        first=accounts.hash_password('same-password');second=accounts.hash_password('same-password')
        self.assertNotEqual(first,second)
        self.assertTrue(accounts.check_password('same-password',first))
        self.assertFalse(accounts.check_password('wrong-password',first))
        self.assertTrue(accounts.check_password('old',hashlib.sha256(b'old').hexdigest()))
        self.assertFalse(accounts.check_password('old','pbkdf2_sha256$999999999$bad$bad'))
    def test_attempt_limit_expiry_and_success(self):
        guard=accounts.LoginGuard()
        with patch('accounts.time.monotonic',return_value=100):
            for _ in range(5):self.assertTrue(guard.attempt('reader','ip'))
            self.assertFalse(guard.attempt('reader','different-ip'))
        with patch('accounts.time.monotonic',return_value=401):self.assertTrue(guard.attempt('reader','ip'))
        guard.success('reader','ip')
        self.assertNotIn(('user','reader'),guard.entries)
    def test_source_address_limit_and_validation(self):
        guard=accounts.LoginGuard()
        for i in range(30):self.assertTrue(guard.attempt(str(i),'same-ip'))
        self.assertFalse(guard.attempt('new-account','same-ip'))
        for password in ('short','a'*129,None):
            with self.assertRaises(ValueError):accounts.validate_password(password)
