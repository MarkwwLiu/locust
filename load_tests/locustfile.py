"""Locust 壓力測試主入口

使用方式:
    # 啟動 Web UI 模式
    locust -f load_tests/locustfile.py

    # 指定目標主機
    locust -f load_tests/locustfile.py --host https://api.example.com

    # 無頭模式 (headless)
    locust -f load_tests/locustfile.py --headless -u 100 -r 10 -t 60s

    # 只執行特定 tag 的測試
    locust -f load_tests/locustfile.py --tags smoke

    # 指定自訂 API 定義目錄
    LOCUST_API_DIR=/path/to/definitions locust -f load_tests/locustfile.py
"""

import os
import sys
import logging

# 將專案根目錄加入 Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from load_tests.generator.generator import load_all_definitions

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)

# 支援透過環境變數指定自訂定義目錄
custom_dir = os.getenv("LOCUST_API_DIR")

# 載入所有 API 定義並產生 User 類別
user_classes = load_all_definitions(definitions_dir=custom_dir)

# 將動態產生的類別註冊到模組層級，讓 Locust 能偵測到
for cls in user_classes:
    globals()[cls.__name__] = cls

if not user_classes:
    logger.warning(
        "未找到任何 API 定義，請在 api_definitions/ 目錄中新增 YAML 檔案"
    )
