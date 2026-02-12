"""拋棄式腳本匯出器

將指定的 YAML 測試定義匯出為完全獨立、自包含的 Python 腳本。
匯出的腳本不依賴本框架的任何模組，可直接複製到任何地方執行:
    locust -f exported_script.py

用法:
    python -m load_tests.exporter.exporter <yaml_file> [-o output.py]
    python export.py <yaml_file> [-o output.py]
"""

import os
import re
import csv
import json
import logging
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

# 偵測 YAML 中使用的特殊變數模式
_CTX_PATTERN = re.compile(r"\$\{CTX:\w+\}")
_CSV_PATTERN = re.compile(r"\$\{CSV:([^:}]+):([^}]+)\}")
_JSON_PATTERN = re.compile(r"\$\{JSON:([^:}]+):([^}]+)\}")
_RANDOM_PATTERN = re.compile(r"\$\{(RANDOM_\w+|TIMESTAMP)\}")


def _W(lines, indent, *texts):
    """寫入多行程式碼，自動加上縮排

    Args:
        lines: 輸出行列表
        indent: 縮排層數 (每層 4 空格)
        *texts: 要加入的行 (可傳多行)
    """
    prefix = "    " * indent
    for text in texts:
        if text == "":
            lines.append("")
        else:
            lines.append(prefix + text)


def _scan_yaml_text(yaml_text):
    """掃描 YAML 原始文字，偵測用到哪些功能"""
    return {
        "has_ctx": bool(_CTX_PATTERN.search(yaml_text)),
        "has_csv": bool(_CSV_PATTERN.search(yaml_text)),
        "has_json": bool(_JSON_PATTERN.search(yaml_text)),
        "has_random": bool(_RANDOM_PATTERN.search(yaml_text)),
        "csv_files": set(m.group(1) for m in _CSV_PATTERN.finditer(yaml_text)),
        "json_files": set(m.group(1) for m in _JSON_PATTERN.finditer(yaml_text)),
    }


def _scan_definition(definition):
    """掃描解析後的 YAML dict，偵測用到哪些功能"""
    features = {
        "has_auth": "auth" in definition and definition["auth"] is not None,
        "has_retry": "retry" in definition and definition["retry"] is not None,
        "has_flows": bool(definition.get("flows")),
        "has_apis": bool(definition.get("apis")),
        "has_extract": False,
    }

    for api in definition.get("apis", []):
        if api.get("extract"):
            features["has_extract"] = True
        if api.get("retry"):
            features["has_retry"] = True

    for flow in definition.get("flows", []):
        for step in flow.get("steps", []):
            if step.get("extract"):
                features["has_extract"] = True
            if step.get("retry"):
                features["has_retry"] = True

    return features


def _load_data_dir():
    """取得 data/ 目錄路徑"""
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "data",
    )


