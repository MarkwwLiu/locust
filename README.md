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
- **獨立腳本匯出** - 將 YAML 定義匯出為完全獨立的 Python 腳本，不依賴框架

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

## 運作原理

```
YAML 定義檔 → generator.py 解析 → 動態產生 Locust User 類別 → Locust 執行壓力測試
                                         ↑
                                  base_user.py (基礎功能)
                                  data_provider.py (變數替換)
                                  report_listener.py (報告)
                                  profile_loader.py (環境設定)
```

1. **locustfile.py** 啟動時載入環境 Profile，掃描 `api_definitions/` 目錄下所有 YAML
2. **generator.py** 解析每個 YAML，動態用 `type()` 建立繼承 `BaseUser` 的 User 類別
3. 每個 API 定義對應一個 `@task` 方法，每個 Flow 對應一個循序執行的 `@task` 方法
4. **BaseUser** 提供認證、重試、回應驗證、值提取等基礎功能
5. **data_provider.py** 在每次請求時動態解析 `${...}` 變數（隨機值、CSV、JSON、CTX）
6. **report_listener.py** 透過 Locust events 自動收集統計資料並產出報告

## 快速開始

### 安裝

```bash
pip install -r requirements.txt
```

依賴套件：
- `locust>=2.20.0` - 壓力測試核心
- `PyYAML>=6.0` - YAML 解析
- `Faker>=22.0.0` - 隨機資料產生
- `pytest>=7.0.0` - 單元測試

### 執行測試

```bash
# Web UI 模式 (預設 http://localhost:8089)
locust -f load_tests/locustfile.py

# 無頭模式
locust -f load_tests/locustfile.py --headless -u 100 -r 10 -t 60s

# 指定 tag
locust -f load_tests/locustfile.py --tags smoke

# 使用環境 Profile
LOCUST_PROFILE=staging locust -f load_tests/locustfile.py

# 啟用 JSON 報告
LOCUST_JSON_REPORT=true locust -f load_tests/locustfile.py

# 組合使用
LOCUST_PROFILE=staging LOCUST_JSON_REPORT=true LOCUST_WEBHOOK_URL=https://hooks.slack.com/... \
  locust -f load_tests/locustfile.py --headless -u 50 -r 5 -t 5m

# 使用自訂 API 定義目錄
LOCUST_API_DIR=/path/to/my_definitions locust -f load_tests/locustfile.py
```

### 執行單元測試

```bash
python -m pytest tests/ -v
```

## YAML 定義格式

### 完整 YAML Schema

```yaml
# === 必要欄位 ===
name: "test_name"                    # 測試名稱，用於產生類別名稱

# === 選用欄位 ===
host: "https://api.example.com"      # 目標主機 (可用 LOCUST_HOST 覆寫)

# 認證設定
auth:
  type: bearer                       # bearer / basic / api_key
  # ... 詳見「認證設定」章節

# Think Time 設定
wait_time:
  mode: "between"                    # between / constant / constant_pacing
  # ... 詳見「Think Time 模式」章節

# 全域重試設定
retry:
  max_retries: 3
  wait_seconds: 1
  on_status: [502, 503, 504]

# API 定義列表
apis:
  - name: "api_name"                 # [必要] API 名稱
    method: "GET"                    # [必要] HTTP 方法
    endpoint: "/api/path"            # [必要] API 路徑
    headers: {}                      # [選用] 額外 headers
    params: {}                       # [選用] Query parameters
    body: {}                         # [選用] Request body (JSON)
    weight: 1                        # [選用] 任務權重 (預設 1)
    tags: [smoke, read]              # [選用] 標籤，可用 --tags 過濾
    assertions:                      # [選用] 回應驗證規則
      status_code: 200
      response_fields: ["data"]
      max_response_time_ms: 3000
    extract:                         # [選用] 從回應提取值到上下文
      var_name: "json.path"
    retry:                           # [選用] 個別 API 重試設定 (覆寫全域)
      max_retries: 5
      wait_seconds: 2
      on_status: [500]

# 請求鏈定義列表
flows:
  - name: "flow_name"               # [必要] Flow 名稱
    weight: 3                        # [選用] 任務權重
    tags: [flow, crud]               # [選用] 標籤
    steps:                           # [必要] 步驟列表，每個 step 格式同 api
      - name: "step_name"
        method: "POST"
        endpoint: "/api/path"
        body: {}
        extract:
          var_name: "data.id"
```

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
      limit: 20
    weight: 5
    tags: [smoke, read]
    assertions:
      status_code: 200
      response_fields: ["data"]
      max_response_time_ms: 3000

  - name: "create_user"
    method: "POST"
    endpoint: "/api/users"
    headers:
      Content-Type: "application/json"
    body:
      name: "${RANDOM_NAME}"
      email: "${RANDOM_EMAIL}"
    weight: 1
    tags: [write]
    assertions:
      status_code: 201
    extract:
      new_user_id: "data.id"        # 提取新建使用者的 ID
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
          email: "${RANDOM_EMAIL}"
        assertions:
          status_code: 201
        extract:
          user_id: "data.id"         # 從回應 JSON 提取

      - name: "get_user"
        method: "GET"
        endpoint: "/api/users/${CTX:user_id}"  # 使用提取的值
        assertions:
          status_code: 200

      - name: "update_user"
        method: "PUT"
        endpoint: "/api/users/${CTX:user_id}"
        body:
          name: "${RANDOM_NAME}"
        assertions:
          status_code: 200
