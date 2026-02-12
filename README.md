# Locust 壓力測試框架

YAML 驅動的壓力測試框架，寫 YAML 就能跑測試，不用寫 Python。

## 架構

```
load_tests/
├── api_definitions/    ← 你寫的 YAML 測試定義
├── base/base_user.py   ← 基礎類別 (認證/重試/驗證)
├── generator/          ← YAML → Locust User 自動產生
├── exporter/           ← 匯出獨立腳本
├── utils/              ← 資料產生與變數替換
├── listeners/          ← 報告與 Webhook
├── profiles/           ← 環境設定 (dev/staging/prod)
├── data/               ← CSV/JSON 測試資料
└── locustfile.py       ← 主入口
tests/                  ← 單元測試
export.py               ← 匯出 CLI
```

## 流程

```
                    ┌─────────────────┐
                    │  撰寫 YAML 定義  │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │  locustfile.py  │
                    │  載入 Profile   │
                    │  掃描 YAML 目錄  │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │  generator.py   │
                    │  解析 YAML      │
                    │  動態產生 User   │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
     ┌────────▼──────┐ ┌────▼─────┐ ┌──────▼───────┐
     │  data_provider │ │ base_user│ │ report_listener│
     │  變數替換      │ │ 認證/重試 │ │ 報告/Webhook  │
     └───────────────┘ └──────────┘ └──────────────┘
              │              │              │
              └──────────────┼──────────────┘
                             │
                    ┌────────▼────────┐
                    │   Locust 執行    │
                    │   壓力測試       │
                    └─────────────────┘
```

## 使用方式

### 1. 安裝

```bash
pip install -r requirements.txt
```

### 2. 寫 YAML

在 `load_tests/api_definitions/` 放一個 `.yaml`：

```yaml
name: "my_test"
host: "https://api.example.com"

apis:
  - name: "get_users"
    method: "GET"
    endpoint: "/api/users"
    assertions:
      status_code: 200
```

### 3. 跑測試

```bash
# Web UI
locust -f load_tests/locustfile.py

# 無頭模式
locust -f load_tests/locustfile.py --headless -u 100 -r 10 -t 60s

# 指定環境
LOCUST_PROFILE=staging locust -f load_tests/locustfile.py

# 指定 tag
locust -f load_tests/locustfile.py --tags smoke
```

### 4. 匯出獨立腳本（拋棄式）

```bash
python export.py load_tests/api_definitions/flow_example.yaml -o /tmp/test.py
locust -f /tmp/test.py --headless -u 10 -r 2 -t 30s
```

### 5. 跑單元測試

```bash
python -m pytest tests/ -v
```

## YAML 功能速查

| 功能 | 語法 | 說明 |
|------|------|------|
| 隨機資料 | `${RANDOM_NAME}` `${RANDOM_EMAIL}` 等 | 14 種內建產生器 |
| CSV 資料 | `${CSV:users.csv:username}` | 從 CSV 循序讀取 |
| JSON 資料 | `${JSON:products.json:product_ids}` | 從 JSON 讀取 |
| 請求鏈 | `${CTX:var_name}` + `extract` | 前一個回應值傳到下一個 |
| 環境變數 | `${MY_VAR}` | 讀取環境變數 |
| 認證 | `auth.type: bearer/basic/api_key` | 自動登入/刷新 Token |
| 重試 | `retry.max_retries: 3` | 指數退避重試 |
| 等待時間 | `wait_time.mode: between/constant` | Think Time 控制 |
| 驗證 | `assertions.status_code: 200` | 回應驗證 |
| 權重 | `weight: 5` | 呼叫頻率比例 |
| 標籤 | `tags: [smoke]` | `--tags` 篩選 |
| 報告 | `LOCUST_JSON_REPORT=true` | JSON 報告 + Webhook |
| Profile | `LOCUST_PROFILE=staging` | 環境切換 |

詳細 YAML 格式與範例請參考 `load_tests/api_definitions/` 目錄下的範例檔案。

## 授權

MIT License
