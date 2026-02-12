"""環境 Profile 管理

支援多環境設定切換 (dev / staging / prod)

使用方式:
    # 透過環境變數指定 profile
    LOCUST_PROFILE=staging locust -f load_tests/locustfile.py

    # profile 檔案放在 load_tests/profiles/ 目錄下
    # 檔名格式: {profile_name}.yaml
"""

import os
import logging
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

# Profile 目錄
PROFILES_DIR = os.path.dirname(os.path.abspath(__file__))


def load_profile(profile_name=None):
    """載入指定的環境 profile

    Args:
        profile_name: profile 名稱 (不含副檔名)
                      預設從 LOCUST_PROFILE 環境變數讀取

    Returns:
        dict: profile 設定值，若無指定或找不到則回傳空 dict
    """
    if profile_name is None:
        profile_name = os.getenv("LOCUST_PROFILE")

    if not profile_name:
        return {}

    # 搜尋 profile 檔案
    for ext in (".yaml", ".yml"):
        file_path = os.path.join(PROFILES_DIR, f"{profile_name}{ext}")
        if os.path.exists(file_path):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    config = yaml.safe_load(f) or {}
                logger.info("已載入環境 profile: %s", profile_name)
                return config
            except Exception as e:
                logger.error("載入 profile '%s' 失敗: %s", profile_name, e)
                return {}

    logger.warning("找不到 profile '%s'，使用預設設定", profile_name)
    return {}


def apply_profile(settings_class, profile):
    """將 profile 設定套用到 Settings 類別

    Args:
        settings_class: Settings 類別
        profile: profile dict
    """
    if not profile:
        return

    mapping = {
        "host": "DEFAULT_HOST",
        "users": "DEFAULT_USERS",
        "spawn_rate": "DEFAULT_SPAWN_RATE",
        "run_time": "DEFAULT_RUN_TIME",
        "request_timeout": "REQUEST_TIMEOUT",
        "enable_assertions": "ENABLE_ASSERTIONS",
    }

    for yaml_key, attr_name in mapping.items():
        if yaml_key in profile:
            setattr(settings_class, attr_name, profile[yaml_key])
            logger.info("Profile 覆寫: %s = %s", attr_name, profile[yaml_key])

    # 合併 headers
    if "headers" in profile:
        settings_class.DEFAULT_HEADERS.update(profile["headers"])

    # 設定環境變數 (讓其他模組也能讀取)
    env_vars = profile.get("env", {})
    for key, value in env_vars.items():
        os.environ.setdefault(key, str(value))
        logger.info("Profile 設定環境變數: %s", key)
