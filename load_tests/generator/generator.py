import os
import logging
from pathlib import Path

import yaml
from locust import task, tag

from load_tests.base.base_user import BaseUser
from load_tests.utils.data_provider import resolve_value
from load_tests.config.settings import Settings

logger = logging.getLogger(__name__)

# 必要欄位
REQUIRED_API_FIELDS = ["name", "method", "endpoint"]


def load_yaml_file(file_path):
    """載入並解析單一 YAML 檔案"""
    with open(file_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def validate_api_definition(api_def, file_path):
    """驗證 API 定義是否包含必要欄位

    Args:
        api_def: 單一 API 定義 dict
        file_path: 來源檔案路徑 (用於錯誤訊息)

    Raises:
        ValueError: 缺少必要欄位時
    """
    for field in REQUIRED_API_FIELDS:
        if field not in api_def:
            raise ValueError(
                f"API 定義缺少必要欄位 '{field}'，檔案: {file_path}"
            )


def _create_task_func(api_def):
    """為單一 API 定義建立 Locust task 函式

    Args:
        api_def: API 定義 dict，包含 method, endpoint, headers 等

    Returns:
        一個可作為 Locust task 的函式
    """
    api_name = api_def["name"]
    method = api_def["method"].upper()
    endpoint = api_def["endpoint"]
    headers = api_def.get("headers", {})
    body = api_def.get("body")
    params = api_def.get("params")
    assertions = api_def.get("assertions")

    def task_func(self):
        # 每次請求時動態解析變數 (支援隨機值)
        resolved_headers = resolve_value(headers)
        resolved_params = resolve_value(params) if params else None
        resolved_body = resolve_value(body) if body else None

        kwargs = {}
        if resolved_params:
            kwargs["params"] = resolved_params
        if resolved_body:
            kwargs["json"] = resolved_body

        self.make_request(
            method=method,
            endpoint=endpoint,
            name=api_name,
            headers=resolved_headers,
            assertions=assertions,
            **kwargs,
        )

    task_func.__name__ = f"task_{api_name}"
    task_func.__qualname__ = f"task_{api_name}"
    return task_func


def generate_user_class(definition, file_name):
    """從 YAML 定義動態產生一個 Locust HttpUser 子類別

    Args:
        definition: 解析後的 YAML dict
        file_name: YAML 檔名 (用於產生類別名稱)

    Returns:
        動態建立的 HttpUser 子類別
    """
    test_name = definition.get("name", Path(file_name).stem)
    host = definition.get("host", Settings.DEFAULT_HOST)
    apis = definition.get("apis", [])
    wait_time_config = definition.get("wait_time", {"min": 1, "max": 3})

    if not apis:
        logger.warning("定義檔 %s 中沒有 API 定義，跳過", file_name)
        return None

    # 動態建立類別屬性
    class_attrs = {
        "host": host,
        "abstract": False,
    }

    # 為每個 API 建立 task
    for api_def in apis:
        weight = api_def.get("weight", 1)
        task_func = _create_task_func(api_def)
        # 使用 @task(weight) 裝飾器
        decorated = task(weight)(task_func)
        # 若有 tags，加上 @tag
        tags = api_def.get("tags", [])
        if tags:
            decorated = tag(*tags)(decorated)
        class_attrs[task_func.__name__] = decorated

    # 動態建立類別名稱 (將 file_name 轉為 PascalCase)
    class_name = "".join(
        word.capitalize()
        for word in test_name.replace("-", "_").split("_")
    ) + "User"

    # 動態建立 User 類別，繼承 BaseUser
    user_class = type(class_name, (BaseUser,), class_attrs)

    logger.info(
        "已產生測試類別: %s (包含 %d 個 API tasks)", class_name, len(apis)
    )
    return user_class


def load_all_definitions(definitions_dir=None):
    """掃描 api_definitions 目錄，載入所有 YAML 檔案並產生 User 類別

    Args:
        definitions_dir: API 定義檔目錄路徑，預設使用 Settings 中的設定

    Returns:
        list: 動態產生的 User 類別列表
    """
    if definitions_dir is None:
        definitions_dir = Settings.API_DEFINITIONS_DIR

    if not os.path.exists(definitions_dir):
        logger.error("API 定義目錄不存在: %s", definitions_dir)
        return []

    user_classes = []
    yaml_files = sorted(
        f
        for f in os.listdir(definitions_dir)
        if f.endswith((".yaml", ".yml"))
    )

    if not yaml_files:
        logger.warning("API 定義目錄中沒有 YAML 檔案: %s", definitions_dir)
        return []

    for file_name in yaml_files:
        file_path = os.path.join(definitions_dir, file_name)
        try:
            definition = load_yaml_file(file_path)

            # 驗證每個 API 定義
            for api_def in definition.get("apis", []):
                validate_api_definition(api_def, file_path)

            user_class = generate_user_class(definition, file_name)
            if user_class:
                user_classes.append(user_class)
                logger.info("成功載入定義檔: %s", file_name)

        except Exception as e:
            logger.error("載入定義檔 %s 失敗: %s", file_name, e)

    logger.info("共載入 %d 個測試定義", len(user_classes))
    return user_classes
