"""data_provider 模組單元測試"""

import os
import json
import csv
import tempfile
import unittest
from unittest.mock import patch

from load_tests.utils.data_provider import (
    resolve_value,
    load_csv_data,
    load_json_data,
    _extract_json_path,
    _csv_cache,
    _json_cache,
    VARIABLE_GENERATORS,
)


class TestResolveValue(unittest.TestCase):
    """測試 resolve_value 函式"""

    def test_plain_string(self):
        """純文字不應被改變"""
        self.assertEqual(resolve_value("hello world"), "hello world")

    def test_random_name_generates_string(self):
        """${RANDOM_NAME} 應產生非空字串"""
        result = resolve_value("${RANDOM_NAME}")
        self.assertIsInstance(result, str)
        self.assertNotEqual(result, "${RANDOM_NAME}")
        self.assertTrue(len(result) > 0)

    def test_random_email_format(self):
        """${RANDOM_EMAIL} 應產生包含 @ 的字串"""
        result = resolve_value("${RANDOM_EMAIL}")
        self.assertIn("@", result)

    def test_random_uuid_format(self):
        """${RANDOM_UUID} 應產生 UUID 格式"""
        result = resolve_value("${RANDOM_UUID}")
        self.assertEqual(len(result.split("-")), 5)

    def test_timestamp_is_numeric(self):
        """${TIMESTAMP} 應產生數字字串"""
        result = resolve_value("${TIMESTAMP}")
        self.assertTrue(result.isdigit())

    def test_env_variable(self):
        """應能解析環境變數"""
        with patch.dict(os.environ, {"MY_TEST_VAR": "test_value"}):
            result = resolve_value("${MY_TEST_VAR}")
            self.assertEqual(result, "test_value")

    def test_unknown_variable_kept(self):
        """未知的變數應保持原樣"""
        result = resolve_value("${TOTALLY_UNKNOWN_VAR_XYZ}")
        self.assertEqual(result, "${TOTALLY_UNKNOWN_VAR_XYZ}")

    def test_multiple_variables(self):
        """應能解析多個變數"""
        result = resolve_value("name=${RANDOM_NAME}&ts=${TIMESTAMP}")
        self.assertNotIn("${RANDOM_NAME}", result)
        self.assertNotIn("${TIMESTAMP}", result)

    def test_dict_resolve(self):
        """應能遞迴解析 dict"""
        data = {"name": "${RANDOM_NAME}", "count": 5, "nested": {"email": "${RANDOM_EMAIL}"}}
        result = resolve_value(data)
        self.assertNotEqual(result["name"], "${RANDOM_NAME}")
        self.assertEqual(result["count"], 5)
        self.assertIn("@", result["nested"]["email"])

    def test_list_resolve(self):
        """應能遞迴解析 list"""
        data = ["${RANDOM_NAME}", "static", "${RANDOM_INT}"]
        result = resolve_value(data)
        self.assertNotEqual(result[0], "${RANDOM_NAME}")
        self.assertEqual(result[1], "static")

    def test_non_string_passthrough(self):
        """非字串值應原封不動回傳"""
        self.assertEqual(resolve_value(42), 42)
        self.assertEqual(resolve_value(3.14), 3.14)
        self.assertIsNone(resolve_value(None))
        self.assertTrue(resolve_value(True))

    def test_context_variable(self):
        """${CTX:var} 應從 context 解析"""
        ctx = {"user_id": "123", "name": "Alice"}
        result = resolve_value("User ${CTX:user_id} is ${CTX:name}", context=ctx)
        self.assertEqual(result, "User 123 is Alice")

    def test_context_variable_missing(self):
        """缺失的 context 變數應保持原樣"""
        ctx = {"user_id": "123"}
        result = resolve_value("${CTX:missing}", context=ctx)
        self.assertEqual(result, "${CTX:missing}")

    def test_context_fallback_in_regular_pattern(self):
        """${var} 也可以從 context 回退解析"""
        ctx = {"MY_CUSTOM_VAR": "custom_value"}
        result = resolve_value("${MY_CUSTOM_VAR}", context=ctx)
        self.assertEqual(result, "custom_value")


