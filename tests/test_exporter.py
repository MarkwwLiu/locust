"""exporter 模組單元測試"""

import os
import py_compile
import tempfile
import unittest

import yaml

from load_tests.exporter.exporter import (
    export_yaml,
    _scan_yaml_text,
    _scan_definition,
)


class TestScanYamlText(unittest.TestCase):
    """測試 YAML 文字功能偵測"""

    def test_detect_random(self):
        result = _scan_yaml_text('name: "${RANDOM_NAME}"')
        self.assertTrue(result["has_random"])

    def test_detect_timestamp(self):
        result = _scan_yaml_text('ts: "${TIMESTAMP}"')
        self.assertTrue(result["has_random"])

    def test_detect_ctx(self):
        result = _scan_yaml_text('endpoint: "/users/${CTX:user_id}"')
        self.assertTrue(result["has_ctx"])

    def test_detect_csv(self):
        result = _scan_yaml_text('username: "${CSV:users.csv:username}"')
        self.assertTrue(result["has_csv"])
        self.assertIn("users.csv", result["csv_files"])

    def test_detect_json(self):
        result = _scan_yaml_text('id: "${JSON:data.json:items.0.id}"')
        self.assertTrue(result["has_json"])
        self.assertIn("data.json", result["json_files"])

    def test_no_features(self):
        result = _scan_yaml_text('name: "simple_test"\nmethod: "GET"')
        self.assertFalse(result["has_random"])
        self.assertFalse(result["has_ctx"])
        self.assertFalse(result["has_csv"])
        self.assertFalse(result["has_json"])


class TestScanDefinition(unittest.TestCase):
    """測試 YAML 結構功能偵測"""

    def test_detect_auth(self):
        definition = {"auth": {"type": "bearer"}, "apis": []}
        result = _scan_definition(definition)
        self.assertTrue(result["has_auth"])

    def test_detect_retry(self):
        definition = {"retry": {"max_retries": 3}, "apis": []}
        result = _scan_definition(definition)
        self.assertTrue(result["has_retry"])

    def test_detect_flows(self):
        definition = {"flows": [{"name": "f", "steps": []}], "apis": []}
        result = _scan_definition(definition)
        self.assertTrue(result["has_flows"])

    def test_detect_extract_in_api(self):
        definition = {"apis": [{"extract": {"user_id": "data.id"}}]}
        result = _scan_definition(definition)
        self.assertTrue(result["has_extract"])

    def test_detect_extract_in_flow(self):
        definition = {
            "apis": [],
            "flows": [{"name": "f", "steps": [{"extract": {"id": "data.id"}}]}],
        }
        result = _scan_definition(definition)
        self.assertTrue(result["has_extract"])

    def test_no_features(self):
        definition = {"apis": [{"name": "t", "method": "GET", "endpoint": "/"}]}
        result = _scan_definition(definition)
        self.assertFalse(result["has_auth"])
        self.assertFalse(result["has_retry"])
        self.assertFalse(result["has_flows"])


class TestExportYaml(unittest.TestCase):
    """測試完整匯出功能"""

    def _export_and_check(self, definition):
        """輔助方法: 寫 YAML、匯出、驗證語法"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            yaml.dump(definition, f)
            yaml_path = f.name

        output_path = yaml_path.replace(".yaml", "_standalone.py")
        try:
            result = export_yaml(yaml_path, output_path)
            self.assertTrue(os.path.exists(result))
            # 驗證 Python 語法
            py_compile.compile(result, doraise=True)
            return result
        finally:
            os.unlink(yaml_path)
            if os.path.exists(output_path):
                os.unlink(output_path)

    def test_simple_api(self):
        definition = {
            "name": "simple_test",
            "host": "https://example.com",
            "apis": [
                {"name": "get_test", "method": "GET", "endpoint": "/test"},
            ],
        }
        self._export_and_check(definition)

    def test_with_auth(self):
        definition = {
            "name": "auth_test",
            "host": "https://example.com",
            "auth": {
                "type": "bearer",
                "login": {
                    "method": "POST",
                    "endpoint": "/login",
                    "body": {"user": "test"},
                    "token_path": "token",
                },
            },
            "apis": [
                {"name": "protected", "method": "GET", "endpoint": "/api/data"},
            ],
        }
        self._export_and_check(definition)

    def test_with_retry(self):
        definition = {
            "name": "retry_test",
            "host": "https://example.com",
            "retry": {"max_retries": 3, "wait_seconds": 1, "on_status": [503]},
            "apis": [
                {"name": "flaky", "method": "GET", "endpoint": "/flaky"},
            ],
        }
        self._export_and_check(definition)

    def test_with_flows(self):
        definition = {
            "name": "flow_test",
            "host": "https://example.com",
            "flows": [
                {
                    "name": "create_read",
                    "steps": [
                        {
                            "name": "create",
                            "method": "POST",
                            "endpoint": "/items",
                            "body": {"name": "test"},
                            "extract": {"item_id": "data.id"},
                        },
                        {
                            "name": "read",
                            "method": "GET",
                            "endpoint": "/items/123",
                        },
                    ],
                },
            ],
        }
        self._export_and_check(definition)

    def test_constant_pacing(self):
        definition = {
            "name": "pacing_test",
            "host": "https://example.com",
            "wait_time": {"mode": "constant_pacing", "value": 5},
            "apis": [
                {"name": "t", "method": "GET", "endpoint": "/"},
            ],
        }
        self._export_and_check(definition)

    def test_mixed_apis_and_flows(self):
        definition = {
            "name": "mixed_test",
            "host": "https://example.com",
            "auth": {"type": "api_key", "header_name": "X-Key", "key": "abc"},
            "retry": {"max_retries": 2, "wait_seconds": 1, "on_status": [502]},
            "wait_time": {"mode": "constant", "value": 2},
            "apis": [
                {
                    "name": "health",
                    "method": "GET",
                    "endpoint": "/health",
                    "tags": ["smoke"],
                    "weight": 5,
                    "assertions": {"status_code": 200},
                },
            ],
            "flows": [
                {
                    "name": "crud",
                    "weight": 3,
                    "tags": ["crud"],
                    "steps": [
                        {"name": "create", "method": "POST", "endpoint": "/items"},
                        {"name": "read", "method": "GET", "endpoint": "/items/1"},
                    ],
                },
            ],
        }
        self._export_and_check(definition)

    def test_nonexistent_yaml(self):
        with self.assertRaises(FileNotFoundError):
            export_yaml("/nonexistent/file.yaml")

    def test_default_output_path(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            yaml.dump(
                {"name": "test", "apis": [{"name": "t", "method": "GET", "endpoint": "/"}]},
                f,
            )
            yaml_path = f.name

        expected_output = yaml_path.replace(".yaml", "_standalone.py")
        try:
            result = export_yaml(yaml_path)
            self.assertEqual(result, expected_output)
            self.assertTrue(os.path.exists(result))
        finally:
            os.unlink(yaml_path)
            if os.path.exists(expected_output):
                os.unlink(expected_output)


if __name__ == "__main__":
    unittest.main()
