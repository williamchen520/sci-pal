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
import socket
import subprocess
import sys
import time
import urllib.parse
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
READY_POLL_INTERVAL = 2.0  # 拉起后「等待就绪」期间的探测间隔

# F-1（本工单核心）：daemon 拉起后**阻塞等待就绪**（与 --once 对齐），
# 就绪之后才清零状态。这个常量只剩兜底用途 —— 当「拉起后等满
# STARTUP_WAIT_TIMEOUT 仍未就绪」时，用它避免下一轮立刻再拉一个。
#
# 原来的 60 s 是错的：实测冷启动 ≈76 s（2026-10-25 07:34 / 07:39），
# 冷却一过探针仍失败 → 再拉一个 → Windows SO_REUSEADDR 允许重复绑定
# → 每 60~70 s 多一个实例，滚雪球到 8 个。
LAUNCH_COOLDOWN = 180.0
STARTUP_WAIT_TIMEOUT = 180.0  # --once 与 daemon 共用的「等待就绪」上限

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


def _host_port() -> tuple[str, int]:
    parsed = urllib.parse.urlparse(BASE_URL)
    return (parsed.hostname or "127.0.0.1", parsed.port or 5000)


def port_listening(timeout: float = 0.6) -> bool:
    """F-3: 端口上是否已经有进程在监听（TCP 层，与 probe 的 HTTP 层互补）。

    为什么必须分开判：Windows 的 SO_REUSEADDR 允许多个进程绑同一端口，
    「探针失败」不等于「没有进程在监听」—— 很可能只是那个进程还在冷启动。
    拉起前不做这个区分，就会在冷启动窗口里反复叠加实例。
    """
    host, port = _host_port()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def listening_pids(port: int | None = None) -> list[int]:
    """F-4: 列出正在监听该端口的 PID（用 netstat -ano 解析，纯标准库）。"""
    _, default_port = _host_port()
    port = port or default_port
    try:
        completed = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True,
            text=True,
            encoding="mbcs",
            errors="replace",
            timeout=15,
        )
    except Exception as exc:  # 不吞：打印出来
        log(f"读取 netstat 失败：{exc}")
        return []

    pids: set[int] = set()
    needle = f":{port}"
    for line in (completed.stdout or "").splitlines():
        if needle not in line or "LISTENING" not in line.upper():
            continue
        parts = line.split()
        if parts and parts[-1].isdigit():
            pids.add(int(parts[-1]))
    return sorted(pids)


def wait_until_ready(timeout: float = STARTUP_WAIT_TIMEOUT) -> bool:
    """F-1: 拉起后阻塞等待服务真正就绪（与 --once 一致）。

    这是本工单的核心修复：旧版 daemon 拉起后立刻 sleep(10s) 就进入下一轮，
    60 s 冷却一过、探针还失败（冷启动 ~76 s）就再拉一个 —— 实例滚雪球。
    现在无论冷启动多久，都等它到底（或等满 timeout），期间绝不再拉起。
    """
    started = time.time()
    while time.time() - started < timeout:
        if probe():
            log(f"服务已就绪（等待 {time.time() - started:.1f}s）")
            return True
        time.sleep(READY_POLL_INTERVAL)
    log(f"等待 {timeout:.0f}s 仍未通过探针，服务可能异常（端口监听={port_listening()}）")
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


