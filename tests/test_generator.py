"""generator 模組單元測試"""

import os
import tempfile
import unittest

import yaml
from locust import between, constant, constant_pacing

from load_tests.generator.generator import (
    load_yaml_file,
    validate_api_definition,
    generate_user_class,
    load_all_definitions,
    _parse_wait_time,
    _create_task_func,
    _create_flow_task,
)


class TestLoadYaml(unittest.TestCase):
    """測試 YAML 載入"""

    def test_load_valid_yaml(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump({"name": "test", "apis": []}, f)
            f.flush()
            result = load_yaml_file(f.name)
        self.assertEqual(result["name"], "test")
        os.unlink(f.name)

    def test_load_invalid_yaml_raises(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("{{invalid yaml")
            f.flush()
        with self.assertRaises(Exception):
            load_yaml_file(f.name)
        os.unlink(f.name)


class TestValidateApiDefinition(unittest.TestCase):
    """測試 API 定義驗證"""

    def test_valid_definition(self):
        api_def = {"name": "test", "method": "GET", "endpoint": "/test"}
        validate_api_definition(api_def, "test.yaml")  # 不應拋例外

    def test_missing_name(self):
        api_def = {"method": "GET", "endpoint": "/test"}
        with self.assertRaises(ValueError):
            validate_api_definition(api_def, "test.yaml")

    def test_missing_method(self):
        api_def = {"name": "test", "endpoint": "/test"}
        with self.assertRaises(ValueError):
            validate_api_definition(api_def, "test.yaml")

    def test_missing_endpoint(self):
        api_def = {"name": "test", "method": "GET"}
        with self.assertRaises(ValueError):
            validate_api_definition(api_def, "test.yaml")


class TestParseWaitTime(unittest.TestCase):
    """測試 wait_time 解析"""

    def test_default_between(self):
        result = _parse_wait_time(None)
        self.assertIsNotNone(result)

    def test_between_mode(self):
        config = {"mode": "between", "min": 2, "max": 5}
        result = _parse_wait_time(config)
        self.assertIsNotNone(result)

    def test_constant_mode(self):
        config = {"mode": "constant", "value": 3}
        result = _parse_wait_time(config)
        self.assertIsNotNone(result)

    def test_constant_pacing_mode(self):
        config = {"mode": "constant_pacing", "value": 5}
        result = _parse_wait_time(config)
        self.assertIsNotNone(result)

    def test_backward_compatible(self):
        """向後相容: 只有 min/max 沒有 mode"""
        config = {"min": 1, "max": 3}
        result = _parse_wait_time(config)
        self.assertIsNotNone(result)

    def test_unknown_mode_fallback(self):
        config = {"mode": "unknown_mode"}
        result = _parse_wait_time(config)
        self.assertIsNotNone(result)


class TestGenerateUserClass(unittest.TestCase):
    """測試動態 User 類別產生"""

    def test_basic_generation(self):
        definition = {
            "name": "test_api",
            "host": "https://example.com",
            "apis": [
                {"name": "get_test", "method": "GET", "endpoint": "/test"},
            ],
        }
        cls = generate_user_class(definition, "test_api.yaml")
        self.assertIsNotNone(cls)
        self.assertEqual(cls.__name__, "TestApiUser")
        self.assertEqual(cls.host, "https://example.com")

    def test_class_name_pascal_case(self):
        definition = {
            "name": "my_cool_api",
            "apis": [
                {"name": "t", "method": "GET", "endpoint": "/"},
            ],
        }
        cls = generate_user_class(definition, "my_cool_api.yaml")
        self.assertEqual(cls.__name__, "MyCoolApiUser")

    def test_empty_apis_returns_none(self):
        definition = {"name": "empty", "apis": []}
        cls = generate_user_class(definition, "empty.yaml")
        self.assertIsNone(cls)

    def test_with_auth_config(self):
        definition = {
            "name": "auth_test",
            "apis": [
                {"name": "t", "method": "GET", "endpoint": "/"},
            ],
            "auth": {"type": "api_key", "header_name": "X-Key", "key": "abc"},
        }
        cls = generate_user_class(definition, "auth.yaml")
        self.assertIsNotNone(cls)
        self.assertEqual(cls.auth_config["type"], "api_key")

    def test_with_retry_config(self):
        definition = {
            "name": "retry_test",
            "apis": [
                {"name": "t", "method": "GET", "endpoint": "/"},
            ],
            "retry": {"max_retries": 3, "wait_seconds": 2, "on_status": [503]},
        }
        cls = generate_user_class(definition, "retry.yaml")
        self.assertIsNotNone(cls)
        self.assertEqual(cls.retry_config["max_retries"], 3)

    def test_with_flows(self):
        definition = {
            "name": "flow_test",
            "flows": [
                {
                    "name": "my_flow",
                    "steps": [
                        {"name": "s1", "method": "POST", "endpoint": "/create"},
                        {"name": "s2", "method": "GET", "endpoint": "/read"},
                    ],
                },
            ],
        }
        cls = generate_user_class(definition, "flow.yaml")
        self.assertIsNotNone(cls)
        self.assertTrue(hasattr(cls, "flow_my_flow"))

    def test_mixed_apis_and_flows(self):
        definition = {
            "name": "mixed",
            "apis": [
                {"name": "standalone", "method": "GET", "endpoint": "/test"},
            ],
            "flows": [
                {
                    "name": "chain",
                    "steps": [
                        {"name": "s1", "method": "GET", "endpoint": "/a"},
                    ],
                },
            ],
        }
        cls = generate_user_class(definition, "mixed.yaml")
        self.assertIsNotNone(cls)
        self.assertTrue(hasattr(cls, "task_standalone"))
        self.assertTrue(hasattr(cls, "flow_chain"))


class TestLoadAllDefinitions(unittest.TestCase):
    """測試批次載入所有定義"""

    def test_nonexistent_dir(self):
        result = load_all_definitions("/nonexistent/dir")
        self.assertEqual(result, [])

    def test_empty_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = load_all_definitions(tmpdir)
            self.assertEqual(result, [])

    def test_load_valid_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            data = {
                "name": "test_def",
                "apis": [
                    {"name": "test_get", "method": "GET", "endpoint": "/test"},
                ],
            }
            file_path = os.path.join(tmpdir, "test.yaml")
            with open(file_path, "w") as f:
                yaml.dump(data, f)

            result = load_all_definitions(tmpdir)
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0].__name__, "TestDefUser")

    def test_skip_invalid_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # 一個有效、一個無效
            valid = {"name": "valid", "apis": [{"name": "t", "method": "GET", "endpoint": "/"}]}
            invalid = {"name": "invalid", "apis": [{"method": "GET"}]}  # 缺 name 和 endpoint

            with open(os.path.join(tmpdir, "01_valid.yaml"), "w") as f:
                yaml.dump(valid, f)
            with open(os.path.join(tmpdir, "02_invalid.yaml"), "w") as f:
                yaml.dump(invalid, f)

            result = load_all_definitions(tmpdir)
            self.assertEqual(len(result), 1)


if __name__ == "__main__":
    unittest.main()
