"""SciPal 服务常驻守护（阶段四-A，阶段六修订）。

用途
    MCP 工具全部依赖 SciPal Flask API（默认 127.0.0.1:5000）先跑起来。
    本脚本负责「服务不在就拉起」，消除人工介入：
      · --once   ：探测一次；不通就拉起 api_server.py，打印实际耗时后退出
      · 常驻模式 ：每 10 秒探测一次，不通就拉起，循环

⚠️ 重要区别
    --once 拉起的服务**会随终端退出被回收**（父终端关闭时进程树被清理）。
    需要持久运行请安装计划任务：
        powershell -File scripts/install_autostart.ps1

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
import json
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

# Windows 进程创建标志
CREATE_BREAKAWAY_FROM_JOB = 0x01000000  # 允许子进程脱离父进程所在的 Job

_once_breakaway_note = "未知"

_lock_acquired = False


# ---------------------------------------------------------------------------
# Windows 进程信息（ctypes，避免依赖 psutil / 反复起 PowerShell）
# ---------------------------------------------------------------------------

if os.name == "nt":
    import ctypes
    from ctypes import wintypes

    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _kernel32.OpenProcess.restype = wintypes.HANDLE
    _kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    _kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

    def process_start_time(pid: int) -> int | None:
        """进程创建时间（FILETIME，100ns 精度，自 1601 起）。用于防止 PID 复用误判。"""
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = _kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return None
        try:
            creation = wintypes.FILETIME()
            exit_time = wintypes.FILETIME()
            kernel = wintypes.FILETIME()
            user = wintypes.FILETIME()
            ok = _kernel32.GetProcessTimes(
                handle,
                ctypes.byref(creation),
                ctypes.byref(exit_time),
                ctypes.byref(kernel),
                ctypes.byref(user),
            )
            if not ok:
                return None
            return (creation.dwHighDateTime << 32) | creation.dwLowDateTime
        finally:
            _kernel32.CloseHandle(handle)
else:  # pragma: no cover - 仅 Windows 使用
    def process_start_time(pid: int) -> int | None:
        return None


# ---------------------------------------------------------------------------
# 基础能力
# ---------------------------------------------------------------------------


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


def command_line_has_watchdog(pid: int) -> bool:
    """回退校验：该 PID 的命令行是否确实属于本脚本（防止 PID 被无关进程复用）。"""
    try:
        completed = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                f"(Get-CimInstance Win32_Process -Filter 'ProcessId={pid}').CommandLine",
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        return "sciPal_watchdog.py" in (completed.stdout or "")
    except Exception:
        return False


# ---------------------------------------------------------------------------
# 单实例锁：PID + 进程创建时间（避免 PID 复用误判）
# ---------------------------------------------------------------------------


def read_lock() -> dict | None:
    """读取锁文件。兼容旧的「纯数字 PID」格式。"""
    try:
        # utf-8-sig：兼容用 PowerShell Set-Content 写入时带的 BOM
        raw = LOCK_FILE.read_text(encoding="utf-8-sig").strip()
    except Exception:
        return None
    if not raw:
        return None
    try:
        data = json.loads(raw)
        if isinstance(data, dict) and "pid" in data:
            return data
    except json.JSONDecodeError:
        pass
    try:
        return {"pid": int(raw), "start": None}
    except ValueError:
        return None


def write_lock() -> bool:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    payload = {"pid": os.getpid(), "start": process_start_time(os.getpid())}
    try:
        LOCK_FILE.write_text(json.dumps(payload), encoding="utf-8")
        return True
    except Exception as exc:
        log(f"写入锁文件失败：{exc}")
        return False


def lock_holder_alive(holder: dict) -> bool:
    """判断锁持有者是否真的是一个存活的 watchdog 进程。

    仅凭 PID 会误判：PID 会被系统复用，旧锁里的 PID 可能已经属于别的进程。
    因此优先比对「进程创建时间」，拿不到时回退到命令行校验。
    """
    pid = holder.get("pid")
    if not isinstance(pid, int) or pid <= 0:
        return False
    if not pid_alive(pid):
        return False

    recorded_start = holder.get("start")
    actual_start = process_start_time(pid)
    if recorded_start is not None and actual_start is not None:
        # 创建时间一致 → 是同一个进程；不一致 → PID 已被复用
        return int(recorded_start) == int(actual_start)

    return command_line_has_watchdog(pid)


def acquire_lock() -> bool:
    """单实例锁：保证只有一个 watchdog，防止重复拉起抢端口。"""
    global _lock_acquired
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    holder = read_lock()
    if holder and lock_holder_alive(holder):
        if holder.get("pid") != os.getpid():
            log(f"已有 watchdog 实例在运行（PID {holder.get('pid')}），本实例退出以避免重复拉起")
            return False
    elif holder:
        log(f"发现过期锁（PID {holder.get('pid')} 已不存在或已被复用），接管")

    if not write_lock():
        return False
    _lock_acquired = True
    atexit.register(release_lock)
    return True


def release_lock() -> None:
    global _lock_acquired
    if not _lock_acquired:
        return
    try:
        holder = read_lock()
        if holder and holder.get("pid") == os.getpid():
            LOCK_FILE.unlink()
    except Exception:
        pass
    _lock_acquired = False


# ---------------------------------------------------------------------------
# 拉起
# ---------------------------------------------------------------------------


def _creation_flags(with_breakaway: bool) -> int:
    flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(
        subprocess, "DETACHED_PROCESS", 0
    )
    if with_breakaway and os.name == "nt":
        flags |= CREATE_BREAKAWAY_FROM_JOB
    return flags


def launch() -> bool:
    """以 detached 方式拉起 api_server.py，stdout/stderr 落 logs/sciPal_api.log。

    优先带 CREATE_BREAKAWAY_FROM_JOB（脱离父终端所在的 Job，减少「终端退出即被杀」）；
    若所在 Job 未开启 breakaway 权限，系统会拒绝 → 自动降级为普通 detached。
    """
    global _once_breakaway_note
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    if not VENV_PYTHON.exists():
        log(f"虚拟环境解释器不存在：{VENV_PYTHON}")
        return False

    # detached 子进程的 stdout/stderr 重定向到文件时，Windows 默认编码是 cp1252，
    # api_server.py 启动打印的 emoji（api_server.py:2035）会抛 UnicodeEncodeError 直接退出。
    # 这里显式强制 UTF-8 —— 不改业务代码，只修正启动环境。
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"

    for with_breakaway in (True, False):
        try:
            handle = open(API_LOG, "a", encoding="utf-8")
            subprocess.Popen(
                [str(VENV_PYTHON), str(API_SCRIPT)],
                cwd=str(PROJECT_ROOT),
                env=env,
                stdout=handle,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                creationflags=_creation_flags(with_breakaway),
            )
        except OSError as exc:
            if with_breakaway:
                log(
                    "CREATE_BREAKAWAY_FROM_JOB 不可用"
                    f"（winerror={getattr(exc, 'winerror', None)}: {exc}），降级为普通 detached"
                )
                _once_breakaway_note = "失败（Job 不允许 breakaway，已降级）"
                continue
            log(f"拉起失败：{exc}")
            return False
        else:
            _once_breakaway_note = "已启用" if with_breakaway else "未启用"
            break

    log(f"已拉起 api_server.py（日志：{API_LOG}；breakaway={_once_breakaway_note}）")
    return True


# ---------------------------------------------------------------------------
# 两种模式
# ---------------------------------------------------------------------------

ONCE_EPILOGUE = (
    "提示：本方式拉起的服务会随终端退出被回收，持久运行请装计划任务：\n"
    "      powershell -File scripts/install_autostart.ps1"
)


def run_once() -> int:
    if probe():
        log(f"SciPal API 已在运行（{BASE_URL}），无需拉起")
        print(ONCE_EPILOGUE, flush=True)
        return 0

    log("SciPal API 未运行，正在拉起 api_server.py ...")
    started = time.time()
    if not launch():
        print(ONCE_EPILOGUE, flush=True)
        return 1

    while time.time() - started < STARTUP_WAIT_TIMEOUT:
        time.sleep(1.0)
        if probe():
            elapsed = time.time() - started
            log(f"服务已就绪，实际耗时 {elapsed:.1f}s（冷启动通常 30–45s）")
            print(ONCE_EPILOGUE, flush=True)
            return 0

    log(f"已等待 {STARTUP_WAIT_TIMEOUT:.0f}s 仍未就绪，请检查日志：{API_LOG}")
    print(ONCE_EPILOGUE, flush=True)
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
        help="只探测一次：不通就拉起并等待就绪，打印实际耗时后退出（临时应急，非持久）",
    )
    args = parser.parse_args()

    if args.once:
        raise SystemExit(run_once())

    run_daemon()


if __name__ == "__main__":
    main()
