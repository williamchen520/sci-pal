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

日志（V33.17 · 看门狗日志落盘）
    文件：`logs/sciPal_watchdog.log` —— **绝对路径**，由 `PROJECT_ROOT` 派生（计划任务的
        cwd 可能是 `C:/Windows/System32`，相对路径会写丢）。可用环境变量
        `SCIPAL_WATCHDOG_LOG` 覆盖，仅供验收时临时指向别处，不参与生产逻辑。
    格式：与 stdout 完全一致 —— `[YYYY-MM-DD HH:MM:SS] msg`，UTF-8，追加写。
    双写：同一行同时进 stdout 与文件；**每次写入 open/close**，不复用长期句柄
        （日志量极小，而长期句柄在进程被强杀时可能丢缓冲）。
    轮转：超过 `LOG_MAX_BYTES`（5 MB）时轮转为 `.1` / `.2`，保留 `LOG_BACKUPS`（2）份，
        超出丢最老；轮转失败不影响运行。
    启动标记：每次启动写 RUN MARKER（pid / BASE_URL / python 路径 / **脚本 mtime + size**
        / 上次退出是否干净），用于回答「跑的是不是修好的那版」。
    降级：日志不可写（磁盘满 / 权限不足 / 目录被删）时**只向 stderr 提示一次**，
        之后静默走 stdout，主循环照常运行 —— 日志失败绝不能让管家死掉。

    判断实例堆积只需看两个信号：**多条「已拉起」没有对应的「服务已就绪」**，以及
    **`listening count > 1`**（此时会额外打一条 `⚠️ 检测到多实例监听`）。

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
from contextlib import contextmanager
from datetime import datetime
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

# T4-1: **拉起互斥守卫** —— 与上面的「常驻单实例锁」是两件事，别混用：
#   · LOCK_FILE   ：只允许一个 daemon 存活（长期持有）
#   · LAUNCH_GUARD：只允许一个进程执行「launch + wait_until_ready」（短命，毫秒~分钟级）
# 分开的原因：daemon 活着时 `--once` 也**必须**被挡住，但它不能因此去抢 daemon 的锁；
# 反过来 daemon 每轮拉起也要挡 `--once`。
LAUNCH_GUARD_FILE = LOGS_DIR / "sciPal_launch.guard"

# L-1: 看门狗自身日志 —— **绝对路径**，由 PROJECT_ROOT / LOGS_DIR 派生。
# 计划任务的工作目录可能是 C:\Windows\System32，用相对路径会把日志写到别处（甚至丢）。
# SCIPAL_WATCHDOG_LOG 仅供验收时指向临时文件，不参与生产逻辑。
_env_log = os.environ.get("SCIPAL_WATCHDOG_LOG", "").strip()
WATCHDOG_LOG = (
    Path(_env_log).expanduser().resolve()
    if _env_log
    else (LOGS_DIR / "sciPal_watchdog.log").resolve()
)

LOG_MAX_BYTES = 5 * 1024 * 1024  # L-4: 轮转阈值（验收时可临时调小）
LOG_BACKUPS = 2                  # 保留 .1 / .2 两份历史，超出丢最老

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


_log_file_broken = False


def _log_backup_path(index: int) -> Path:
    """sciPal_watchdog.log.1 / .2（用字符串拼接，避免 with_suffix 对多段后缀报错）。"""
    return WATCHDOG_LOG.parent / f"{WATCHDOG_LOG.name}.{index}"


def _rotate_if_needed() -> None:
    """L-4: 按大小轮转（纯标准库 os.replace）。失败不影响运行，只向 stderr 提示。"""
    try:
        if not WATCHDOG_LOG.exists() or WATCHDOG_LOG.stat().st_size < LOG_MAX_BYTES:
            return
    except OSError:
        return

    try:
        oldest = _log_backup_path(LOG_BACKUPS)
        if oldest.exists():
            oldest.unlink()
        for index in range(LOG_BACKUPS - 1, 0, -1):
            src = _log_backup_path(index)
            if src.exists():
                os.replace(src, _log_backup_path(index + 1))
        os.replace(WATCHDOG_LOG, _log_backup_path(1))
    except OSError as exc:
        print(
            f"[WARN] 看门狗日志轮转失败（继续写原文件）：{exc}",
            file=sys.stderr,
            flush=True,
        )


