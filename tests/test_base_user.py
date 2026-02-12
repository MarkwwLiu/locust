"""base_user 模組單元測試"""

import unittest

from load_tests.base.base_user import BaseUser


class TestExtractJsonValue(unittest.TestCase):
    """測試 _extract_json_value 靜態方法"""

    def test_simple_key(self):
        data = {"token": "abc123"}
        self.assertEqual(BaseUser._extract_json_value(data, "token"), "abc123")

    def test_nested_key(self):
        data = {"data": {"access_token": "xyz"}}
        self.assertEqual(
            BaseUser._extract_json_value(data, "data.access_token"), "xyz"
        )

    def test_deep_nested(self):
        data = {"a": {"b": {"c": {"d": "deep"}}}}
        self.assertEqual(BaseUser._extract_json_value(data, "a.b.c.d"), "deep")

    def test_array_index(self):
        data = {"items": [{"id": 1}, {"id": 2}, {"id": 3}]}
        self.assertEqual(BaseUser._extract_json_value(data, "items.1.id"), 2)

    def test_missing_key_returns_none(self):
        data = {"token": "abc"}
        self.assertIsNone(BaseUser._extract_json_value(data, "missing"))

    def test_missing_nested_returns_none(self):
        data = {"a": {"b": 1}}
        self.assertIsNone(BaseUser._extract_json_value(data, "a.c.d"))

    def test_empty_data(self):
        self.assertIsNone(BaseUser._extract_json_value({}, "key"))

    def test_numeric_value(self):
        data = {"count": 42}
        self.assertEqual(BaseUser._extract_json_value(data, "count"), 42)

    def test_boolean_value(self):
        data = {"active": True}
        self.assertTrue(BaseUser._extract_json_value(data, "active"))


if __name__ == "__main__":
    unittest.main()