```

`extract` 使用 JSON 點號路徑 (dot notation) 來指定提取位置：
- `"data.id"` → 取 `response.data.id`
- `"data.users.0.name"` → 取 `response.data.users[0].name`
- `"token"` → 取 `response.token`

### 認證設定

#### Bearer Token (自動登入/刷新)

```yaml
auth:
  type: bearer
  prefix: "Bearer"                   # Authorization header 前綴 (預設 "Bearer")
  header_name: "Authorization"       # header 名稱 (預設 "Authorization")
  login:
    method: "POST"
    endpoint: "/auth/login"
    body:
      username: "user"
      password: "pass"
    token_path: "data.access_token"  # 從登入回應中提取 token 的 JSON 路徑
  refresh:                           # [選用] Token 刷新設定
    endpoint: "/auth/refresh"
    method: "POST"
    token_path: "data.access_token"
    token_ttl_seconds: 3600          # Token 有效期 (秒)，到期前 60 秒自動刷新
```

#### Basic Auth

```yaml
auth:
  type: basic
  username: "admin"
  password: "secret123"
```

#### API Key

```yaml
auth:
  type: api_key
  header_name: "X-API-Key"          # 自訂 header 名稱 (預設 "X-API-Key")
  key: "your-api-key-here"
```

### CSV / JSON 資料來源

將資料檔案放在 `load_tests/data/` 目錄下。

#### CSV 資料

CSV 檔案會循序讀取 (sequential)，每次請求取下一列，到底後從頭循環：

```csv
# load_tests/data/users.csv
username,password,email
user1,pass1,user1@example.com
user2,pass2,user2@example.com
```

```yaml
apis:
  - name: "login"
    method: "POST"
    endpoint: "/auth/login"
    body:
      username: "${CSV:users.csv:username}"     # 從 CSV 循序讀取
      password: "${CSV:users.csv:password}"
```

#### JSON 資料

JSON 資料使用點號路徑存取，如果值是陣列會隨機取一個：

```json
// load_tests/data/products.json
{
  "product_ids": [101, 102, 103, 104, 105],
  "categories": ["electronics", "clothing", "food"]
}
```

```yaml
apis:
  - name: "get_product"
    method: "GET"
    endpoint: "/products/${JSON:products.json:product_ids}"  # 從陣列隨機取值
    params:
      category: "${JSON:products.json:categories}"
```

### 重試機制

支援指數退避 (exponential backoff)：等待時間依次為 `wait_seconds`、`wait_seconds*2`、`wait_seconds*4`...

```yaml
# 全域重試 (套用到所有沒有自訂 retry 的 API)
retry:
  max_retries: 3
  wait_seconds: 1                    # 初始等待 1s，之後 2s, 4s (指數退避)
  on_status: [502, 503, 504]         # 只在這些狀態碼時重試

# 在單一 API 設定 (覆寫全域設定)
apis:
  - name: "important_api"
    method: "GET"
    endpoint: "/critical"
    retry:
      max_retries: 5
      wait_seconds: 2
      on_status: [500, 502, 503]
```

### 回應驗證 (Assertions)

```yaml
apis:
  - name: "get_data"
    method: "GET"
    endpoint: "/api/data"
    assertions:
      status_code: 200               # 驗證 HTTP 狀態碼
      response_fields:               # 驗證回應 JSON 中包含指定欄位
        - "data"
        - "meta"
      max_response_time_ms: 3000     # 驗證回應時間不超過 3000ms
```

驗證失敗時會在 Locust 報告中標記為 failure，並顯示失敗原因。可透過 `LOCUST_ENABLE_ASSERTIONS=false` 關閉驗證。

### Think Time 模式

```yaml
# 隨機等待 1~3 秒 (預設)
wait_time:
  mode: "between"
  min: 1
  max: 3

