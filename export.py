#!/usr/bin/env python3
"""拋棄式腳本匯出工具

將指定的 YAML 測試定義匯出為完全獨立的 Locust 腳本，
不依賴框架中的任何模組，可直接複製到任何地方執行。

用法:
    python export.py <yaml_file> [-o output.py]

範例:
    # 匯出 flow_example.yaml (輸出到同目錄)
    python export.py load_tests/api_definitions/flow_example.yaml

    # 匯出到指定路徑
    python export.py load_tests/api_definitions/flow_example.yaml -o /tmp/my_test.py

    # 匯出後直接執行
    python export.py load_tests/api_definitions/flow_example.yaml -o /tmp/my_test.py
    locust -f /tmp/my_test.py --headless -u 10 -r 2 -t 30s
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from load_tests.exporter.exporter import main

if __name__ == "__main__":
    main()