def _read_csv_file(file_name):
    """讀取 CSV 檔案並回傳 list of dicts"""
    file_path = os.path.join(_load_data_dir(), file_name)
    if not os.path.exists(file_path):
        logger.warning("CSV 檔案不存在: %s", file_path)
        return []
    with open(file_path, "r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _read_json_file(file_name):
    """讀取 JSON 檔案"""
    file_path = os.path.join(_load_data_dir(), file_name)
    if not os.path.exists(file_path):
        logger.warning("JSON 檔案不存在: %s", file_path)
        return None
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _gen_imports(features, text_features):
    """產生 import 區塊"""
    L = []
    _W(L, 0, '"""自動匯出的獨立壓力測試腳本')
    _W(L, 0, "")
    _W(L, 0, "此檔案由 Locust 壓力測試框架的 Exporter 自動產生。")
    _W(L, 0, "完全獨立，不依賴框架的任何模組。")
    _W(L, 0, "")
    _W(L, 0, "使用方式:")
    _W(L, 0, "    locust -f <this_file>.py")
    _W(L, 0, "    locust -f <this_file>.py --headless -u 10 -r 2 -t 60s")
    _W(L, 0, '"""')
    _W(L, 0, "")
    _W(L, 0, "import os")
    _W(L, 0, "import re")
    _W(L, 0, "import logging")
    _W(L, 0, "import time")

    if text_features["has_random"]:
        _W(L, 0, "import uuid")
        _W(L, 0, "import random")
        _W(L, 0, "import string")

    if text_features["has_csv"]:
        _W(L, 0, "import csv")
    if text_features["has_json"] or text_features["has_csv"]:
        _W(L, 0, "import json")

    _W(L, 0, "")

    if text_features["has_random"]:
        _W(L, 0, "from faker import Faker")

    wait_mode = features.get("_wait_mode", "between")
    locust_imports = ["HttpUser", "task", "tag"]
    if wait_mode == "between":
        locust_imports.append("between")
    elif wait_mode == "constant":
        locust_imports.append("constant")
    elif wait_mode == "constant_pacing":
        locust_imports.append("constant_pacing")

    _W(L, 0, f"from locust import {', '.join(locust_imports)}")

    return "\n".join(L)


def _gen_settings(definition):
    """產生內嵌的 Settings"""
    host = definition.get("host", "https://api.example.com")
    L = []
    _W(L, 0, "")
    _W(L, 0, "# " + "=" * 60)
    _W(L, 0, "# 設定")
    _W(L, 0, "# " + "=" * 60)
    _W(L, 0, "SETTINGS = {")
    _W(L, 1, f'"host": os.getenv("LOCUST_HOST", "{host}"),')
    _W(L, 1, '"request_timeout": int(os.getenv("LOCUST_REQUEST_TIMEOUT", "30")),')
    _W(L, 1, '"enable_assertions": os.getenv("LOCUST_ENABLE_ASSERTIONS", "true").lower() == "true",')
    _W(L, 1, '"default_headers": {')
    _W(L, 2, '"Content-Type": "application/json",')
    _W(L, 2, '"Accept": "application/json",')
    _W(L, 1, "},")
    _W(L, 0, "}")
    _W(L, 0, "")
    _W(L, 0, "logging.basicConfig(")
    _W(L, 1, "level=logging.INFO,")
    _W(L, 1, 'format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",')
    _W(L, 0, ")")
    _W(L, 0, "logger = logging.getLogger(__name__)")
    return "\n".join(L)


def _gen_data_provider(text_features):
    """產生內嵌的資料產生器"""
    L = []
    _W(L, 0, "")
    _W(L, 0, "# " + "=" * 60)
    _W(L, 0, "# 資料產生與變數解析")
    _W(L, 0, "# " + "=" * 60)

    if text_features["has_random"]:
        _W(L, 0, "fake = Faker()")
        _W(L, 0, "")
        _W(L, 0, "VARIABLE_GENERATORS = {")
        _W(L, 1, '"RANDOM_NAME": lambda: fake.name(),')
        _W(L, 1, '"RANDOM_EMAIL": lambda: fake.email(),')
        _W(L, 1, '"RANDOM_PHONE": lambda: fake.phone_number(),')
        _W(L, 1, '"RANDOM_UUID": lambda: str(uuid.uuid4()),')
        _W(L, 1, '"RANDOM_INT": lambda: random.randint(1, 10000),')
        _W(L, 1, '"RANDOM_STRING": lambda: "".join(random.choices(string.ascii_letters, k=10)),')
        _W(L, 1, '"TIMESTAMP": lambda: int(time.time()),')
        _W(L, 1, '"RANDOM_ADDRESS": lambda: fake.address().replace("\\n", ", "),')
        _W(L, 1, '"RANDOM_TEXT": lambda: fake.text(max_nb_chars=50),')
        _W(L, 1, '"RANDOM_USERNAME": lambda: fake.user_name(),')
        _W(L, 1, '"RANDOM_PASSWORD": lambda: fake.password(length=12),')
        _W(L, 1, '"RANDOM_IPV4": lambda: fake.ipv4(),')
        _W(L, 1, '"RANDOM_URL": lambda: fake.url(),')
        _W(L, 1, '"RANDOM_BOOL": lambda: random.choice(["true", "false"]),')
        _W(L, 0, "}")
        _W(L, 0, "")

    _W(L, 0, 'VARIABLE_PATTERN = re.compile(r"\\$\\{(\\w+)\\}")')
    if text_features["has_ctx"]:
        _W(L, 0, 'CONTEXT_PATTERN = re.compile(r"\\$\\{CTX:(\\w+)\\}")')
    if text_features["has_csv"] or text_features["has_json"]:
        _W(L, 0, 'DATA_SOURCE_PATTERN = re.compile(r"\\$\\{(CSV|JSON):([^:}]+):([^}]+)\\}")')

    # 內嵌 CSV 資料
    if text_features["has_csv"]:
        _W(L, 0, "")
        _W(L, 0, "# 內嵌 CSV 資料")
        _W(L, 0, "_csv_data = {}")
        _W(L, 0, "_csv_index = {}")
        for csv_file in sorted(text_features["csv_files"]):
            rows = _read_csv_file(csv_file)
            if rows:
                _W(L, 0, f"_csv_data[{csv_file!r}] = {json.dumps(rows, ensure_ascii=False)}")
                _W(L, 0, f"_csv_index[{csv_file!r}] = 0")
        _W(L, 0, "")
        _W(L, 0, "")
        _W(L, 0, 'def _load_csv_row(file_name, mode="sequential"):')
        _W(L, 1, "if file_name not in _csv_data or not _csv_data[file_name]:")
        _W(L, 2, "return {}")
        _W(L, 1, "rows = _csv_data[file_name]")
        _W(L, 1, 'if mode == "random":')
        _W(L, 2, "return random.choice(rows)")
        _W(L, 1, "row = rows[_csv_index[file_name] % len(rows)]")
        _W(L, 1, "_csv_index[file_name] += 1")
        _W(L, 1, "return row")

    # 內嵌 JSON 資料
    if text_features["has_json"]:
        _W(L, 0, "")
        _W(L, 0, "# 內嵌 JSON 資料")
        _W(L, 0, "_json_data = {}")
        for json_file in sorted(text_features["json_files"]):
            data = _read_json_file(json_file)
            if data is not None:
                _W(L, 0, f"_json_data[{json_file!r}] = {json.dumps(data, ensure_ascii=False)}")

    # _extract_json_path (for CSV/JSON data sources)
    if text_features["has_json"]:
        _W(L, 0, "")
        _W(L, 0, "")
        _W(L, 0, "def _extract_json_path(data, path):")
        _W(L, 1, 'keys = path.split(".")')
        _W(L, 1, "current = data")
        _W(L, 1, "for key in keys:")
        _W(L, 2, "if isinstance(current, dict) and key in current:")
        _W(L, 3, "current = current[key]")
        _W(L, 2, "elif isinstance(current, list) and key.isdigit():")
        _W(L, 3, "idx = int(key)")
        _W(L, 3, "if idx < len(current):")
        _W(L, 4, "current = current[idx]")
        _W(L, 3, "else:")
        _W(L, 4, "return None")
        _W(L, 2, "else:")
        _W(L, 3, "return None")
        _W(L, 1, "return current")

    # resolve_value
    _W(L, 0, "")
    _W(L, 0, "")
    _W(L, 0, "def resolve_value(value, context=None):")
    _W(L, 1, "if isinstance(value, str):")
    _W(L, 2, "return _resolve_string(value, context)")
    _W(L, 1, "elif isinstance(value, dict):")
    _W(L, 2, "return {k: resolve_value(v, context) for k, v in value.items()}")
    _W(L, 1, "elif isinstance(value, list):")
    _W(L, 2, "return [resolve_value(item, context) for item in value]")
    _W(L, 1, "return value")

    # _resolve_string
    _W(L, 0, "")
    _W(L, 0, "")
    _W(L, 0, "def _resolve_string(text, context=None):")

    if text_features["has_ctx"]:
        _W(L, 1, "if context:")
        _W(L, 2, "def ctx_replacer(match):")
        _W(L, 3, "var_name = match.group(1)")
        _W(L, 3, "if var_name in context:")
        _W(L, 4, "return str(context[var_name])")
        _W(L, 3, "return match.group(0)")
        _W(L, 2, "text = CONTEXT_PATTERN.sub(ctx_replacer, text)")

    if text_features["has_csv"] or text_features["has_json"]:
        _W(L, 1, "def data_source_replacer(match):")
        _W(L, 2, "source_type, file_name, field = match.group(1), match.group(2), match.group(3)")
        if text_features["has_csv"]:
            _W(L, 2, 'if source_type == "CSV":')
            _W(L, 3, "row = _load_csv_row(file_name)")
            _W(L, 3, "if row and field in row:")
            _W(L, 4, "return str(row[field])")
        if text_features["has_json"]:
            _W(L, 2, 'if source_type == "JSON":')
            _W(L, 3, "data = _json_data.get(file_name)")
            _W(L, 3, "if data is not None:")
            _W(L, 4, "val = _extract_json_path(data, field)")
            _W(L, 4, "if val is not None:")
            _W(L, 5, "return str(random.choice(val)) if isinstance(val, list) else str(val)")
        _W(L, 2, "return match.group(0)")
        _W(L, 1, "text = DATA_SOURCE_PATTERN.sub(data_source_replacer, text)")

    _W(L, 1, "def replacer(match):")
    _W(L, 2, "var_name = match.group(1)")
    if text_features["has_random"]:
        _W(L, 2, "if var_name in VARIABLE_GENERATORS:")
        _W(L, 3, "return str(VARIABLE_GENERATORS[var_name]())")
    _W(L, 2, "if context and var_name in context:")
    _W(L, 3, "return str(context[var_name])")
    _W(L, 2, "env_val = os.getenv(var_name)")
    _W(L, 2, "if env_val is not None:")
    _W(L, 3, "return env_val")
    _W(L, 2, "return match.group(0)")
    _W(L, 1, "return VARIABLE_PATTERN.sub(replacer, text)")

    return "\n".join(L)


def _gen_base_user(features):
    """產生內嵌的 BaseUser 類別"""
    wait_mode = features.get("_wait_mode", "between")
    wait_config = features.get("_wait_config", {})

    if wait_mode == "between":
        wt = f"between({wait_config.get('min', 1)}, {wait_config.get('max', 3)})"
    elif wait_mode == "constant":
        wt = f"constant({wait_config.get('value', 1)})"
    elif wait_mode == "constant_pacing":
        wt = f"constant_pacing({wait_config.get('value', 1)})"
    else:
        wt = "between(1, 3)"

    L = []
    _W(L, 0, "")
    _W(L, 0, "")
    _W(L, 0, "# " + "=" * 60)
    _W(L, 0, "# BaseUser")
    _W(L, 0, "# " + "=" * 60)
    _W(L, 0, "class BaseUser(HttpUser):")
    _W(L, 1, "abstract = True")
    _W(L, 1, 'host = SETTINGS["host"]')
    _W(L, 1, f"wait_time = {wt}")

    if features["has_auth"]:
        _W(L, 1, f"auth_config = {features.get('_auth_config')!r}")
    else:
        _W(L, 1, "auth_config = None")

    if features["has_retry"]:
        _W(L, 1, f"retry_config = {features.get('_retry_config')!r}")
    else:
        _W(L, 1, "retry_config = None")

    _W(L, 0, "")

    # on_start
    _W(L, 1, "def on_start(self):")
    _W(L, 2, 'self.default_headers = SETTINGS["default_headers"].copy()')
    _W(L, 2, "self.context = {}")
    if features["has_auth"]:
        _W(L, 2, "self._init_auth()")
    _W(L, 2, 'logger.info("使用者 %s 開始執行壓力測試", self.__class__.__name__)')
    _W(L, 0, "")

    # on_stop
    _W(L, 1, "def on_stop(self):")
    _W(L, 2, 'logger.info("使用者 %s 結束壓力測試", self.__class__.__name__)')
    _W(L, 0, "")

    # _extract_json_value
    _W(L, 1, "@staticmethod")
    _W(L, 1, "def _extract_json_value(data, path):")
    _W(L, 2, 'keys = path.split(".")')
    _W(L, 2, "current = data")
    _W(L, 2, "for key in keys:")
    _W(L, 3, "if isinstance(current, dict) and key in current:")
    _W(L, 4, "current = current[key]")
    _W(L, 3, "elif isinstance(current, list) and key.isdigit():")
    _W(L, 4, "current = current[int(key)]")
    _W(L, 3, "else:")
    _W(L, 4, "return None")
    _W(L, 2, "return current")
    _W(L, 0, "")

    # auth methods
    if features["has_auth"]:
        _W(L, 1, "def _init_auth(self):")
        _W(L, 2, "if not self.auth_config:")
        _W(L, 3, "return")
        _W(L, 2, 'auth_type = self.auth_config.get("type", "bearer")')
        _W(L, 2, 'if auth_type == "bearer" and "login" in self.auth_config:')
        _W(L, 3, "self._do_login()")
        _W(L, 2, 'elif auth_type == "basic":')
        _W(L, 3, "import base64")
        _W(L, 3, 'username = self.auth_config.get("username", "")')
        _W(L, 3, 'password = self.auth_config.get("password", "")')
        _W(L, 3, 'token = base64.b64encode(f"{username}:{password}".encode()).decode()')
        _W(L, 3, 'self.default_headers["Authorization"] = f"Basic {token}"')
        _W(L, 2, 'elif auth_type == "api_key":')
        _W(L, 3, 'header_name = self.auth_config.get("header_name", "X-API-Key")')
        _W(L, 3, 'api_key = self.auth_config.get("key", "")')
        _W(L, 3, "self.default_headers[header_name] = api_key")
        _W(L, 0, "")

        _W(L, 1, "def _do_login(self):")
        _W(L, 2, 'login_cfg = self.auth_config["login"]')
        _W(L, 2, 'method = login_cfg.get("method", "POST").upper()')
        _W(L, 2, 'endpoint = login_cfg.get("endpoint", "/auth/login")')
        _W(L, 2, 'body = login_cfg.get("body", {})')
        _W(L, 2, 'token_path = login_cfg.get("token_path", "token")')
        _W(L, 2, "try:")
        _W(L, 3, "resp = self.client.request(")
        _W(L, 4, "method=method, url=endpoint, json=body,")
        _W(L, 4, 'headers={"Content-Type": "application/json"},')
        _W(L, 3, ")")
        _W(L, 3, "if resp.status_code < 400:")
        _W(L, 4, "json_resp = resp.json()")
        _W(L, 4, "token = self._extract_json_value(json_resp, token_path)")
        _W(L, 4, "if token:")
        _W(L, 5, 'header_name = self.auth_config.get("header_name", "Authorization")')
        _W(L, 5, 'prefix = self.auth_config.get("prefix", "Bearer")')
        _W(L, 5, 'self.default_headers[header_name] = f"{prefix} {token}"')
        _W(L, 5, 'self.context["AUTH_TOKEN"] = token')
        _W(L, 5, "self._token_obtained_at = time.time()")
        _W(L, 5, 'logger.info("使用者 %s 登入成功", self.__class__.__name__)')
        _W(L, 2, "except Exception as e:")
        _W(L, 3, 'logger.error("登入時發生錯誤: %s", e)')
        _W(L, 0, "")

        _W(L, 1, "def _refresh_token_if_needed(self):")
        _W(L, 2, 'if not self.auth_config or "refresh" not in self.auth_config:')
        _W(L, 3, "return")
        _W(L, 2, 'refresh_cfg = self.auth_config["refresh"]')
        _W(L, 2, 'ttl = refresh_cfg.get("token_ttl_seconds", 3600)')
        _W(L, 2, 'if not hasattr(self, "_token_obtained_at"):')
        _W(L, 3, "return")
        _W(L, 2, "if time.time() - self._token_obtained_at < ttl - 60:")
        _W(L, 3, "return")
        _W(L, 2, 'endpoint = refresh_cfg.get("endpoint", "/auth/refresh")')
        _W(L, 2, 'method = refresh_cfg.get("method", "POST").upper()')
        _W(L, 2, 'token_path = refresh_cfg.get("token_path", "token")')
        _W(L, 2, "try:")
        _W(L, 3, "resp = self.client.request(")
        _W(L, 4, "method=method, url=endpoint,")
        _W(L, 4, "headers=self.default_headers.copy(),")
        _W(L, 3, ")")
        _W(L, 3, "if resp.status_code < 400:")
        _W(L, 4, "json_resp = resp.json()")
        _W(L, 4, "token = self._extract_json_value(json_resp, token_path)")
        _W(L, 4, "if token:")
        _W(L, 5, 'header_name = self.auth_config.get("header_name", "Authorization")')
        _W(L, 5, 'prefix = self.auth_config.get("prefix", "Bearer")')
        _W(L, 5, 'self.default_headers[header_name] = f"{prefix} {token}"')
        _W(L, 5, 'self.context["AUTH_TOKEN"] = token')
        _W(L, 5, "self._token_obtained_at = time.time()")
        _W(L, 2, "except Exception as e:")
        _W(L, 3, 'logger.error("刷新 Token 失敗: %s", e)')
        _W(L, 0, "")

    # make_request
    _W(L, 1, "def make_request(self, method, endpoint, name=None, **kwargs):")
    if features["has_auth"]:
        _W(L, 2, "self._refresh_token_if_needed()")
    _W(L, 2, "headers = self.default_headers.copy()")
    _W(L, 2, 'if "headers" in kwargs:')
    _W(L, 3, 'headers.update(kwargs.pop("headers"))')
    _W(L, 2, 'assertions = kwargs.pop("assertions", None)')
    _W(L, 2, 'extract = kwargs.pop("extract", None)')
    _W(L, 2, 'retry = kwargs.pop("retry", None) or self.retry_config')
    _W(L, 2, 'kwargs.setdefault("timeout", SETTINGS["request_timeout"])')
    _W(L, 2, 'request_name = name or f"[{method}] {endpoint}"')

    if features["has_retry"]:
        _W(L, 2, "max_retries, retry_wait, retry_on_status = 0, 1, []")
        _W(L, 2, "if retry:")
        _W(L, 3, 'max_retries = retry.get("max_retries", 0)')
        _W(L, 3, 'retry_wait = retry.get("wait_seconds", 1)')
        _W(L, 3, 'retry_on_status = retry.get("on_status", [])')
        _W(L, 2, "response = None")
        _W(L, 2, "for attempt in range(max_retries + 1):")
        _W(L, 3, "with self.client.request(")
        _W(L, 4, "method=method, url=endpoint, headers=headers,")
        _W(L, 4, "name=request_name, catch_response=True, **kwargs,")
        _W(L, 3, ") as resp:")
        _W(L, 4, "if attempt < max_retries and retry_on_status and resp.status_code in retry_on_status:")
        _W(L, 5, 'logger.warning("%s 第 %d 次嘗試回傳 HTTP %d，%ds 後重試",')
        _W(L, 5, "               request_name, attempt + 1, resp.status_code, retry_wait)")
        _W(L, 5, "resp.success()")
        _W(L, 5, "time.sleep(retry_wait)")
        _W(L, 5, "retry_wait *= 2")
        _W(L, 5, "continue")
        _W(L, 4, "self._validate_response(resp, assertions, request_name)")
        _W(L, 4, "if extract:")
        _W(L, 5, "self._extract_from_response(resp, extract, request_name)")
        _W(L, 4, "response = resp")
        _W(L, 4, "break")
        _W(L, 2, "return response")
    else:
        _W(L, 2, "with self.client.request(")
        _W(L, 3, "method=method, url=endpoint, headers=headers,")
        _W(L, 3, "name=request_name, catch_response=True, **kwargs,")
        _W(L, 2, ") as resp:")
        _W(L, 3, "self._validate_response(resp, assertions, request_name)")
        _W(L, 3, "if extract:")
        _W(L, 4, "self._extract_from_response(resp, extract, request_name)")
        _W(L, 3, "return resp")
    _W(L, 0, "")

    # _extract_from_response
    _W(L, 1, "def _extract_from_response(self, response, extract_rules, request_name):")
    _W(L, 2, "try:")
    _W(L, 3, "json_resp = response.json()")
    _W(L, 3, "for var_name, json_path in extract_rules.items():")
    _W(L, 4, "value = self._extract_json_value(json_resp, json_path)")
    _W(L, 4, "if value is not None:")
    _W(L, 5, "self.context[var_name] = value")
    _W(L, 4, "else:")
    _W(L, 5, """logger.warning("%s: 無法提取 '%s' (path: %s)", request_name, var_name, json_path)""")
    _W(L, 2, "except Exception as e:")
    _W(L, 3, 'logger.warning("%s: 提取回應值失敗: %s", request_name, e)')
    _W(L, 0, "")

    # _validate_response
    _W(L, 1, "def _validate_response(self, response, assertions, request_name):")
    _W(L, 2, 'if not SETTINGS["enable_assertions"] or not assertions:')
    _W(L, 3, "if response.status_code >= 400:")
    _W(L, 4, 'response.failure(f"{request_name} 回傳 HTTP {response.status_code}")')
    _W(L, 3, "else:")
    _W(L, 4, "response.success()")
    _W(L, 3, "return")
    _W(L, 2, 'expected_status = assertions.get("status_code")')
    _W(L, 2, "if expected_status and response.status_code != expected_status:")
    _W(L, 3, 'response.failure(f"{request_name} 預期狀態碼 {expected_status}，實際為 {response.status_code}")')
    _W(L, 3, "return")
    _W(L, 2, 'expected_fields = assertions.get("response_fields")')
    _W(L, 2, "if expected_fields:")
    _W(L, 3, "try:")
    _W(L, 4, "json_resp = response.json()")
    _W(L, 4, "for field in expected_fields:")
    _W(L, 5, "if field not in json_resp:")
    _W(L, 6, 'response.failure(f"{request_name} 回應中缺少欄位: {field}")')
    _W(L, 6, "return")
    _W(L, 3, "except Exception:")
    _W(L, 4, 'response.failure(f"{request_name} 回應非有效 JSON")')
    _W(L, 4, "return")
    _W(L, 2, 'max_response_time = assertions.get("max_response_time_ms")')
    _W(L, 2, "if max_response_time and response.elapsed.total_seconds() * 1000 > max_response_time:")
    _W(L, 3, "response.failure(")
    _W(L, 4, 'f"{request_name} 回應時間 {response.elapsed.total_seconds() * 1000:.0f}ms "'
       )
    _W(L, 4, 'f"超過上限 {max_response_time}ms"')
    _W(L, 3, ")")
    _W(L, 3, "return")
    _W(L, 2, "response.success()")

    return "\n".join(L)


def _gen_task_method(api_def, indent=4):
    """產生單一 API task 方法的程式碼"""
    name = api_def["name"]
    method = api_def["method"].upper()
    endpoint = api_def["endpoint"]
    headers = api_def.get("headers", {})
    body = api_def.get("body")
    params = api_def.get("params")
    assertions = api_def.get("assertions")
    extract = api_def.get("extract")
    retry = api_def.get("retry")
    i = indent  # indent level (in units of 4 spaces)

    L = []
    _W(L, i // 4, f"def task_{name}(self):")
    n = i // 4 + 1
    _W(L, n, "ctx = self.context")
    _W(L, n, f"endpoint = resolve_value({endpoint!r}, ctx)")
    _W(L, n, f"headers = resolve_value({headers!r}, ctx)")
    if params:
        _W(L, n, f"params = resolve_value({params!r}, ctx)")
    if body:
        _W(L, n, f"body = resolve_value({body!r}, ctx)")
    _W(L, n, "kwargs = {}")
    if params:
        _W(L, n, "kwargs['params'] = params")
    if body:
        _W(L, n, "kwargs['json'] = body")
    if extract:
        _W(L, n, f"kwargs['extract'] = {extract!r}")
    if retry:
        _W(L, n, f"kwargs['retry'] = {retry!r}")

    call_args = f"{method!r}, endpoint, name={name!r}, headers=headers"
    if assertions:
        call_args += f", assertions={assertions!r}"
    _W(L, n, f"self.make_request({call_args}, **kwargs)")

    return "\n".join(L)


def _gen_flow_method(flow_def, indent=4):
    """產生 flow task 方法的程式碼"""
    flow_name = flow_def["name"]
    steps = flow_def.get("steps", [])
    base = indent // 4

    L = []
    _W(L, base, f"def flow_{flow_name}(self):")
    _W(L, base + 1, "ctx = self.context")

    for i, step in enumerate(steps):
        step_method = step["method"].upper()
        step_endpoint = step["endpoint"]
        step_headers = step.get("headers", {})
        step_body = step.get("body")
        step_params = step.get("params")
        step_assertions = step.get("assertions")
        step_extract = step.get("extract")
        step_retry = step.get("retry")
        step_name = step.get("name", f"{flow_name}/step_{i}")
        n = base + 1

        _W(L, n, f"# Step {i + 1}: {step_name}")
        _W(L, n, f"ep_{i} = resolve_value({step_endpoint!r}, ctx)")
        _W(L, n, f"hd_{i} = resolve_value({step_headers!r}, ctx)")

        kwargs_parts = []
        if step_params:
            _W(L, n, f"pm_{i} = resolve_value({step_params!r}, ctx)")
            kwargs_parts.append(f"'params': pm_{i}")
        if step_body:
            _W(L, n, f"bd_{i} = resolve_value({step_body!r}, ctx)")
            kwargs_parts.append(f"'json': bd_{i}")
        if step_extract:
            kwargs_parts.append(f"'extract': {step_extract!r}")
        if step_retry:
            kwargs_parts.append(f"'retry': {step_retry!r}")

        kwargs_str = "{" + ", ".join(kwargs_parts) + "}" if kwargs_parts else "{}"

        call_args = f"{step_method!r}, ep_{i}, name={step_name!r}, headers=hd_{i}"
        if step_assertions:
            call_args += f", assertions={step_assertions!r}"
        _W(L, n, f"self.make_request({call_args}, **{kwargs_str})")

    return "\n".join(L)


def _gen_user_class(definition, class_name):
    """產生具體的 User 子類別"""
    apis = definition.get("apis", [])
    flows = definition.get("flows", [])

    L = []
    _W(L, 0, "")
    _W(L, 0, "")
    _W(L, 0, "# " + "=" * 60)
    _W(L, 0, f"# 測試 User: {class_name}")
    _W(L, 0, "# " + "=" * 60)
    _W(L, 0, f"class {class_name}(BaseUser):")
    _W(L, 1, "abstract = False")
    _W(L, 0, "")

    for api_def in apis:
        weight = api_def.get("weight", 1)
        tags_list = api_def.get("tags", [])
        if tags_list:
            _W(L, 1, f"@tag({', '.join(repr(t) for t in tags_list)})")
        _W(L, 1, f"@task({weight})")
        L.append(_gen_task_method(api_def, indent=4))
        _W(L, 0, "")

    for flow_def in flows:
        weight = flow_def.get("weight", 1)
        tags_list = flow_def.get("tags", [])
        if tags_list:
            _W(L, 1, f"@tag({', '.join(repr(t) for t in tags_list)})")
        _W(L, 1, f"@task({weight})")
        L.append(_gen_flow_method(flow_def, indent=4))
        _W(L, 0, "")

    return "\n".join(L)


def export_yaml(yaml_path, output_path=None):
    """將 YAML 測試定義匯出為獨立 Python 腳本

    Args:
        yaml_path: YAML 定義檔路徑
        output_path: 輸出檔路徑，預設為同目錄下的 {name}_standalone.py

    Returns:
        str: 輸出檔路徑
    """
    yaml_path = os.path.abspath(yaml_path)
    if not os.path.exists(yaml_path):
        raise FileNotFoundError(f"YAML 檔案不存在: {yaml_path}")

    with open(yaml_path, "r", encoding="utf-8") as f:
        yaml_text = f.read()
    definition = yaml.safe_load(yaml_text)

    text_features = _scan_yaml_text(yaml_text)
    struct_features = _scan_definition(definition)
    features = {**text_features, **struct_features}

    wt_cfg = definition.get("wait_time", {"min": 1, "max": 3})
    features["_wait_mode"] = wt_cfg.get("mode", "between")
    features["_wait_config"] = wt_cfg

    if features["has_auth"]:
        features["_auth_config"] = definition["auth"]
        features["_auth_type"] = definition["auth"].get("type", "bearer")
    if features["has_retry"]:
        features["_retry_config"] = definition.get("retry")

    test_name = definition.get("name", Path(yaml_path).stem)
    class_name = "".join(
        word.capitalize()
        for word in test_name.replace("-", "_").split("_")
    ) + "User"

    parts = [
        _gen_imports(features, text_features),
        _gen_settings(definition),
        _gen_data_provider(text_features),
        _gen_base_user(features),
        _gen_user_class(definition, class_name),
    ]
    script = "\n".join(parts) + "\n"

    if output_path is None:
        output_dir = os.path.dirname(yaml_path)
        stem = Path(yaml_path).stem
        output_path = os.path.join(output_dir, f"{stem}_standalone.py")

    output_path = os.path.abspath(output_path)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(script)

    logger.info("已匯出獨立腳本: %s", output_path)
    return output_path


def main():
    """CLI 入口"""
    import argparse

    parser = argparse.ArgumentParser(
        description="將 YAML 測試定義匯出為獨立的 Locust 腳本"
    )
    parser.add_argument("yaml_file", help="YAML 測試定義檔路徑")
    parser.add_argument("-o", "--output", help="輸出檔路徑 (預設: {yaml_name}_standalone.py)", default=None)

    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    try:
        output = export_yaml(args.yaml_file, args.output)
        print(f"匯出成功: {output}")
    except Exception as e:
        print(f"匯出失敗: {e}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
