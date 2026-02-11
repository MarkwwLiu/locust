import logging

from locust import HttpUser, between

from load_tests.config.settings import Settings

logger = logging.getLogger(__name__)


class BaseUser(HttpUser):
    """壓力測試基礎 User 類別

    提供共用的:
    - 預設 headers 注入
    - 回應驗證
    - 錯誤處理與日誌
    """

    abstract = True
    host = Settings.DEFAULT_HOST
    wait_time = between(1, 3)

    def on_start(self):
        """使用者開始時的初始化"""
        self.default_headers = Settings.DEFAULT_HEADERS.copy()
        logger.info("使用者 %s 開始執行壓力測試", self.__class__.__name__)

    def on_stop(self):
        """使用者結束時的清理"""
        logger.info("使用者 %s 結束壓力測試", self.__class__.__name__)

    def make_request(self, method, endpoint, name=None, **kwargs):
        """統一的請求方法，自動注入 headers 與驗證回應

        Args:
            method: HTTP 方法 (GET, POST, PUT, DELETE 等)
            endpoint: API 路徑
            name: Locust 報告中顯示的名稱
            **kwargs: 傳遞給 requests 的額外參數
                - headers: 額外的 headers (會與預設 headers 合併)
                - assertions: 回應驗證規則
                - params: query parameters
                - json: request body

        Returns:
            Response 物件
        """
        # 合併 headers
        headers = self.default_headers.copy()
        if "headers" in kwargs:
            headers.update(kwargs.pop("headers"))

        # 取出 assertions (不傳給 requests)
        assertions = kwargs.pop("assertions", None)

        # 設定 timeout
        kwargs.setdefault("timeout", Settings.REQUEST_TIMEOUT)

        request_name = name or f"[{method}] {endpoint}"

        with self.client.request(
            method=method,
            url=endpoint,
            headers=headers,
            name=request_name,
            catch_response=True,
            **kwargs,
        ) as response:
            self._validate_response(response, assertions, request_name)
            return response

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