class TestExtractJsonPath(unittest.TestCase):
    """測試 _extract_json_path 函式"""

    def test_simple_path(self):
        data = {"name": "Alice"}
        self.assertEqual(_extract_json_path(data, "name"), "Alice")

    def test_nested_path(self):
        data = {"data": {"user": {"id": 42}}}
        self.assertEqual(_extract_json_path(data, "data.user.id"), 42)

    def test_array_index(self):
        data = {"items": ["a", "b", "c"]}
        self.assertEqual(_extract_json_path(data, "items.1"), "b")

    def test_missing_key(self):
        data = {"name": "Alice"}
        self.assertIsNone(_extract_json_path(data, "missing"))

    def test_deep_missing(self):
        data = {"a": {"b": 1}}
        self.assertIsNone(_extract_json_path(data, "a.c.d"))

    def test_array_out_of_bounds(self):
        data = {"items": [1, 2]}
        self.assertIsNone(_extract_json_path(data, "items.5"))


class TestCsvDataLoading(unittest.TestCase):
    """測試 CSV 資料載入"""

    def setUp(self):
        _csv_cache.clear()
        self.tmpdir = tempfile.mkdtemp()
        self.csv_file = os.path.join(self.tmpdir, "test.csv")
        with open(self.csv_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["name", "email"])
            writer.writerow(["Alice", "alice@test.com"])
            writer.writerow(["Bob", "bob@test.com"])

    @patch("load_tests.utils.data_provider._get_data_dir")
    def test_sequential_read(self, mock_dir):
        mock_dir.return_value = self.tmpdir
        row1 = load_csv_data("test.csv", mode="sequential")
        row2 = load_csv_data("test.csv", mode="sequential")
        self.assertEqual(row1["name"], "Alice")
        self.assertEqual(row2["name"], "Bob")

    @patch("load_tests.utils.data_provider._get_data_dir")
    def test_sequential_wraps_around(self, mock_dir):
        mock_dir.return_value = self.tmpdir
        load_csv_data("test.csv", mode="sequential")  # Alice
        load_csv_data("test.csv", mode="sequential")  # Bob
        row3 = load_csv_data("test.csv", mode="sequential")  # wraps to Alice
        self.assertEqual(row3["name"], "Alice")

    @patch("load_tests.utils.data_provider._get_data_dir")
    def test_random_read(self, mock_dir):
        mock_dir.return_value = self.tmpdir
        row = load_csv_data("test.csv", mode="random")
        self.assertIn(row["name"], ["Alice", "Bob"])

    @patch("load_tests.utils.data_provider._get_data_dir")
    def test_missing_file(self, mock_dir):
        mock_dir.return_value = self.tmpdir
        result = load_csv_data("nonexistent.csv")
        self.assertEqual(result, {})


class TestJsonDataLoading(unittest.TestCase):
    """測試 JSON 資料載入"""

    def setUp(self):
        _json_cache.clear()
        self.tmpdir = tempfile.mkdtemp()
        self.json_file = os.path.join(self.tmpdir, "test.json")
        data = {"users": [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]}
        with open(self.json_file, "w", encoding="utf-8") as f:
            json.dump(data, f)

    @patch("load_tests.utils.data_provider._get_data_dir")
    def test_load_json(self, mock_dir):
        mock_dir.return_value = self.tmpdir
        data = load_json_data("test.json")
        self.assertIsNotNone(data)
        self.assertEqual(len(data["users"]), 2)

    @patch("load_tests.utils.data_provider._get_data_dir")
    def test_missing_json(self, mock_dir):
        mock_dir.return_value = self.tmpdir
        data = load_json_data("nonexistent.json")
        self.assertIsNone(data)


class TestAllGenerators(unittest.TestCase):
    """測試所有內建變數產生器"""

    def test_all_generators_callable(self):
        for name, gen in VARIABLE_GENERATORS.items():
            result = gen()
            self.assertIsNotNone(result, f"{name} 產生了 None")


if __name__ == "__main__":
    unittest.main()