# 固定等待 2 秒
wait_time:
  mode: "constant"
  value: 2

# 確保每 5 秒執行一次 (含請求時間)
wait_time:
  mode: "constant_pacing"
  value: 5
```

### 加權任務分配

透過 `weight` 控制各 API/Flow 的呼叫頻率比例：

```yaml
apis:
  - name: "read_api"
    method: "GET"
    endpoint: "/api/data"
    weight: 10                       # 被呼叫的頻率是 write_api 的 10 倍

  - name: "write_api"
    method: "POST"
    endpoint: "/api/data"
    weight: 1

flows:
  - name: "full_crud"
    weight: 3                        # Flow 也支援 weight
    steps: [...]
```

### Tags (標籤篩選)

為 API 或 Flow 加上 tags，執行時可只跑特定標籤：

```yaml
apis:
  - name: "health"
    method: "GET"
    endpoint: "/health"
    tags: [smoke, health]

  - name: "create_order"
    method: "POST"
    endpoint: "/orders"
    tags: [write, order]
```

```bash
# 只執行 smoke 標籤的測試
locust -f load_tests/locustfile.py --tags smoke

# 排除 write 標籤
locust -f load_tests/locustfile.py --exclude-tags write
```

## 環境 Profile

在 `load_tests/profiles/` 建立 YAML 設定檔，透過 `LOCUST_PROFILE` 環境變數切換：

```yaml
# staging.yaml
host: "https://staging-api.example.com"
users: 50
spawn_rate: 5
run_time: "5m"
request_timeout: 30
enable_assertions: true
headers:                             # 額外注入的 headers (會與預設合併)
  X-Environment: "staging"
env:                                 # 設定環境變數
  TOKEN: "staging-token"
  API_KEY: "staging-key"
```

Profile 可覆寫的設定：

| Profile 欄位 | 對應設定 | 說明 |
|--------------|---------|------|
| `host` | `DEFAULT_HOST` | 目標主機 |
| `users` | `DEFAULT_USERS` | 並發使用者數 |
| `spawn_rate` | `DEFAULT_SPAWN_RATE` | 每秒產生使用者數 |
| `run_time` | `DEFAULT_RUN_TIME` | 測試時間 |
| `request_timeout` | `REQUEST_TIMEOUT` | 請求逾時 (秒) |
| `enable_assertions` | `ENABLE_ASSERTIONS` | 啟用回應驗證 |
| `headers` | `DEFAULT_HEADERS` | 合併到預設 headers |
| `env` | 環境變數 | 設定額外環境變數 |

啟用方式：

```bash
LOCUST_PROFILE=staging locust -f load_tests/locustfile.py
LOCUST_PROFILE=prod locust -f load_tests/locustfile.py
```

## 報告與通知

### JSON 報告

```bash
LOCUST_JSON_REPORT=true LOCUST_REPORT_DIR=./reports locust -f load_tests/locustfile.py
```

測試結束後自動產出 `reports/report_YYYYMMDD_HHMMSS.json`，格式如下：

```json
{
  "start_time": "2025-01-01T10:00:00",
  "end_time": "2025-01-01T10:05:00",
  "summary": {
    "total_requests": 15000,
    "total_failures": 12,
    "failure_rate": 0.08,
    "avg_response_time_ms": 156.32,
    "min_response_time_ms": 23,
    "max_response_time_ms": 4521,
    "requests_per_second": 50.12,
    "percentiles": {
      "p50": 120,
      "p75": 180,
      "p90": 310,
      "p95": 450,
      "p99": 1200
    },
    "per_endpoint": {
      "[GET] get_users": {
        "num_requests": 10000,
        "num_failures": 5,
        "avg_response_time_ms": 130.50,
        "min_response_time_ms": 23,
        "max_response_time_ms": 3200,
        "requests_per_second": 33.40
      }
    }
  },
  "requests": [...],
  "failures": [...]
}
```

### Webhook 通知

```bash
LOCUST_WEBHOOK_URL=https://hooks.slack.com/services/... locust -f load_tests/locustfile.py
```

測試**開始**時發送：

```json
{
  "event": "test_start",
  "time": "2025-01-01T10:00:00",
  "message": "壓力測試已開始"
}
```

測試**結束**時發送：

```json
{
  "event": "test_stop",
  "time": "2025-01-01T10:05:00",
  "summary": { ... },
  "message": "壓力測試已結束"
}
```

## 匯出獨立腳本 (拋棄式腳本)

將指定的 YAML 測試定義匯出為完全獨立、自包含的 Python 腳本，不依賴框架，可直接複製到任何地方執行。

### 使用方式

```bash
# 匯出到預設路徑 (同目錄下 {name}_standalone.py)
python export.py load_tests/api_definitions/flow_example.yaml

