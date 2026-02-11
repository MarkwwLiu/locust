import os
import re
import uuid
import random
import string
import time

from faker import Faker

fake = Faker()


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


def resolve_value(value):
    """遞迴解析值中的變數佔位符

    支援:
        - "${RANDOM_NAME}" -> 動態產生隨機名稱
        - "${ENV_VAR}" -> 從環境變數讀取
        - 巢狀 dict/list 結構
    """
    if isinstance(value, str):
        return _resolve_string(value)
    elif isinstance(value, dict):
        return {k: resolve_value(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [resolve_value(item) for item in value]
    return value


def _resolve_string(text):
    """解析字串中的所有 ${VAR} 佔位符"""

    def replacer(match):
        var_name = match.group(1)

        # 優先使用內建變數產生器
        if var_name in VARIABLE_GENERATORS:
            return str(VARIABLE_GENERATORS[var_name]())

        # 其次從環境變數讀取
        env_val = os.getenv(var_name)
        if env_val is not None:
            return env_val

        # 找不到則保持原樣
        return match.group(0)

    return VARIABLE_PATTERN.sub(replacer, text)