def log(message: str) -> None:
    """写一行日志：stdout + 文件双写（L-1）。

    - 文件写入**每次 open/close**，不复用长期句柄：日志量极小（健康时只在状态切换打点），
      而长期句柄在进程被强杀时可能丢缓冲；每次 open 追加能保证「写进去的就是盘上的」。
    - 写失败**绝不抛、也不刷屏**：第一次失败向 stderr 提示一次，之后静默走 stdout，
      主循环照跑 —— 磁盘满 / 权限不足 / 目录被删，都不许让管家死掉。
    """
    global _log_file_broken
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())}] {message}"
    print(line, flush=True)

    if _log_file_broken:
        return
    try:
        _rotate_if_needed()
        WATCHDOG_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(WATCHDOG_LOG, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except Exception as exc:
        _log_file_broken = True
        print(
            f"[WARN] 看门狗日志写入失败，后续只输出 stdout（{WATCHDOG_LOG}）：{exc}",
            file=sys.stderr,
            flush=True,
        )


def _human_size(num: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if num < 1024 or unit == "GB":
            return f"{num:.1f} {unit}" if unit != "B" else f"{int(num)} B"
        num /= 1024
    return f"{num:.1f} GB"


def _last_log_time() -> str:
    """读日志最后一行的时间戳（只读尾部 4 KB，不整文件读）。"""
    try:
        with open(WATCHDOG_LOG, "rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - 4096))
            tail = handle.read().decode("utf-8", errors="replace")
    except OSError as exc:
        return f"不可读（{exc}）"
    for line in reversed(tail.splitlines()):
        if line.startswith("[") and len(line) >= 20:
            return line[1:20]
    return "（空）"


def _log_writable() -> bool:
    """L-5: 日志可写探针 —— 写一次空内容（不改变文件大小、不留垃圾行）。"""
    try:
        WATCHDOG_LOG.parent.mkdir(parents=True, exist_ok=True)
        before = WATCHDOG_LOG.stat().st_size if WATCHDOG_LOG.exists() else 0
        with open(WATCHDOG_LOG, "a", encoding="utf-8") as handle:
            handle.write("")
        after = WATCHDOG_LOG.stat().st_size if WATCHDOG_LOG.exists() else 0
        return after >= before
    except Exception:
        return False


def _run_marker(mode: str, previous_lock: dict | None) -> None:
    """L-2: RUN MARKER —— 回答「跑的是不是修好的那版」。

    关键是脚本自身的 mtime + size：本机踩过两次「改了代码但没重启守护进程」，
    每次都靠比进程 CreationDate 才发现，写进日志后自查成本归零。
    """
    script = Path(__file__).resolve()
    try:
        stat = script.stat()
        script_mtime = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(stat.st_mtime))
        script_size = stat.st_size
    except OSError:
        script_mtime, script_size = "?", "?"

    if previous_lock is None:
        last_exit = "clean（无残留锁）"
    else:
        holder_pid = previous_lock.get("pid")
        if holder_pid and pid_alive(int(holder_pid)):
            last_exit = f"running（锁被 PID {holder_pid} 持有且存活）"
        else:
            last_exit = f"unclean（残留锁 PID {holder_pid} 已死：疑似异常退出/被强杀）"

    log("=== watchdog start ===")
    log(f"mode={mode}  pid={os.getpid()}")
    log(f"BASE_URL={BASE_URL}  PROBE_URL={PROBE_URL}")
    log(f"python={sys.version.split()[0]}  exe={sys.executable}")
    log(f"script={script}")
    log(f"script mtime={script_mtime}  size={script_size}B")
    log(f"last exit={last_exit}")
    log(f"log file={WATCHDOG_LOG}")
    log("=== watchdog start end ===")


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
            pids = listening_pids()
            log(
                f"服务已就绪（等待 {time.time() - started:.1f}s，"
                f"listening count={len(pids)}，pids={pids}）"
            )
            # L-3: count > 1 就是「已经堆积」的关键告警信号
            if len(pids) > 1:
                log(f"⚠️ 检测到多实例监听：{len(pids)} 个进程同时占用端口 {pids}")
            return True
        time.sleep(READY_POLL_INTERVAL)

    pids = listening_pids()
    log(
        f"等待 {timeout:.0f}s 仍未通过探针，服务可能异常"
        f"（port_listening={port_listening()}，listening count={len(pids)}，pids={pids}）"
    )
    if len(pids) > 1:
        log(f"⚠️ 检测到多实例监听：{len(pids)} 个进程同时占用端口 {pids}")
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
# T4-1 拉起互斥守卫（logs/sciPal_launch.guard）
#
# 为什么需要它：daemon 的 LOCK_FILE 只挡「两个 daemon」，`--once` 以前既不读锁
# 也不看端口，`probe()` 一失败就 `launch()`。实测同一秒两个 `--once` 各拉一个，
# 而 Windows 的 SO_REUSEADDR 让两个 Flask **都能绑定 5000、都能通过 health 200**，
# 于是 T-2 刚焊死的「唯一一把解析锁」被进程边界打穿。
#
# 守卫生效范围：**只包住 `launch() + wait_until_ready()` 这一段**。
# ---------------------------------------------------------------------------


def read_launch_guard() -> dict | None:
    """读取守卫文件；不存在 / 空 / 非法 JSON 都返回 None。"""
    try:
        raw = LAUNCH_GUARD_FILE.read_text(encoding="utf-8-sig").strip()
    except Exception:
        return None
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) and "pid" in data else None


def launch_guard_holder_alive(holder: dict) -> bool:
    """守卫持有者是否是**同一个还活着的**看门狗进程。

    判据与 LOCK_FILE 一致：PID 存活 + 创建时间一致（防 PID 复用）；
    拿不到创建时间时退回命令行校验（`sciPal_watchdog.py`）。
    """
    pid = holder.get("pid")
    if not isinstance(pid, int) or pid <= 0:
        return False
    if not pid_alive(pid):
        return False

    recorded_start = holder.get("start")
    actual_start = process_start_time(pid)
    if recorded_start is not None and actual_start is not None:
        return int(recorded_start) == int(actual_start)

    return command_line_has_watchdog(pid)


def _create_guard_exclusive() -> bool:
    """原子创建守卫文件（`O_CREAT|O_EXCL`）：谁先创建谁持有。"""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        {
            "pid": os.getpid(),
            "start": process_start_time(os.getpid()),
            "at": datetime.now().isoformat(timespec="seconds"),
        },
        ensure_ascii=False,
    )
    try:
        fd = os.open(str(LAUNCH_GUARD_FILE), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return False
    except Exception as exc:  # 权限/磁盘等：不吞
        log(f"创建拉起守卫失败：{exc}")
        return False
    try:
        os.write(fd, payload.encode("utf-8"))
    finally:
        os.close(fd)
    return True


def release_launch_guard() -> None:
    """释放守卫（只删自己写的，别人接管走的不动）。"""
    holder = read_launch_guard()
    if holder and holder.get("pid") != os.getpid():
        return
    try:
        LAUNCH_GUARD_FILE.unlink()
    except Exception:
        pass


def _read_guard_after_contention(timeout: float = 1.0) -> dict | None:
    """创建失败后读守卫内容 —— 给赢家一点时间把 JSON 写进去。

    `O_CREAT|O_EXCL` 创建与写入之间有一个极短的空文件窗口；此处若立刻判
    「读不出来 = stale」就会把赢家踢掉，两边一起拉起（正是要修的问题）。
    """
    deadline = time.time() + timeout
    while True:
        holder = read_launch_guard()
        if holder is not None:
            return holder
        if time.time() >= deadline:
            return None
        time.sleep(0.05)


@contextmanager
def launch_guard():
    """拉起互斥：同一时刻只允许一个进程执行 `launch + wait_until_ready`。

    yield:
        True  → 已持有守卫（退出 with 时自动删除文件）
        False → 守卫被占 / 接管失败，**调用方不得 launch**，本轮跳过

    stale 判定：持有者 PID 已死、或 PID 已被复用（创建时间不符）→ 接管，
    避免强杀留下的尸检文件把看门狗永久锁死。
    """
    if _create_guard_exclusive():
        log(f"取得拉起守卫（PID {os.getpid()}）")
        try:
            yield True
        finally:
            release_launch_guard()
        return

    holder = _read_guard_after_contention()
    if holder and launch_guard_holder_alive(holder):
        log(
            f"拉起守卫被占（PID {holder.get('pid')} 正在拉起/等待就绪），本轮跳过"
        )
        yield False
        return

    # 读不出内容且文件很新：可能是赢家还没写完 JSON，保守让路（不抢）
    if holder is None:
        try:
            age = time.time() - LAUNCH_GUARD_FILE.stat().st_mtime
        except OSError:
            age = None
        if age is not None and age < 5:
            log("拉起守卫刚被创建（内容未就绪），本轮跳过")
            yield False
            return

    log(f"发现过期拉起守卫（{holder or '内容不可读'}），接管")
    try:
        LAUNCH_GUARD_FILE.unlink()
    except Exception:
        pass

    if not _create_guard_exclusive():
        log("接管拉起守卫失败（被其他进程抢先），本轮跳过")
        yield False
        return

    log(f"已接管并重新取得拉起守卫（PID {os.getpid()}）")
    try:
        yield True
    finally:
        release_launch_guard()


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
    # L-3: 拉起后立刻快照端口 —— 若此时 count>1，说明已经堆了
    pids = listening_pids()
    log(
        f"拉起后快照：listening count={len(pids)}，pids={pids}；"
        f"接下来阻塞等待就绪，上限 {STARTUP_WAIT_TIMEOUT:.0f}s"
    )
    if len(pids) > 1:
        log(f"⚠️ 检测到多实例监听：{len(pids)} 个进程同时占用端口 {pids}")
    return proc.pid


# ---------------------------------------------------------------------------
# 两种模式
# ---------------------------------------------------------------------------

ONCE_EPILOGUE = (
    "提示：本方式拉起的服务会随终端退出被回收，持久运行请装计划任务：\n"
    "      powershell -File scripts/install_autostart.ps1"
)


def run_once() -> int:
    """临时应急拉起，**任何路径都不许堆出第二个实例**（T4-1）。

    三道闸，顺序不能换（越便宜、越有权威的越前面）：
      ① 服务已就绪          → 无需拉起
      ② 有 daemon 在运行    → 拉起是它的职责，`--once` 绝不抢先
      ③ 端口已有人在监听    → 那是在冷启动/僵死，再拉一个就是双实例
    三道都过才进「拉起守卫」→ launch() → 等就绪。

    退出码口径：**只要有「不 launch」的正当理由就 exit 0**；
    只有「尝试拉起但未在超时内就绪」才 exit 1。
    """
    _run_marker("once", read_lock())

    # ① 服务已就绪
    if probe():
        log(f"SciPal API 已在运行（{BASE_URL}），无需拉起")
        print(ONCE_EPILOGUE, flush=True)
        return 0

    # ② 常驻看门狗在跑 → 拉起归它管
    holder = read_lock()
    if holder and lock_holder_alive(holder) and holder.get("pid") != os.getpid():
        log(
            f"已有看门狗在运行（PID {holder.get('pid')}），--once 不重复拉起"
            f"（探针当前失败，拉起/重试由该常驻进程负责）"
        )
        print(ONCE_EPILOGUE, flush=True)
        return 0

    # ③ 端口已被占用（探针未通过 = 在冷启动或僵死）
    if port_listening():
        pids = listening_pids()
        log(
            f"端口已有人在监听（可能在冷启动），--once 不重复拉起"
            f"（listening count={len(pids)}，pids={pids}）"
        )
        print(ONCE_EPILOGUE, flush=True)
        return 0

    # ④ 进守卫：launch + 等就绪 全程互斥
    with launch_guard() as acquired:
        if not acquired:
            print(ONCE_EPILOGUE, flush=True)
            return 0

        # 拿到守卫后复查：等待期间别人可能已经拉起并开始监听
        if port_listening():
            pids = listening_pids()
            log(
                f"取得守卫后复查：端口已被占用，取消本次拉起"
                f"（listening count={len(pids)}，pids={pids}）"
            )
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
    # L-2: 启动前先快照锁，供 RUN MARKER 判定「上次是否干净退出」
    previous = read_lock()
    if not acquire_lock():
        return

    _run_marker("daemon", previous)
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
                pids = listening_pids()
                log(f"服务不通（{PROBE_URL}，listening pids={pids}）")
                was_down = True

            # ── F-3：端口已有实例在监听但探针失败 → 它在冷启动/僵死，别再拉一个 ──
            if port_listening():
                pids = listening_pids()
                log(
                    "端口已有人在监听但探针未通过（可能在冷启动），本轮**不拉起**，继续等"
                    f"（listening count={len(pids)}，pids={pids}）"
                )
                time.sleep(POLL_INTERVAL)
                continue

            # ── 兜底冷却：上次拉起等满超时仍未就绪 ──
            if last_launch and (time.time() - last_launch) < LAUNCH_COOLDOWN:
                remaining = LAUNCH_COOLDOWN - (time.time() - last_launch)
                log(f"上次拉起未就绪，兜底冷却中（剩 {remaining:.0f}s）")
                time.sleep(POLL_INTERVAL)
                continue

            # ── 拉起 + T4-1 守卫 + F-1：阻塞等待就绪，期间绝不进入下一轮 ──
            with launch_guard() as acquired:
                if not acquired:
                    # 另一个进程（daemon 另一路 / --once）正在拉起或等就绪
                    time.sleep(POLL_INTERVAL)
                    continue

                # 拿到守卫后复查端口：等待守卫期间别人可能已经拉起来了
                if port_listening():
                    pids = listening_pids()
                    log(
                        "取得守卫后复查：端口已被占用，本轮不拉起"
                        f"（listening count={len(pids)}，pids={pids}）"
                    )
                    time.sleep(POLL_INTERVAL)
                    continue

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

    # T4-1: 拉起守卫 + 实例数（判单实例只认监听 PID 个数，不认 health 200）
    guard = read_launch_guard()
    print(f"launch guard      : {guard}")
    if guard and guard.get("pid"):
        guard_alive = launch_guard_holder_alive(guard)
        print(
            f"launch guard alive: {guard_alive}"
            + ("" if guard_alive else "（stale，下次拉起会接管）")
        )
    print(f"instance count    : {len(pids)}（pids={pids}）")

    # L-5: 日志可观测性（保留上面全部原有字段）
    try:
        log_size = WATCHDOG_LOG.stat().st_size if WATCHDOG_LOG.exists() else 0
    except OSError:
        log_size = 0
    writable = _log_writable()
    print(f"log file          : {WATCHDOG_LOG}")
    print(
        f"log size          : {_human_size(log_size)}"
        f"（阈值 {_human_size(LOG_MAX_BYTES)}，保留 {LOG_BACKUPS} 份）"
    )
    print(f"log last line at  : {_last_log_time()}")
    print(f"log writable      : {writable}")
    if not writable:
        print(f"  [WARN] 日志文件不可写：{WATCHDOG_LOG}（不影响 verdict）")

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