# 匯出到指定路徑
python export.py load_tests/api_definitions/flow_example.yaml -o /tmp/my_test.py

# 匯出後直接執行
locust -f /tmp/my_test.py --headless -u 10 -r 2 -t 30s
```

### 智慧功能偵測

匯出器會自動分析 YAML 用到的功能，只將必要的程式碼內嵌到腳本中，保持腳本精簡：

| YAML 使用的功能 | 匯出行為 |
|----------------|---------|
| `${RANDOM_*}` / `${TIMESTAMP}` | 內嵌 Faker 資料產生器 + 所有隨機函式 |
| `${CSV:file:column}` | 將 CSV 資料直接嵌入腳本 (無需原始檔案) |
| `${JSON:file:path}` | 將 JSON 資料直接嵌入腳本 (無需原始檔案) |
| `${CTX:var_name}` | 內嵌上下文變數解析邏輯 |
| `auth` | 內嵌認證邏輯 (登入、刷新、Basic、API Key) |
| `retry` | 內嵌重試與指數退避邏輯 |
| `flows` | 產生循序執行的 flow task 方法 |
| `extract` | 內嵌 JSON 值提取邏輯 |

匯出的腳本只需要 `locust` 和 `faker`（如有用到隨機值）即可執行，完全不依賴本框架。

## 變數替換

### 內建隨機資料產生器

| 語法 | 說明 | 範例輸出 |
|------|------|---------|
| `${RANDOM_NAME}` | 隨機姓名 | John Smith |
| `${RANDOM_EMAIL}` | 隨機 Email | john@example.com |
| `${RANDOM_PHONE}` | 隨機電話 | +1-555-0123 |
| `${RANDOM_UUID}` | UUID v4 | 550e8400-e29b-41d4-a716-446655440000 |
| `${RANDOM_INT}` | 隨機整數 (1-10000) | 4273 |
| `${RANDOM_STRING}` | 隨機 10 字元字串 | aBcDeFgHiJ |
| `${RANDOM_USERNAME}` | 隨機使用者名稱 | john_doe42 |
| `${RANDOM_PASSWORD}` | 隨機密碼 (12 字元) | aB3$dEfG9!hI |
| `${RANDOM_IPV4}` | 隨機 IPv4 | 192.168.1.100 |
| `${RANDOM_URL}` | 隨機 URL | https://example.com |
| `${RANDOM_BOOL}` | 隨機 true/false | true |
| `${RANDOM_ADDRESS}` | 隨機地址 | 123 Main St, City |
| `${RANDOM_TEXT}` | 隨機文字 (50 字以內) | Lorem ipsum dolor sit amet |
| `${TIMESTAMP}` | 當前 Unix 時間戳 | 1704067200 |

### 資料來源與上下文

| 語法 | 說明 |
|------|------|
| `${ENV_VAR_NAME}` | 讀取環境變數 |
| `${CTX:var_name}` | 請求鏈上下文變數 (由 extract 產生) |
| `${CSV:file:column}` | 從 CSV 檔案循序讀取指定欄位 |
| `${JSON:file:path}` | 從 JSON 檔案讀取 (陣列會隨機取值) |

### 變數解析順序

1. `${CTX:...}` - 最先解析請求鏈上下文
2. `${CSV:...}` / `${JSON:...}` - 解析外部資料來源
3. `${RANDOM_*}` / `${TIMESTAMP}` - 內建隨機產生器
4. `${VAR_NAME}` - 從上下文 context 查找
5. `${VAR_NAME}` - 從環境變數 `os.getenv()` 查找
6. 以上都找不到則保留原始 `${VAR_NAME}` 不替換

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

## 新增測試定義步驟

1. 在 `load_tests/api_definitions/` 目錄下建立 `.yaml` 檔案
2. 填入 `name` 和 `apis`（或 `flows`）定義
3. 啟動 Locust，框架會自動偵測並載入新檔案
4. 無需修改任何 Python 程式碼

```bash
# 範例: 建立一個新的測試定義
cat > load_tests/api_definitions/my_test.yaml << 'EOF'
name: "my_test"
host: "https://api.example.com"

apis:
  - name: "get_status"
    method: "GET"
    endpoint: "/status"
    assertions:
      status_code: 200
EOF

# 直接執行
locust -f load_tests/locustfile.py --headless -u 5 -r 1 -t 30s
```

## 授權

MIT License
