import os


class Settings:
    """壓力測試全域設定"""

    # 預設目標主機
    DEFAULT_HOST = os.getenv("LOCUST_HOST", "https://api.example.com")

    # 預設使用者數量
    DEFAULT_USERS = int(os.getenv("LOCUST_USERS", "10"))

    # 每秒產生使用者速率
    DEFAULT_SPAWN_RATE = int(os.getenv("LOCUST_SPAWN_RATE", "1"))

    # 測試執行時間 (秒)，0 表示無限
    DEFAULT_RUN_TIME = os.getenv("LOCUST_RUN_TIME", "0")

    # API 定義檔目錄路徑
    API_DEFINITIONS_DIR = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "api_definitions",
    )

    # 請求逾時時間 (秒)
    REQUEST_TIMEOUT = int(os.getenv("LOCUST_REQUEST_TIMEOUT", "30"))

    # 預設 headers
    DEFAULT_HEADERS = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    # 是否啟用回應驗證
    ENABLE_ASSERTIONS = os.getenv("LOCUST_ENABLE_ASSERTIONS", "true").lower() == "true"
