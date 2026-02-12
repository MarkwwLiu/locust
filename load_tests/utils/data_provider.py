import os
import re
import csv
import json
import uuid
import random
import string
import time
import logging
from pathlib import Path

from faker import Faker

fake = Faker()
logger = logging.getLogger(__name__)

# 內建變數產生器對照表
VARIABLE_GENERATORS = {
    "RANDOM_NAME": lambda: fake.name(),
    "RANDOM_EMAIL": lambda: fake.email(),
    "RANDOM_PHONE": lambda: fake.phone_number(),
    "RANDOM_UUID": lambda: str(uuid.uuid4()),
    "RANDOM_INT": lambda: random.randint(1, 10000),
    "RANDOM_STRING": lambda: "".join(
        random.choices(string.ascii_letters, k=10)
    ),
    "TIMESTAMP": lambda: int(time.time()),
    "RANDOM_ADDRESS": lambda: fake.address().replace("\n", ", "),
    "RANDOM_TEXT": lambda: fake.text(max_nb_chars=50),
    "RANDOM_USERNAME": lambda: fake.user_name(),
    "RANDOM_PASSWORD": lambda: fake.password(length=12),
    "RANDOM_IPV4": lambda: fake.ipv4(),
    "RANDOM_URL": lambda: fake.url(),
    "RANDOM_BOOL": lambda: random.choice(["true", "false"]),
}

# 變數替換的正規表達式: ${VARIABLE_NAME}
VARIABLE_PATTERN = re.compile(r"\$\{(\w+)\}")

# CSV 資料快取: {file_path: {"headers": [...], "rows": [...], "index": 0}}
_csv_cache = {}

# JSON 資料快取: {file_path: data}
_json_cache = {}

# CSV/JSON 變數模式: ${CSV:filename:column} 或 ${JSON:filename:path}
DATA_SOURCE_PATTERN = re.compile(r"\$\{(CSV|JSON):([^:}]+):([^}]+)\}")

# Context 變數模式: ${CTX:variable_name}
CONTEXT_PATTERN = re.compile(r"\$\{CTX:(\w+)\}")


def _get_data_dir():
    """取得 data 目錄的路徑"""
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "data",
    )


def load_csv_data(file_name, mode="sequential"):
    """載入 CSV 檔案資料

    Args:
        file_name: CSV 檔名 (相對於 data/ 目錄)
        mode: 讀取模式 - sequential (循序) / random (隨機)

    Returns:
        單一列的 dict
    """
    file_path = os.path.join(_get_data_dir(), file_name)

    if file_path not in _csv_cache:
        if not os.path.exists(file_path):
            logger.error("CSV 檔案不存在: %s", file_path)
            return {}
        with open(file_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            if not rows:
                logger.warning("CSV 檔案為空: %s", file_path)
                return {}
            _csv_cache[file_path] = {"rows": rows, "index": 0}
            logger.info("已載入 CSV: %s (%d 筆資料)", file_name, len(rows))

    cache = _csv_cache[file_path]
    rows = cache["rows"]

    if mode == "random":
        return random.choice(rows)

    # sequential: 循環讀取
    row = rows[cache["index"] % len(rows)]
    cache["index"] += 1
    return row


def load_json_data(file_name):
    """載入 JSON 檔案資料

    Args:
        file_name: JSON 檔名 (相對於 data/ 目錄)

    Returns:
        解析後的 JSON 物件
    """
    file_path = os.path.join(_get_data_dir(), file_name)

    if file_path not in _json_cache:
        if not os.path.exists(file_path):
            logger.error("JSON 檔案不存在: %s", file_path)
            return None
        with open(file_path, "r", encoding="utf-8") as f:
            _json_cache[file_path] = json.load(f)
            logger.info("已載入 JSON: %s", file_name)

    return _json_cache[file_path]


def _extract_json_path(data, path):
    """從 JSON 資料中依路徑提取值

    支援點號分隔路徑和陣列索引，如 "users.0.name"
    """
    keys = path.split(".")
    current = data
    for key in keys:
        if isinstance(current, dict) and key in current:
            current = current[key]
        elif isinstance(current, list) and key.isdigit():
            idx = int(key)
            if idx < len(current):
                current = current[idx]
            else:
                return None
        else:
            return None
    return current


def resolve_value(value, context=None):
    """遞迴解析值中的變數佔位符

    支援:
        - "${RANDOM_NAME}" -> 動態產生隨機名稱
        - "${ENV_VAR}" -> 從環境變數讀取
        - "${CTX:var_name}" -> 從請求鏈上下文讀取
        - "${CSV:file:column}" -> 從 CSV 檔案讀取
        - "${JSON:file:path}" -> 從 JSON 檔案讀取
        - 巢狀 dict/list 結構

    Args:
        value: 待解析的值
        context: 請求鏈上下文 dict (可選)
    """
    if isinstance(value, str):
        return _resolve_string(value, context)
    elif isinstance(value, dict):
        return {k: resolve_value(v, context) for k, v in value.items()}
    elif isinstance(value, list):
        return [resolve_value(item, context) for item in value]
    return value


def _resolve_string(text, context=None):
    """解析字串中的所有變數佔位符"""

    # 1. 先解析 ${CTX:var_name}
    if context:
        def ctx_replacer(match):
            var_name = match.group(1)
            if var_name in context:
                return str(context[var_name])
            return match.group(0)
        text = CONTEXT_PATTERN.sub(ctx_replacer, text)

    # 2. 解析 ${CSV:file:column} 和 ${JSON:file:path}
    def data_source_replacer(match):
        source_type = match.group(1)
        file_name = match.group(2)
        field = match.group(3)

        if source_type == "CSV":
            row = load_csv_data(file_name)
            if row and field in row:
                return str(row[field])
        elif source_type == "JSON":
            data = load_json_data(file_name)
            if data is not None:
                val = _extract_json_path(data, field)
                if val is not None:
                    if isinstance(val, list):
                        return str(random.choice(val))
                    return str(val)
        return match.group(0)

    text = DATA_SOURCE_PATTERN.sub(data_source_replacer, text)

    # 3. 解析 ${VARIABLE_NAME}
    def replacer(match):
        var_name = match.group(1)

        # 優先使用內建變數產生器
        if var_name in VARIABLE_GENERATORS:
            return str(VARIABLE_GENERATORS[var_name]())

        # 其次從 context 讀取
        if context and var_name in context:
            return str(context[var_name])

        # 再從環境變數讀取
        env_val = os.getenv(var_name)
        if env_val is not None:
            return env_val

        # 找不到則保持原樣
        return match.group(0)

    return VARIABLE_PATTERN.sub(replacer, text)
