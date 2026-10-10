"""Offline tests for account validation, password authentication and durable DB selection."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend import accounts


class AccountTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp.name) / "accounts.sqlite3"
        self.path_patch = patch.object(accounts, "DB_PATH", self.db_path)
        self.path_patch.start()
        # Set TEST_DATABASE_URL to run the same tests against a real PostgreSQL database.
        self.pg_url = os.environ.get("TEST_DATABASE_URL", "")
        self.url_patch = patch.object(accounts, "_database_url", return_value=self.pg_url)
        self.url_patch.start()
        if self.pg_url:
            conn = accounts._connect()
            try:
                conn.execute("DELETE FROM login_attempts")
                conn.execute("DELETE FROM accounts")
                conn.commit()
            finally:
                conn.close()

    def tearDown(self):
        self.url_patch.stop()
        self.path_patch.stop()
        self.temp.cleanup()

    def test_create_and_authenticate_case_insensitive_username(self):
        token = accounts.create_user("Hassan_01", "correct horse battery", "Hassan Bashiru")
        self.assertEqual(accounts.authenticate_user("hassan_01", "correct horse battery"), token)
        self.assertIsNone(accounts.authenticate_user("hassan_01", "wrong password"))
        self.assertEqual(accounts.get_account(token)["account_name"], "Hassan Bashiru")

    def test_duplicate_username_is_rejected(self):
        accounts.create_user("hassan_02", "correct horse battery", "Hassan")
        with self.assertRaisesRegex(ValueError, "already taken"):
            accounts.create_user("HASSAN_02", "another valid password", "Another User")

    def test_invalid_username_password_and_name_are_rejected(self):
        with self.assertRaises(ValueError):
            accounts.create_user("ab", "correct horse battery", "Hassan")
        with self.assertRaises(ValueError):
            accounts.create_user("hassan_03", "short", "Hassan")
        with self.assertRaises(ValueError):
            accounts.create_user("hassan_03", "correct horse battery", "<bad>")

    def test_trial_count_and_unlock_persist_in_database(self):
        token = accounts.create_user("hassan_04", "correct horse battery", "Hassan")
        for _ in range(5):
            accounts.increment_usage(token)
        self.assertTrue(accounts.trial_exceeded(token))
        accounts.unlock_account(token)
        self.assertFalse(accounts.trial_exceeded(token))

    def test_database_mode_matches_configuration(self):
        self.assertEqual(accounts.storage_mode(), "postgresql" if self.pg_url else "sqlite-local")

    def test_lockout_after_repeated_wrong_passwords_and_reset_on_success(self):
        token = accounts.create_user("lock_user", "correct-horse-123", "Lock User")
        for _ in range(accounts.MAX_FAILED_LOGINS - 1):
            self.assertIsNone(accounts.authenticate_user("lock_user", "wrong-password"))
        self.assertEqual(accounts.login_lockout_seconds("lock_user"), 0)
        self.assertEqual(accounts.authenticate_user("lock_user", "correct-horse-123"), token)  # success resets the count
        for _ in range(accounts.MAX_FAILED_LOGINS):
            accounts.authenticate_user("lock_user", "wrong-password")
        self.assertGreater(accounts.login_lockout_seconds("lock_user"), 0)
        self.assertIsNone(accounts.authenticate_user("lock_user", "correct-horse-123"))  # locked: even the right password is refused

    def test_lockout_applies_to_unknown_usernames_too(self):
        for _ in range(accounts.MAX_FAILED_LOGINS):
            accounts.authenticate_user("nobody_here", "whatever-123")
        self.assertGreater(accounts.login_lockout_seconds("nobody_here"), 0)

    def test_lock_expires(self):
        accounts.create_user("expire_user", "correct-horse-123", "Expire User")
        for _ in range(accounts.MAX_FAILED_LOGINS):
            accounts.authenticate_user("expire_user", "wrong-password")
        conn = accounts._connect()
        try:
            accounts._execute(conn, "UPDATE login_attempts SET locked_until = 1 WHERE username = ?", ("expire_user",))
            conn.commit()
        finally:
            conn.close()
        self.assertEqual(accounts.login_lockout_seconds("expire_user"), 0)
        self.assertIsNotNone(accounts.authenticate_user("expire_user", "correct-horse-123"))

    def test_get_account_never_returns_password_material(self):
        token = accounts.create_user("leak_user", "correct-horse-123", "Leak User")
        self.assertFalse({"password_hash", "password_salt"} & set(accounts.get_account(token)))


if __name__ == "__main__":
    unittest.main()
