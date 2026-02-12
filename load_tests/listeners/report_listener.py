"""自訂事件監聽器 - 即時統計與報告產出

支援:
    - JSON 報告輸出
    - Webhook 通知 (Slack / 自訂 URL)
    - 即時統計收集

使用方式:
    在 locustfile.py 中 import 即自動註冊:
        from load_tests.listeners.report_listener import setup_listeners
        setup_listeners(env)
"""

import os
import json
import time
import logging
import datetime
from collections import defaultdict

import locust.env
from locust import events

logger = logging.getLogger(__name__)

# 統計資料收集器
_stats_collector = {
    "start_time": None,
    "end_time": None,
    "requests": [],
    "failures": [],
    "summary": {},
}


@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """測試開始時觸發"""
    _stats_collector["start_time"] = datetime.datetime.now().isoformat()
    _stats_collector["requests"] = []
    _stats_collector["failures"] = []
    logger.info("壓力測試開始")

    webhook_url = os.getenv("LOCUST_WEBHOOK_URL")
    if webhook_url:
        _send_webhook(webhook_url, {
            "event": "test_start",
            "time": _stats_collector["start_time"],
            "message": "壓力測試已開始",
        })


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """測試結束時觸發，產出報告"""
    _stats_collector["end_time"] = datetime.datetime.now().isoformat()

    # 產出摘要
    _stats_collector["summary"] = _build_summary(environment)

    # 寫出 JSON 報告
    report_dir = os.getenv("LOCUST_REPORT_DIR", "reports")
    if os.getenv("LOCUST_JSON_REPORT", "false").lower() == "true":
        _write_json_report(report_dir)

    # Webhook 通知
    webhook_url = os.getenv("LOCUST_WEBHOOK_URL")
    if webhook_url:
        _send_webhook(webhook_url, {
            "event": "test_stop",
            "time": _stats_collector["end_time"],
            "summary": _stats_collector["summary"],
            "message": "壓力測試已結束",
        })

    logger.info("壓力測試結束")


@events.request.add_listener
def on_request(request_type, name, response_time, response_length,
               exception, context, **kwargs):
    """每次請求完成時觸發"""
    record = {
        "method": request_type,
        "name": name,
        "response_time_ms": response_time,
        "response_length": response_length,
        "timestamp": datetime.datetime.now().isoformat(),
        "success": exception is None,
    }

    if exception:
        record["error"] = str(exception)
        _stats_collector["failures"].append(record)

    # 限制記憶體使用，只保留最近 10000 筆
    if len(_stats_collector["requests"]) < 10000:
        _stats_collector["requests"].append(record)


def _build_summary(environment):
    """從 Locust 統計資料建構摘要"""
    stats = environment.runner.stats
    summary = {
        "total_requests": stats.total.num_requests,
        "total_failures": stats.total.num_failures,
        "avg_response_time_ms": round(stats.total.avg_response_time, 2),
        "min_response_time_ms": stats.total.min_response_time or 0,
        "max_response_time_ms": stats.total.max_response_time or 0,
        "requests_per_second": round(stats.total.current_rps, 2),
        "failure_rate": round(
            stats.total.fail_ratio * 100, 2
        ) if stats.total.num_requests > 0 else 0,
        "percentiles": {},
        "per_endpoint": {},
    }

    # 各百分位數
    if stats.total.num_requests > 0:
        for p in [50, 75, 90, 95, 99]:
            summary["percentiles"][f"p{p}"] = stats.total.get_response_time_percentile(p / 100.0)

    # 各 endpoint 統計
    for entry in stats.entries.values():
        key = f"[{entry.method}] {entry.name}"
        summary["per_endpoint"][key] = {
            "num_requests": entry.num_requests,
            "num_failures": entry.num_failures,
            "avg_response_time_ms": round(entry.avg_response_time, 2),
            "min_response_time_ms": entry.min_response_time or 0,
            "max_response_time_ms": entry.max_response_time or 0,
            "requests_per_second": round(entry.current_rps, 2),
        }

    return summary


def _write_json_report(report_dir):
    """將統計資料寫出為 JSON 報告檔案"""
    os.makedirs(report_dir, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    file_path = os.path.join(report_dir, f"report_{timestamp}.json")

    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(_stats_collector, f, ensure_ascii=False, indent=2)
        logger.info("JSON 報告已寫入: %s", file_path)
    except Exception as e:
        logger.error("寫入 JSON 報告失敗: %s", e)


def _send_webhook(url, payload):
    """發送 Webhook 通知"""
    try:
        import urllib.request
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status < 400:
                logger.info("Webhook 通知發送成功: %s", url)
            else:
                logger.warning("Webhook 回傳 HTTP %d", resp.status)
    except Exception as e:
        logger.warning("Webhook 通知發送失敗: %s", e)


def get_stats_collector():
    """取得統計資料收集器 (供外部使用)"""
    return _stats_collector
