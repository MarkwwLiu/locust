"""profile_loader 模組單元測試"""

import os
import tempfile
import unittest
from unittest.mock import patch

import yaml

from load_tests.profiles.profile_loader import load_profile, apply_profile
from load_tests.config.settings import Settings


class TestLoadProfile(unittest.TestCase):
    """測試 profile 載入"""

    def test_no_profile_returns_empty(self):
        with patch.dict(os.environ, {}, clear=True):
            result = load_profile(None)
            self.assertEqual(result, {})

    def test_load_existing_profile(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = {"host": "https://test.example.com", "users": 50}
            with open(os.path.join(tmpdir, "test.yaml"), "w") as f:
                yaml.dump(config, f)

            with patch(
                "load_tests.profiles.profile_loader.PROFILES_DIR", tmpdir
            ):
                result = load_profile("test")
                self.assertEqual(result["host"], "https://test.example.com")
                self.assertEqual(result["users"], 50)

    def test_missing_profile_returns_empty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch(
                "load_tests.profiles.profile_loader.PROFILES_DIR", tmpdir
            ):
                result = load_profile("nonexistent")
                self.assertEqual(result, {})

    def test_env_var_profile(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = {"host": "https://env-test.com"}
            with open(os.path.join(tmpdir, "from_env.yaml"), "w") as f:
                yaml.dump(config, f)

            with patch(
                "load_tests.profiles.profile_loader.PROFILES_DIR", tmpdir
            ), patch.dict(os.environ, {"LOCUST_PROFILE": "from_env"}):
                result = load_profile()
                self.assertEqual(result["host"], "https://env-test.com")


class TestApplyProfile(unittest.TestCase):
    """測試 profile 套用"""

    def setUp(self):
        self._original_host = Settings.DEFAULT_HOST
        self._original_users = Settings.DEFAULT_USERS
        self._original_headers = Settings.DEFAULT_HEADERS.copy()

    def tearDown(self):
        Settings.DEFAULT_HOST = self._original_host
        Settings.DEFAULT_USERS = self._original_users
        Settings.DEFAULT_HEADERS = self._original_headers

    def test_apply_empty_profile(self):
        apply_profile(Settings, {})
        self.assertEqual(Settings.DEFAULT_HOST, self._original_host)

    def test_apply_host(self):
        apply_profile(Settings, {"host": "https://new.example.com"})
        self.assertEqual(Settings.DEFAULT_HOST, "https://new.example.com")

    def test_apply_users(self):
        apply_profile(Settings, {"users": 99})
        self.assertEqual(Settings.DEFAULT_USERS, 99)

    def test_apply_headers(self):
        apply_profile(Settings, {"headers": {"X-Custom": "value"}})
        self.assertIn("X-Custom", Settings.DEFAULT_HEADERS)
        self.assertEqual(Settings.DEFAULT_HEADERS["X-Custom"], "value")

    def test_apply_env_vars(self):
        apply_profile(Settings, {"env": {"TEST_VAR_12345": "hello"}})
        self.assertEqual(os.environ.get("TEST_VAR_12345"), "hello")
        os.environ.pop("TEST_VAR_12345", None)


if __name__ == "__main__":
    unittest.main()
