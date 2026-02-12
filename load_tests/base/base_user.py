import logging
import time

from locust import HttpUser, between

from load_tests.config.settings import Settings

logger = logging.getLogger(__name__)


class BaseUser(HttpUser):
    """壓力測試基礎 User 類別

    提供共用的:
    - 預設 headers 注入
    - 回應驗證
    - 錯誤處理與日誌
    - 請求鏈 (Response Extraction & Chaining)
    - 認證管理
    - 重試機制
    """

    abstract = True
    host = Settings.DEFAULT_HOST
    wait_time = between(1, 3)

    # 認證設定 (由 generator 注入)
    auth_config = None

    # 重試設定
    retry_config = None

    def on_start(self):
        """使用者開始時的初始化"""
        self.default_headers = Settings.DEFAULT_HEADERS.copy()
        # 請求鏈上下文: 儲存 extract 出來的值供後續請求使用
        self.context = {}
        # 認證初始化
        self._init_auth()
        logger.info("使用者 %s 開始執行壓力測試", self.__class__.__name__)

    def on_stop(self):
        """使用者結束時的清理"""
        logger.info("使用者 %s 結束壓力測試", self.__class__.__name__)

    def _init_auth(self):
        """根據 auth_config 執行認證流程"""
        if not self.auth_config:
            return

        auth_type = self.auth_config.get("type", "bearer")

        if auth_type == "bearer" and "login" in self.auth_config:
            self._do_login()
        elif auth_type == "basic":
            import base64
            username = self.auth_config.get("username", "")
            password = self.auth_config.get("password", "")
            token = base64.b64encode(f"{username}:{password}".encode()).decode()
            self.default_headers["Authorization"] = f"Basic {token}"
        elif auth_type == "api_key":
            header_name = self.auth_config.get("header_name", "X-API-Key")
            api_key = self.auth_config.get("key", "")
            self.default_headers[header_name] = api_key

    def _do_login(self):
        """執行登入取得 Token"""
        login_cfg = self.auth_config["login"]
        method = login_cfg.get("method", "POST").upper()
        endpoint = login_cfg.get("endpoint", "/auth/login")
        body = login_cfg.get("body", {})
        token_path = login_cfg.get("token_path", "token")

        try:
            resp = self.client.request(
                method=method,
                url=endpoint,
                json=body,
                headers={"Content-Type": "application/json"},
            )
            if resp.status_code < 400:
                json_resp = resp.json()
                token = self._extract_json_value(json_resp, token_path)
                if token:
                    header_name = self.auth_config.get("header_name", "Authorization")
                    prefix = self.auth_config.get("prefix", "Bearer")
                    self.default_headers[header_name] = f"{prefix} {token}"
                    self.context["AUTH_TOKEN"] = token
                    self._token_obtained_at = time.time()
                    logger.info("使用者 %s 登入成功", self.__class__.__name__)
                else:
                    logger.error("無法從回應中提取 token (path: %s)", token_path)
            else:
                logger.error("登入失敗，HTTP %d", resp.status_code)
        except Exception as e:
            logger.error("登入時發生錯誤: %s", e)

    def _refresh_token_if_needed(self):
        """檢查並在需要時刷新 Token"""
        if not self.auth_config or "refresh" not in self.auth_config:
            return
        refresh_cfg = self.auth_config["refresh"]
        ttl = refresh_cfg.get("token_ttl_seconds", 3600)
        if not hasattr(self, "_token_obtained_at"):
            return
        if time.time() - self._token_obtained_at < ttl - 60:
            return
        # Token 即將過期，刷新
        endpoint = refresh_cfg.get("endpoint", "/auth/refresh")
        method = refresh_cfg.get("method", "POST").upper()
        token_path = refresh_cfg.get("token_path", "token")
        try:
            resp = self.client.request(
                method=method,
                url=endpoint,
                headers=self.default_headers.copy(),
            )
            if resp.status_code < 400:
                json_resp = resp.json()
                token = self._extract_json_value(json_resp, token_path)
                if token:
                    header_name = self.auth_config.get("header_name", "Authorization")
                    prefix = self.auth_config.get("prefix", "Bearer")
                    self.default_headers[header_name] = f"{prefix} {token}"
                    self.context["AUTH_TOKEN"] = token
                    self._token_obtained_at = time.time()
                    logger.info("Token 刷新成功")
        except Exception as e:
            logger.error("刷新 Token 時發生錯誤: %s", e)

    @staticmethod
    def _extract_json_value(data, path):
        """從 JSON 物件中依路徑提取值

        支援點號分隔路徑，如 "data.access_token"
        """
        keys = path.split(".")
        current = data
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            elif isinstance(current, list) and key.isdigit():
                current = current[int(key)]
            else:
                return None
        return current

    def make_request(self, method, endpoint, name=None, **kwargs):
        """統一的請求方法，自動注入 headers 與驗證回應

        Args:
            method: HTTP 方法 (GET, POST, PUT, DELETE 等)
            endpoint: API 路徑
            name: Locust 報告中顯示的名稱
            **kwargs: 傳遞給 requests 的額外參數
                - headers: 額外的 headers (會與預設 headers 合併)
                - assertions: 回應驗證規則
                - extract: 從回應中提取值到 context
                - params: query parameters
                - json: request body

        Returns:
            Response 物件
        """
        # 檢查是否需要刷新 Token
        self._refresh_token_if_needed()

        # 合併 headers
        headers = self.default_headers.copy()
        if "headers" in kwargs:
            headers.update(kwargs.pop("headers"))

        # 取出非 requests 參數
        assertions = kwargs.pop("assertions", None)
        extract = kwargs.pop("extract", None)
        retry = kwargs.pop("retry", None) or self.retry_config

        # 設定 timeout
        kwargs.setdefault("timeout", Settings.REQUEST_TIMEOUT)

        request_name = name or f"[{method}] {endpoint}"

        # 重試機制
        max_retries = 0
        retry_wait = 1
        retry_on_status = []
        if retry:
            max_retries = retry.get("max_retries", 0)
            retry_wait = retry.get("wait_seconds", 1)
            retry_on_status = retry.get("on_status", [])

        response = None
        for attempt in range(max_retries + 1):
            with self.client.request(
                method=method,
                url=endpoint,
                headers=headers,
                name=request_name,
                catch_response=True,
                **kwargs,
            ) as resp:
                # 判斷是否需要重試
                if (
                    attempt < max_retries
                    and retry_on_status
                    and resp.status_code in retry_on_status
                ):
                    logger.warning(
                        "%s 第 %d 次嘗試回傳 HTTP %d，%ds 後重試",
                        request_name, attempt + 1, resp.status_code, retry_wait,
                    )
                    resp.success()  # 不算失敗，等重試
                    time.sleep(retry_wait)
                    retry_wait *= 2  # 指數退避
                    continue

                self._validate_response(resp, assertions, request_name)

                # 從回應中提取值到 context
                if extract:
                    self._extract_from_response(resp, extract, request_name)

                response = resp
                break

        return response

    def _extract_from_response(self, response, extract_rules, request_name):
        """從回應中提取值並存入 self.context

        Args:
            response: HTTP 回應物件
            extract_rules: dict，key 為 context 變數名，value 為 JSON path
            request_name: 請求名稱 (用於日誌)
        """
        try:
            json_resp = response.json()
            for var_name, json_path in extract_rules.items():
                value = self._extract_json_value(json_resp, json_path)
                if value is not None:
                    self.context[var_name] = value
                    logger.debug(
                        "%s: 提取 %s = %s", request_name, var_name, value
                    )
                else:
                    logger.warning(
                        "%s: 無法從回應中提取 '%s' (path: %s)",
                        request_name, var_name, json_path,
                    )
        except Exception as e:
            logger.warning("%s: 提取回應值失敗: %s", request_name, e)

    def _validate_response(self, response, assertions, request_name):
        """驗證回應是否符合預期

        Args:
            response: Locust 回應物件
            assertions: 驗證規則 dict
            request_name: 請求名稱 (用於日誌)
        """
        if not Settings.ENABLE_ASSERTIONS or not assertions:
            if response.status_code >= 400:
                response.failure(
                    f"{request_name} 回傳 HTTP {response.status_code}"
                )
            else:
                response.success()
            return

        # 驗證 status_code
        expected_status = assertions.get("status_code")
        if expected_status and response.status_code != expected_status:
            response.failure(
                f"{request_name} 預期狀態碼 {expected_status}，"
                f"實際為 {response.status_code}"
            )
            return

        # 驗證回應 body 包含特定欄位
        expected_fields = assertions.get("response_fields")
        if expected_fields:
            try:
                json_resp = response.json()
                for field in expected_fields:
                    if field not in json_resp:
                        response.failure(
                            f"{request_name} 回應中缺少欄位: {field}"
                        )
                        return
            except Exception:
                response.failure(f"{request_name} 回應非有效 JSON")
                return

        # 驗證回應時間
        max_response_time = assertions.get("max_response_time_ms")
        if max_response_time and response.elapsed.total_seconds() * 1000 > max_response_time:
            response.failure(
                f"{request_name} 回應時間 "
                f"{response.elapsed.total_seconds() * 1000:.0f}ms "
                f"超過上限 {max_response_time}ms"
            )
            return

        response.success()