def launch() -> int | None:
    """以 detached 方式拉起 api_server.py，返回子进程 pid；失败返回 None。

    优先带 CREATE_BREAKAWAY_FROM_JOB（脱离父终端所在的 Job，减少「终端退出即被杀」）；
    若所在 Job 未开启 breakaway 权限，系统会拒绝 → 自动降级为普通 detached。
    """
    global _once_breakaway_note
    proc: subprocess.Popen | None = None
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
            proc = subprocess.Popen(
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
            return None
        else:
            _once_breakaway_note = "已启用" if with_breakaway else "未启用"
            break

    if proc is None:
        return None
    log(
        f"已拉起 api_server.py（pid={proc.pid}，日志：{API_LOG}；"
        f"breakaway={_once_breakaway_note}）"
    )
    return proc.pid


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
    if launch() is None:
        print(ONCE_EPILOGUE, flush=True)
        return 1

    if wait_until_ready(STARTUP_WAIT_TIMEOUT):
        log(f"服务已就绪，实际耗时 {time.time() - started:.1f}s")
        print(ONCE_EPILOGUE, flush=True)
        return 0

    log(f"已等待 {STARTUP_WAIT_TIMEOUT:.0f}s 仍未就绪，请检查日志：{API_LOG}")
    print(ONCE_EPILOGUE, flush=True)
    return 1


def run_daemon() -> None:
    if not acquire_lock():
        return

    log(f"watchdog 常驻启动：每 {POLL_INTERVAL:.0f}s 探测 {PROBE_URL}（PID {os.getpid()}）")
    log(
        "拉起策略：先判端口占用（F-3）→ 拉起后**阻塞等待就绪**，"
        f"上限 {STARTUP_WAIT_TIMEOUT:.0f}s（F-1）→ 失败才进 {LAUNCH_COOLDOWN:.0f}s 兜底冷却"
    )
    last_launch = 0.0
    was_down = False

    try:
        while True:
            # ── 健康 ──
            if probe():
                if was_down:
                    log(f"服务已恢复（{BASE_URL}）")
                    was_down = False
                last_launch = 0.0  # 健康时清零：冷却只服务于「拉起后未就绪」的失败场景
                time.sleep(POLL_INTERVAL)
                continue

            if not was_down:
                log(f"服务不通（{PROBE_URL}）")
                was_down = True

            # ── F-3：端口已有实例在监听但探针失败 → 它在冷启动/僵死，别再拉一个 ──
            if port_listening():
                log("端口已有人在监听但探针未通过（可能在冷启动），本轮**不拉起**，继续等")
                time.sleep(POLL_INTERVAL)
                continue

            # ── 兜底冷却：上次拉起等满超时仍未就绪 ──
            if last_launch and (time.time() - last_launch) < LAUNCH_COOLDOWN:
                remaining = LAUNCH_COOLDOWN - (time.time() - last_launch)
                log(f"上次拉起未就绪，兜底冷却中（剩 {remaining:.0f}s）")
                time.sleep(POLL_INTERVAL)
                continue

            # ── 拉起 + F-1：阻塞等待就绪，期间绝不进入下一轮 ──
            pid = launch()
            if pid is None:
                time.sleep(POLL_INTERVAL)
                continue

            last_launch = time.time()
            if wait_until_ready(STARTUP_WAIT_TIMEOUT):
                last_launch = 0.0
                was_down = False
            # 未就绪：保留 last_launch，下一轮先走端口检查 + 兜底冷却

            time.sleep(POLL_INTERVAL)
    except KeyboardInterrupt:
        log("收到中断信号，退出")
    finally:
        release_lock()


def show_status() -> int:
    """F-4: 一次性自检 —— 锁 / 监听数 / 探针，不用再手敲 netstat。"""
    ok = probe()
    pids = listening_pids()
    holder = read_lock()

    print("=== SciPal watchdog 状态 ===")
    print(f"BASE_URL          : {BASE_URL}")
    print(f"probe             : {'OK' if ok else 'FAIL'}")
    print(f"port_listening    : {port_listening()}")
    print(f"listening pids    : {pids}")
    print(f"listening count   : {len(pids)}")
    print(f"lock              : {holder}")
    if holder and holder.get("pid"):
        print(f"lock holder alive : {pid_alive(holder['pid'])}")

    healthy = ok and len(pids) <= 1
    print(f"verdict           : {'OK' if healthy else 'DEGRADED（可能多实例或服务异常）'}")
    return 0 if healthy else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="SciPal 服务常驻守护")
    parser.add_argument(
        "--once",
        action="store_true",
        help="只探测一次：不通就拉起并等待就绪，打印实际耗时后退出（临时应急，非持久）",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="自检：打印锁内容、监听 5000 的 PID 列表、探针结果后退出（F-4）",
    )
    args = parser.parse_args()

    if args.status:
        raise SystemExit(show_status())

    if args.once:
        raise SystemExit(run_once())

    run_daemon()


if __name__ == "__main__":
    main()
