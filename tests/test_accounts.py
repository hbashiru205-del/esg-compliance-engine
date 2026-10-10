import os
import tempfile
import unittest
from pathlib import Path

from backend import accounts


class AccountTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old_path = accounts.DB_PATH
        accounts.DB_PATH = Path(self.temp.name) / "accounts.db"

    def tearDown(self):
        accounts.DB_PATH = self.old_path
        self.temp.cleanup()

    def test_create_and_authenticate(self):
        token = accounts.create_user("Hassan_23", "correct-horse-123", "Hassan Bashiru")
        self.assertTrue(token)
        self.assertEqual(accounts.authenticate_user("hassan_23", "correct-horse-123"), token)
        self.assertIsNone(accounts.authenticate_user("hassan_23", "wrong-password"))
        self.assertEqual(accounts.get_account(token)["account_name"], "Hassan Bashiru")

    def test_duplicate_username_rejected_case_insensitively(self):
        accounts.create_user("Hassan23", "correct-horse-123", "Hassan")
        with self.assertRaisesRegex(ValueError, "already taken"):
            accounts.create_user("hassan23", "another-password", "Other User")

    def test_password_and_username_validation(self):
        with self.assertRaisesRegex(ValueError, "at least 8"):
            accounts.create_user("valid_user", "short", "Valid Name")
        with self.assertRaisesRegex(ValueError, "Username must"):
            accounts.create_user("x", "valid-password", "Valid Name")

    def test_password_is_not_stored_as_plain_text(self):
        accounts.create_user("safe_user", "not-plaintext-password", "Safe User")
        conn = accounts._connect()
        try:
            salt, digest = conn.execute("SELECT password_salt, password_hash FROM accounts WHERE username='safe_user'").fetchone()
        finally:
            conn.close()
        self.assertNotEqual(digest, "not-plaintext-password")
        self.assertNotIn("not-plaintext-password", digest)
        self.assertTrue(salt)


if __name__ == "__main__":
    unittest.main()
