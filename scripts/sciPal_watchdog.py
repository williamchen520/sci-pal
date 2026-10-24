"""SciPal 服务常驻守护（阶段四-A）。

用途
    MCP 工具全部依赖 SciPal Flask API（默认 127.0.0.1:5000）先跑起来。
    本脚本负责「服务不在就拉起」，消除人工介入：
      · --once   ：探测一次；不通就拉起 api_server.py，打印实际耗时后退出
      · 常驻模式 ：每 10 秒探测一次，不通就拉起，循环

硬约束（违反即设计失效）
    1. 绝不在 MCP 工具调用里同步等待服务启动：冷启动 30–45 秒 + 检索 7–12 秒，
       随时顶到 MCP 的 60 秒上限。启动必须发生在工具调用之外。
    2. 只在不通时拉起；服务存活时**不得**反复重启。
    3. 拉起后进入冷却期（覆盖冷启动窗口），避免预热期间被判定为「不通」而重复拉起抢端口。
    4. 探测必须绕过代理：本机存在 http_proxy，不绕过会把存活的服务误判成没起。

用法
    D:/sciPal/venv_sciPal_py312/Scripts/python.exe scripts/sciPal_watchdog.py --once
    D:/sciPal/venv_sciPal_py312/Scripts/python.exe scripts/sciPal_watchdog.py

说明
    本脚本不 import 任何 SciPal 业务模块，也不改动 api_server.py。
"""

from __future__ import annotations

import argparse
import atexit
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

# Windows 控制台默认 cp1252，中文/emoji 输出会抛 UnicodeEncodeError
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
VENV_PYTHON = PROJECT_ROOT / "venv_sciPal_py312" / "Scripts" / "python.exe"
API_SCRIPT = PROJECT_ROOT / "api_server.py"
LOGS_DIR = PROJECT_ROOT / "logs"
API_LOG = LOGS_DIR / "sciPal_api.log"
LOCK_FILE = LOGS_DIR / "sciPal_watchdog.lock"

BASE_URL = os.environ.get("SCIPAL_BASE_URL", "http://127.0.0.1:5000").rstrip("/")
PROBE_URL = f"{BASE_URL}/api/health"

PROBE_TIMEOUT = 3.0        # 单次探测超时
POLL_INTERVAL = 10.0       # 常驻模式探测间隔
LAUNCH_COOLDOWN = 60.0     # 拉起后冷却期 > 冷启动 30–45s，避免重复拉起
STARTUP_WAIT_TIMEOUT = 180.0  # --once 模式等待就绪上限

_lock_acquired = False


def log(message: str) -> None:
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())}] {message}", flush=True)


def probe() -> bool:
    """探测 /api/health。必须用 ProxyHandler({}) 绕开本机 http_proxy，否则会误判。"""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(PROBE_URL, timeout=PROBE_TIMEOUT) as response:
            return 200 <= response.status < 400
    except Exception:
        return False


def pid_alive(pid: int) -> bool:
    """Windows 下探测进程是否存活（不引入 psutil）。"""
    try:
        completed = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return str(pid) in completed.stdout
    except Exception:
        return False


def acquire_lock() -> bool:
    """单实例锁：保证只有一个 watchdog，防止重复拉起抢端口。"""
    global _lock_acquired
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    if LOCK_FILE.exists():
        try:
            holder = int(LOCK_FILE.read_text(encoding="utf-8").strip())
        except Exception:
            holder = 0
        if holder and holder != os.getpid() and pid_alive(holder):
            log(f"已有 watchdog 实例在运行（PID {holder}），本实例退出以避免重复拉起")
            return False
    try:
        LOCK_FILE.write_text(str(os.getpid()), encoding="utf-8")
    except Exception as exc:
        log(f"写入锁文件失败：{exc}")
        return False
    _lock_acquired = True
    atexit.register(release_lock)
    return True


def release_lock() -> None:
    global _lock_acquired
    if not _lock_acquired:
        return
    try:
        if LOCK_FILE.exists():
            holder = int(LOCK_FILE.read_text(encoding="utf-8").strip())
            if holder == os.getpid():
                LOCK_FILE.unlink()
    except Exception:
        pass
    _lock_acquired = False


def launch() -> bool:
    """以 detached 方式拉起 api_server.py，stdout/stderr 落 logs/sciPal_api.log。"""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    if not VENV_PYTHON.exists():
        log(f"虚拟环境解释器不存在：{VENV_PYTHON}")
        return False

    flags = 0
    if os.name == "nt":
        flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(
            subprocess, "DETACHED_PROCESS", 0
        )

    # detached 子进程的 stdout/stderr 重定向到文件时，Windows 默认编码是 cp1252，
    # api_server.py 启动打印的 emoji（api_server.py:2035）会抛 UnicodeEncodeError 直接退出。
    # 这里显式强制 UTF-8 —— 不改业务代码，只修正启动环境。
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"

    try:
        handle = open(API_LOG, "a", encoding="utf-8")
        subprocess.Popen(
            [str(VENV_PYTHON), str(API_SCRIPT)],
            cwd=str(PROJECT_ROOT),
            env=env,
            stdout=handle,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            creationflags=flags,
        )
    except Exception as exc:
        log(f"拉起失败：{exc}")
        return False

    log(f"已拉起 api_server.py（日志：{API_LOG}）")
    return True


def run_once() -> int:
    if probe():
        log(f"SciPal API 已在运行（{BASE_URL}），无需拉起")
        return 0

    log(f"SciPal API 未运行，正在拉起 api_server.py ...")
    started = time.time()
    if not launch():
        return 1

    while time.time() - started < STARTUP_WAIT_TIMEOUT:
        time.sleep(1.0)
        if probe():
            elapsed = time.time() - started
            log(f"服务已就绪，实际耗时 {elapsed:.1f}s（冷启动通常 30–45s）")
            return 0

    log(f"已等待 {STARTUP_WAIT_TIMEOUT:.0f}s 仍未就绪，请检查日志：{API_LOG}")
    return 1


def run_daemon() -> None:
    if not acquire_lock():
        return

    log(f"watchdog 常驻启动：每 {POLL_INTERVAL:.0f}s 探测 {PROBE_URL}（PID {os.getpid()}）")
    last_launch = 0.0
    was_down = False

    try:
        while True:
            alive = probe()
            if alive:
                if was_down:
                    log(f"服务已恢复（{BASE_URL}）")
                    was_down = False
            else:
                if not was_down:
                    log(f"服务不通（{PROBE_URL}）")
                    was_down = True
                if time.time() - last_launch >= LAUNCH_COOLDOWN:
                    if launch():
                        last_launch = time.time()
                        log(f"进入 {LAUNCH_COOLDOWN:.0f}s 冷却期，等待冷启动完成")
                else:
                    remaining = LAUNCH_COOLDOWN - (time.time() - last_launch)
                    log(f"冷却期内（剩 {remaining:.0f}s），暂不重复拉起")
            time.sleep(POLL_INTERVAL)
    except KeyboardInterrupt:
        log("收到中断信号，退出")
    finally:
        release_lock()


def main() -> None:
    parser = argparse.ArgumentParser(description="SciPal 服务常驻守护")
    parser.add_argument(
        "--once",
        action="store_true",
        help="只探测一次：不通就拉起并等待就绪，打印实际耗时后退出",
    )
    args = parser.parse_args()

    if args.once:
        raise SystemExit(run_once())

    run_daemon()


if __name__ == "__main__":
    main()
