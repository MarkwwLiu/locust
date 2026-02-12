import os
import logging
from pathlib import Path

import yaml
from locust import task, tag, between, constant, constant_pacing

from load_tests.base.base_user import BaseUser
from load_tests.utils.data_provider import resolve_value
from load_tests.config.settings import Settings

logger = logging.getLogger(__name__)

# 必要欄位
REQUIRED_API_FIELDS = ["name", "method", "endpoint"]

# 支援的 wait_time 模式
WAIT_TIME_MODES = {
    "between": lambda cfg: between(cfg.get("min", 1), cfg.get("max", 3)),
    "constant": lambda cfg: constant(cfg.get("value", 1)),
    "constant_pacing": lambda cfg: constant_pacing(cfg.get("value", 1)),
}


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
    extract = api_def.get("extract")
    retry = api_def.get("retry")

    def task_func(self):
        # 每次請求時動態解析變數 (支援隨機值 + context 變數)
        ctx = getattr(self, "context", {})
        resolved_endpoint = resolve_value(endpoint, ctx)
        resolved_headers = resolve_value(headers, ctx)
        resolved_params = resolve_value(params, ctx) if params else None
        resolved_body = resolve_value(body, ctx) if body else None

        kwargs = {}
        if resolved_params:
            kwargs["params"] = resolved_params
        if resolved_body:
            kwargs["json"] = resolved_body
        if extract:
            kwargs["extract"] = extract
        if retry:
            kwargs["retry"] = retry

        self.make_request(
            method=method,
            endpoint=resolved_endpoint,
            name=api_name,
            headers=resolved_headers,
            assertions=assertions,
            **kwargs,
        )

    task_func.__name__ = f"task_{api_name}"
    task_func.__qualname__ = f"task_{api_name}"
    return task_func


def _create_flow_task(flow_def):
    """為 flow (請求鏈) 建立一個循序執行的 Locust task

    flow 中的 API 按順序執行，前一個的 extract 值可供後續使用。

    Args:
        flow_def: flow 定義 dict，包含 name, steps 等

    Returns:
        一個可作為 Locust task 的函式
    """
    flow_name = flow_def["name"]
    steps = flow_def.get("steps", [])

    def flow_task_func(self):
        ctx = getattr(self, "context", {})
        for step in steps:
            step_method = step["method"].upper()
            step_endpoint = step["endpoint"]
            step_headers = step.get("headers", {})
            step_body = step.get("body")
            step_params = step.get("params")
            step_assertions = step.get("assertions")
            step_extract = step.get("extract")
            step_retry = step.get("retry")
            step_name = step.get("name", f"{flow_name}/{step_endpoint}")

            resolved_endpoint = resolve_value(step_endpoint, ctx)
            resolved_headers = resolve_value(step_headers, ctx)
            resolved_params = resolve_value(step_params, ctx) if step_params else None
            resolved_body = resolve_value(step_body, ctx) if step_body else None

            kwargs = {}
            if resolved_params:
                kwargs["params"] = resolved_params
            if resolved_body:
                kwargs["json"] = resolved_body
            if step_extract:
                kwargs["extract"] = step_extract
            if step_retry:
                kwargs["retry"] = step_retry

            self.make_request(
                method=step_method,
                endpoint=resolved_endpoint,
                name=step_name,
                headers=resolved_headers,
                assertions=step_assertions,
                **kwargs,
            )

    flow_task_func.__name__ = f"flow_{flow_name}"
    flow_task_func.__qualname__ = f"flow_{flow_name}"
    return flow_task_func


def _parse_wait_time(config):
    """解析 wait_time 設定

    支援:
        - {"mode": "between", "min": 1, "max": 3}  (預設)
        - {"mode": "constant", "value": 2}
        - {"mode": "constant_pacing", "value": 5}
        - {"min": 1, "max": 3}  (向後相容)
    """
    if not config:
        return between(1, 3)

    mode = config.get("mode", "between")
    factory = WAIT_TIME_MODES.get(mode)
    if factory:
        return factory(config)

    logger.warning("不支援的 wait_time 模式: %s，使用預設 between(1, 3)", mode)
    return between(1, 3)


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
    flows = definition.get("flows", [])
    wait_time_config = definition.get("wait_time", {"min": 1, "max": 3})
    auth_config = definition.get("auth")
    retry_config = definition.get("retry")

    if not apis and not flows:
        logger.warning("定義檔 %s 中沒有 API 或 flow 定義，跳過", file_name)
        return None

    # 動態建立類別屬性
    class_attrs = {
        "host": host,
        "abstract": False,
        "wait_time": _parse_wait_time(wait_time_config),
        "auth_config": auth_config,
        "retry_config": retry_config,
    }

    # 為每個 API 建立 task
    for api_def in apis:
        weight = api_def.get("weight", 1)
        task_func = _create_task_func(api_def)
        decorated = task(weight)(task_func)
        tags_list = api_def.get("tags", [])
        if tags_list:
            decorated = tag(*tags_list)(decorated)
        class_attrs[task_func.__name__] = decorated

    # 為每個 flow 建立 task
    for flow_def in flows:
        weight = flow_def.get("weight", 1)
        flow_func = _create_flow_task(flow_def)
        decorated = task(weight)(flow_func)
        tags_list = flow_def.get("tags", [])
        if tags_list:
            decorated = tag(*tags_list)(decorated)
        class_attrs[flow_func.__name__] = decorated

    # 動態建立類別名稱 (將 file_name 轉為 PascalCase)
    class_name = "".join(
        word.capitalize()
        for word in test_name.replace("-", "_").split("_")
    ) + "User"

    # 動態建立 User 類別，繼承 BaseUser
    user_class = type(class_name, (BaseUser,), class_attrs)

    total_tasks = len(apis) + len(flows)
    logger.info(
        "已產生測試類別: %s (包含 %d 個 tasks)", class_name, total_tasks
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

            # 驗證每個 flow 中的 step
            for flow_def in definition.get("flows", []):
                if "name" not in flow_def:
                    raise ValueError(
                        f"Flow 定義缺少 'name' 欄位，檔案: {file_path}"
                    )
                for step in flow_def.get("steps", []):
                    validate_api_definition(step, file_path)

            user_class = generate_user_class(definition, file_name)
            if user_class:
                user_classes.append(user_class)
                logger.info("成功載入定義檔: %s", file_name)

        except Exception as e:
            logger.error("載入定義檔 %s 失敗: %s", file_name, e)

    logger.info("共載入 %d 個測試定義", len(user_classes))
    return user_classes
