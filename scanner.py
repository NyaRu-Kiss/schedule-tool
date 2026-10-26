"""
日程效率工具 - 后台扫描线程

每 SCAN_INTERVAL_SECONDS 秒触发一次 scan_and_remind。
Flask app 启动时通过 start_scan_thread() 启动。
"""

import threading
import time
import logging

from config import SCAN_INTERVAL_SECONDS
from remind import scan_and_remind

log = logging.getLogger("scanner")

_stop_event = threading.Event()


def _loop():
    log.info("提醒扫描线程已启动 (间隔 %ds)", SCAN_INTERVAL_SECONDS)
    while not _stop_event.is_set():
        try:
            n = scan_and_remind()
            if n:
                log.info("本次推送了 %d 条提醒", n)
        except Exception as e:
            log.exception("扫描线程异常: %s", e)
        _stop_event.wait(SCAN_INTERVAL_SECONDS)


def start_scan_thread():
    t = threading.Thread(target=_loop, name="reminder-scanner", daemon=True)
    t.start()
    return t


def stop_scan_thread():
    _stop_event.set()