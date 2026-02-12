# Locust 壓力測試框架

基於 [Locust](https://locust.io/) 的 YAML 驅動壓力測試框架，透過 YAML 定義即可自動產生測試案例，無需撰寫 Python 程式碼。

## 功能特點

- **YAML 驅動測試** - 用 YAML 定義 API 測試，自動產生 Locust User 類別
- **請求鏈 (Flow)** - 多個 API 依序執行，前一個回應值可供後續使用
- **認證管理** - 支援 Bearer Token 自動登入/刷新、Basic Auth、API Key
- **動態資料產生** - 14 種內建隨機資料產生器 (姓名、Email、UUID 等)
- **CSV/JSON 資料來源** - 從外部檔案載入測試資料
- **重試機制** - 支援指數退避的自動重試，可針對特定 HTTP 狀態碼觸發
- **環境 Profile** - dev / staging / prod 多環境設定切換
- **自訂報告** - JSON 報告輸出、Webhook 通知 (Slack 等)
- **Think Time 模式** - 支援 between、constant、constant_pacing
- **回應驗證** - 狀態碼、欄位存在性、回應時間上限
- **加權任務分配** - 透過 weight 控制各 API 呼叫頻率

## 專案結構

```
export.py                      # 匯出獨立腳本的 CLI 入口
load_tests/
├── locustfile.py              # 主入口
├── api_definitions/           # YAML 測試定義
│   ├── single_api_example.yaml
│   ├── multi_api_example.yaml
│   ├── flow_example.yaml      # 請求鏈範例
│   └── data_source_example.yaml
├── base/
│   └── base_user.py           # 基礎 User 類別
├── config/
│   └── settings.py            # 全域設定
├── generator/
│   └── generator.py           # YAML → Locust 類別產生器
├── exporter/
│   └── exporter.py            # 拋棄式腳本匯出器
├── utils/
│   └── data_provider.py       # 資料產生與變數替換
├── listeners/
│   └── report_listener.py     # 事件監聽與報告
├── profiles/                  # 環境 Profile
│   ├── dev.yaml
│   ├── staging.yaml
│   └── prod.yaml
├── data/                      # 外部測試資料
│   ├── users.csv
│   └── products.json
tests/                         # 單元測試
├── test_base_user.py
├── test_data_provider.py
├── test_exporter.py
├── test_generator.py
└── test_profile_loader.py
```

## 快速開始

### 安裝

```bash
pip install -r requirements.txt
```

### 執行測試

```bash
# Web UI 模式
locust -f load_tests/locustfile.py

# 無頭模式
locust -f load_tests/locustfile.py --headless -u 100 -r 10 -t 60s

# 指定 tag
locust -f load_tests/locustfile.py --tags smoke

# 使用環境 Profile
LOCUST_PROFILE=staging locust -f load_tests/locustfile.py

# 啟用 JSON 報告
LOCUST_JSON_REPORT=true locust -f load_tests/locustfile.py
```

### 匯出獨立腳本 (拋棄式腳本)

將指定的 YAML 測試定義匯出為完全獨立的 Python 腳本，不依賴框架，可直接複製到任何地方執行：

```bash
# 匯出到預設路徑 (同目錄下 {name}_standalone.py)
python export.py load_tests/api_definitions/flow_example.yaml

# 匯出到指定路徑
python export.py load_tests/api_definitions/flow_example.yaml -o /tmp/my_test.py

# 匯出後直接執行
locust -f /tmp/my_test.py --headless -u 10 -r 2 -t 30s
```

匯出器會自動分析 YAML 用到的功能，只將必要的程式碼內嵌到腳本中：
- 用到 `${RANDOM_*}` → 內嵌 Faker 資料產生器
- 用到 `${CSV:...}` → 將 CSV 資料直接嵌入腳本
- 用到 `${JSON:...}` → 將 JSON 資料直接嵌入腳本
- 用到 `auth` → 內嵌認證邏輯
- 用到 `retry` → 內嵌重試機制

### 執行單元測試

```bash
python -m pytest tests/ -v
```

## YAML 定義格式

### 基本 API 測試

```yaml
name: "my_api_test"
host: "https://api.example.com"

apis:
  - name: "get_users"
    method: "GET"
    endpoint: "/api/users"
    headers:
      Authorization: "Bearer ${TOKEN}"
    params:
      page: 1
    weight: 5
    tags: [smoke, read]
    assertions:
      status_code: 200
      response_fields: ["data"]
      max_response_time_ms: 3000
```

### 請求鏈 (Flow)

前一個 step 的 `extract` 值可透過 `${CTX:變數名}` 在後續 step 使用：

```yaml
flows:
  - name: "create_and_read"
    weight: 3
    tags: [flow]
    steps:
      - name: "create_user"
        method: "POST"
        endpoint: "/api/users"
        body:
          name: "${RANDOM_NAME}"
        extract:
          user_id: "data.id"       # 從回應 JSON 提取

      - name: "get_user"
        method: "GET"
        endpoint: "/api/users/${CTX:user_id}"  # 使用提取的值
```

### 認證設定

```yaml
auth:
  type: bearer          # bearer / basic / api_key
  prefix: "Bearer"
  login:
    method: "POST"
    endpoint: "/auth/login"
    body:
      username: "user"
      password: "pass"
    token_path: "data.access_token"  # 從登入回應中提取 token
  refresh:
    endpoint: "/auth/refresh"
    token_path: "data.access_token"
    token_ttl_seconds: 3600
```

### CSV / JSON 資料來源

將資料檔案放在 `load_tests/data/` 目錄下：

```yaml
apis:
  - name: "login"
    method: "POST"
    endpoint: "/auth/login"
    body:
      username: "${CSV:users.csv:username}"         # 從 CSV 循序讀取
      password: "${CSV:users.csv:password}"

  - name: "get_product"
    method: "GET"
    endpoint: "/products/${JSON:products.json:product_ids}"  # 從 JSON 隨機取值
```

### 重試機制

```yaml
# 全域重試 (套用到所有 API)
retry:
  max_retries: 3
  wait_seconds: 1       # 指數退避: 1s, 2s, 4s
  on_status: [502, 503, 504]

# 或在單一 API 設定
apis:
  - name: "important_api"
    method: "GET"
    endpoint: "/critical"
    retry:
      max_retries: 5
      wait_seconds: 2
      on_status: [500, 502, 503]
```

### Think Time 模式

```yaml
wait_time:
  mode: "between"           # 隨機等待 1~3 秒 (預設)
  min: 1
  max: 3

wait_time:
  mode: "constant"          # 固定等待 2 秒
  value: 2

wait_time:
  mode: "constant_pacing"   # 確保每 5 秒執行一次
  value: 5
```

## 環境 Profile

在 `load_tests/profiles/` 建立 YAML 設定檔：

```yaml
# staging.yaml
host: "https://staging-api.example.com"
users: 50
spawn_rate: 5
run_time: "5m"
request_timeout: 30
enable_assertions: true
headers:
  X-Environment: "staging"
env:
  TOKEN: "staging-token"
```

啟用方式：

```bash
LOCUST_PROFILE=staging locust -f load_tests/locustfile.py
```

## 報告與通知

### JSON 報告

```bash
LOCUST_JSON_REPORT=true LOCUST_REPORT_DIR=./reports locust -f load_tests/locustfile.py
```

測試結束後自動產出 `reports/report_YYYYMMDD_HHMMSS.json`，包含：
- 總請求數、失敗數、失敗率
- 平均 / 最小 / 最大回應時間
- P50 / P75 / P90 / P95 / P99 百分位數
- 各 endpoint 分別統計

### Webhook 通知

```bash
LOCUST_WEBHOOK_URL=https://hooks.slack.com/services/... locust -f load_tests/locustfile.py
```

測試開始和結束時會自動發送 JSON payload 到指定 URL。

## 變數替換

| 語法 | 說明 |
|------|------|
| `${RANDOM_NAME}` | 隨機姓名 |
| `${RANDOM_EMAIL}` | 隨機 Email |
| `${RANDOM_PHONE}` | 隨機電話 |
| `${RANDOM_UUID}` | UUID v4 |
| `${RANDOM_INT}` | 隨機整數 (1-10000) |
| `${RANDOM_STRING}` | 隨機 10 字元字串 |
| `${RANDOM_USERNAME}` | 隨機使用者名稱 |
| `${RANDOM_PASSWORD}` | 隨機密碼 (12 字元) |
| `${RANDOM_IPV4}` | 隨機 IPv4 |
| `${RANDOM_URL}` | 隨機 URL |
| `${RANDOM_BOOL}` | 隨機 true/false |
| `${RANDOM_ADDRESS}` | 隨機地址 |
| `${RANDOM_TEXT}` | 隨機文字 (50 字以內) |
| `${TIMESTAMP}` | 當前時間戳 |
| `${ENV_VAR_NAME}` | 讀取環境變數 |
| `${CTX:var_name}` | 請求鏈上下文變數 |
| `${CSV:file:column}` | CSV 資料 |
| `${JSON:file:path}` | JSON 資料 |

## 環境變數

| 變數 | 預設值 | 說明 |
|------|--------|------|
| `LOCUST_HOST` | `https://api.example.com` | 目標主機 |
| `LOCUST_USERS` | `10` | 並發使用者數 |
| `LOCUST_SPAWN_RATE` | `1` | 每秒產生使用者數 |
| `LOCUST_RUN_TIME` | `0` (無限) | 測試執行時間 |
| `LOCUST_REQUEST_TIMEOUT` | `30` | 請求逾時 (秒) |
| `LOCUST_ENABLE_ASSERTIONS` | `true` | 啟用回應驗證 |
| `LOCUST_PROFILE` | - | 環境 Profile 名稱 |
| `LOCUST_API_DIR` | - | 自訂 API 定義目錄 |
| `LOCUST_JSON_REPORT` | `false` | 啟用 JSON 報告 |
| `LOCUST_REPORT_DIR` | `reports` | 報告輸出目錄 |
| `LOCUST_WEBHOOK_URL` | - | Webhook 通知 URL |

## 授權

MIT License
