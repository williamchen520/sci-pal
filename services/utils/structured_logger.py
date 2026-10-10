"""
Sci-Pal 结构化日志与监控模块 V33.6

用途：提供 JSON 格式结构化日志和简单的监控指标收集。
- 结构化日志：JSON 格式，包含 timestamp、level、module、event、details、duration 等
- 日志级别：DEBUG / INFO / WARNING / ERROR / CRITICAL
- 模块过滤：支持按模块名过滤日志
- 日志查询：按时间范围/级别/模块/关键词查询历史日志
- 监控指标：请求数、错误率、平均耗时、各模块调用次数

设计原则：
- 结构化：所有日志都是 JSON，方便后续分析和查询
- 低开销：日志写入异步或批量，不影响主流程性能
- 可查询：历史日志可按条件查询，方便排查问题
- 可监控：关键指标自动收集，提供概览统计
"""

import json
import time
import uuid
import threading
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional
from dataclasses import dataclass, field, asdict
from enum import Enum
from collections import defaultdict, deque


# =============================================================================
# 日志级别
# =============================================================================

class LogLevel(str, Enum):
    """日志级别"""
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"

    @property
    def numeric(self) -> int:
        return {
            "debug": 10,
            "info": 20,
            "warning": 30,
            "error": 40,
            "critical": 50,
        }[self.value]


# =============================================================================
# 日志记录
# =============================================================================

@dataclass
class LogEntry:
    """结构化日志记录"""
    log_id: str = field(default_factory=lambda: f"log_{uuid.uuid4().hex[:12]}")
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    timestamp_unix: float = field(default_factory=time.time)
    level: str = LogLevel.INFO.value
    module: str = ""
    event: str = ""
    message: str = ""
    details: dict = field(default_factory=dict)
    duration_seconds: float = 0.0
    request_id: str = ""
    user_id: str = ""
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


# =============================================================================
# 监控指标
# =============================================================================

@dataclass
class MetricPoint:
    """指标数据点"""
    timestamp: float = field(default_factory=time.time)
    value: float = 0.0
    tags: dict = field(default_factory=dict)


@dataclass
class MonitorStats:
    """监控统计信息"""
    total_requests: int = 0
    total_errors: int = 0
    error_rate: float = 0.0
    avg_duration_seconds: float = 0.0
    p50_duration: float = 0.0
    p95_duration: float = 0.0
    p99_duration: float = 0.0
    by_module: dict[str, int] = field(default_factory=dict)
    by_event: dict[str, int] = field(default_factory=dict)
    by_level: dict[str, int] = field(default_factory=dict)
    time_window_seconds: int = 3600


# =============================================================================
# 结构化日志记录器
# =============================================================================

class StructuredLogger:
    """
    结构化日志记录器

    用法：
        logger = StructuredLogger(module='review_generator')

        # 记录普通日志
        logger.info('开始生成综述', details={'review_id': 'rev_001'})

        # 记录带耗时的日志
        with logger.timer('generate_section', details={'section_id': 'sec_001'}):
            # ... 执行操作 ...
            pass

        # 记录错误
        logger.error('生成失败', error=e, details={'review_id': 'rev_001'})

        # 查询历史日志
        logs = logger.query(level='error', module='review_generator', limit=50)
    """

    def __init__(
        self,
        module: str = "default",
        storage_dir: Optional[str] = None,
        max_file_size_mb: int = 50,
        max_files: int = 10,
        min_level: str = LogLevel.INFO.value,
        console_output: bool = True,
    ):
        """
        Args:
            module: 模块名
            storage_dir: 存储目录，默认 data/logs/
            max_file_size_mb: 单个日志文件最大大小（MB）
            max_files: 最多保留的日志文件数
            min_level: 最低日志级别
            console_output: 是否同时输出到控制台
        """
        self.module = module
        self.min_level = LogLevel(min_level).numeric
        self.console_output = console_output
        self.max_file_size = max_file_size_mb * 1024 * 1024
        self.max_files = max_files

        # 存储目录
        if storage_dir:
            self.storage_dir = Path(storage_dir)
        else:
            self.storage_dir = Path(__file__).parent.parent.parent / "data" / "logs"
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        # 内存缓存（最近的日志）
        self._log_buffer: deque[LogEntry] = deque(maxlen=10000)
        self._lock = threading.Lock()

        # 监控指标
        self._metrics_lock = threading.Lock()
        self._request_count = 0
        self._error_count = 0
        self._durations: deque[float] = deque(maxlen=10000)
        self._module_counts: dict[str, int] = defaultdict(int)
        self._event_counts: dict[str, int] = defaultdict(int)
        self._level_counts: dict[str, int] = defaultdict(int)

        # 当前日志文件
        self._current_file = self._get_current_log_file()

    # -------------------------------------------------------------------------
    # 日志记录方法
    # -------------------------------------------------------------------------

    def debug(self, message: str, **kwargs):
        """记录 DEBUG 日志"""
        self._log(LogLevel.DEBUG, message, **kwargs)

    def info(self, message: str, **kwargs):
        """记录 INFO 日志"""
        self._log(LogLevel.INFO, message, **kwargs)

    def warning(self, message: str, **kwargs):
        """记录 WARNING 日志"""
        self._log(LogLevel.WARNING, message, **kwargs)

    def error(self, message: str, error: Optional[Exception] = None, **kwargs):
        """记录 ERROR 日志"""
        details = kwargs.pop("details", {})
        if error:
            details["error_type"] = type(error).__name__
            details["error_message"] = str(error)
        self._log(LogLevel.ERROR, message, details=details, **kwargs)

    def critical(self, message: str, error: Optional[Exception] = None, **kwargs):
        """记录 CRITICAL 日志"""
        details = kwargs.pop("details", {})
        if error:
            details["error_type"] = type(error).__name__
            details["error_message"] = str(error)
        self._log(LogLevel.CRITICAL, message, details=details, **kwargs)

    def timer(self, event: str, **kwargs):
        """
        上下文管理器，自动记录耗时

        用法：
            with logger.timer('generate_section', details={'section_id': 'sec_001'}):
                # ... 执行操作 ...
                pass
        """
        return _TimerContext(self, event, **kwargs)

    # -------------------------------------------------------------------------
    # 日志查询
    # -------------------------------------------------------------------------

    def query(
        self,
        level: str = "",
        module: str = "",
        event: str = "",
        keyword: str = "",
        since_seconds: int = 3600,
        limit: int = 100,
    ) -> list[dict]:
        """
        查询历史日志

        Args:
            level: 日志级别过滤
            module: 模块名过滤
            event: 事件名过滤
            keyword: 关键词搜索（在 message 和 details 中搜索）
            since_seconds: 查询最近多少秒的日志
            limit: 最多返回条数

        Returns:
            日志记录列表（按时间倒序）
        """
        since_time = time.time() - since_seconds
        results = []

        with self._lock:
            for entry in reversed(self._log_buffer):
                if entry.timestamp_unix < since_time:
                    break
                if level and entry.level != level:
                    continue
                if module and entry.module != module:
                    continue
                if event and entry.event != event:
                    continue
                if keyword:
                    text = entry.message + json.dumps(entry.details, ensure_ascii=False)
                    if keyword.lower() not in text.lower():
                        continue
                results.append(entry.to_dict())
                if len(results) >= limit:
                    break

        return results

    def get_recent(self, n: int = 20) -> list[dict]:
        """获取最近的 N 条日志"""
        with self._lock:
            return [entry.to_dict() for entry in list(self._log_buffer)[-n:][::-1]]

    # -------------------------------------------------------------------------
    # 监控指标
    # -------------------------------------------------------------------------

    def get_stats(self, time_window_seconds: int = 3600) -> MonitorStats:
        """获取监控统计信息"""
        with self._metrics_lock:
            total = self._request_count
            errors = self._error_count
            durations = list(self._durations)[-1000:] if self._durations else []

            avg_duration = sum(durations) / len(durations) if durations else 0.0
            sorted_durations = sorted(durations)
            p50 = sorted_durations[int(len(sorted_durations) * 0.5)] if sorted_durations else 0.0
            p95 = sorted_durations[int(len(sorted_durations) * 0.95)] if sorted_durations else 0.0
            p99 = sorted_durations[int(len(sorted_durations) * 0.99)] if sorted_durations else 0.0

            return MonitorStats(
                total_requests=total,
                total_errors=errors,
                error_rate=errors / total if total > 0 else 0.0,
                avg_duration_seconds=avg_duration,
                p50_duration=p50,
                p95_duration=p95,
                p99_duration=p99,
                by_module=dict(self._module_counts),
                by_event=dict(self._event_counts),
                by_level=dict(self._level_counts),
                time_window_seconds=time_window_seconds,
            )

    def reset_stats(self):
        """重置监控统计"""
        with self._metrics_lock:
            self._request_count = 0
            self._error_count = 0
            self._durations.clear()
            self._module_counts.clear()
            self._event_counts.clear()
            self._level_counts.clear()

    # -------------------------------------------------------------------------
    # 内部方法
    # -------------------------------------------------------------------------

    def _log(self, level: LogLevel, message: str, **kwargs):
        """记录日志（内部方法）"""
        if level.numeric < self.min_level:
            return

        entry = LogEntry(
            level=level.value,
            module=self.module,
            event=kwargs.pop("event", ""),
            message=message,
            details=kwargs.pop("details", {}),
            duration_seconds=kwargs.pop("duration_seconds", 0.0),
            request_id=kwargs.pop("request_id", ""),
            user_id=kwargs.pop("user_id", ""),
            metadata=kwargs,
        )

        # 写入内存缓存
        with self._lock:
            self._log_buffer.append(entry)

        # 更新监控指标
        with self._metrics_lock:
            self._request_count += 1
            if level.numeric >= LogLevel.ERROR.numeric:
                self._error_count += 1
            if entry.duration_seconds > 0:
                self._durations.append(entry.duration_seconds)
            self._module_counts[entry.module] += 1
            if entry.event:
                self._event_counts[entry.event] += 1
            self._level_counts[entry.level] += 1

        # 写入文件
        self._write_to_file(entry)

        # 控制台输出
        if self.console_output:
            self._print_to_console(entry)

    def _write_to_file(self, entry: LogEntry):
        """写入日志文件"""
        try:
            # 检查文件大小，必要时轮转
            if self._current_file.is_file() and self._current_file.stat().st_size > self.max_file_size:
                self._rotate_log_files()

            with open(self._current_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")
        except Exception as e:
            # 日志写入失败不应该影响主流程
            pass

    def _rotate_log_files(self):
        """轮转日志文件"""
        try:
            # 重命名现有文件
            for i in range(self.max_files - 1, 0, -1):
                src = self.storage_dir / f"app_{i}.log"
                dst = self.storage_dir / f"app_{i + 1}.log"
                if src.is_file():
                    if dst.is_file():
                        dst.unlink()
                    src.rename(dst)

            # 当前文件重命名为 app_1.log
            if self._current_file.is_file():
                self._current_file.rename(self.storage_dir / "app_1.log")

            # 创建新的当前文件
            self._current_file = self._get_current_log_file()
        except Exception:
            pass

    def _get_current_log_file(self) -> Path:
        """获取当前日志文件路径"""
        return self.storage_dir / "app.log"

    def _print_to_console(self, entry: LogEntry):
        """输出到控制台"""
        level_icons = {
            "debug": "🔍",
            "info": "✅",
            "warning": "⚠️",
            "error": "❌",
            "critical": "🔥",
        }
        icon = level_icons.get(entry.level, "")
        time_str = entry.timestamp[11:23]  # 只取时间部分
        print(f"{icon} [{time_str}] [{entry.level.upper()}] [{entry.module}] {entry.message}")


# =============================================================================
# 计时器上下文管理器
# =============================================================================

class _TimerContext:
    """计时器上下文管理器"""

    def __init__(self, logger: StructuredLogger, event: str, **kwargs):
        self.logger = logger
        self.event = event
        self.kwargs = kwargs
        self.start_time = 0.0

    def __enter__(self):
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = time.time() - self.start_time
        if exc_type:
            self.logger.error(
                f"{self.event} 失败",
                error=exc_val,
                event=self.event,
                duration_seconds=duration,
                **self.kwargs,
            )
        else:
            self.logger.info(
                f"{self.event} 完成",
                event=self.event,
                duration_seconds=duration,
                **self.kwargs,
            )
        return False  # 不吞异常


# =============================================================================
# 全局单例
# =============================================================================

_logger_instances: dict[str, StructuredLogger] = {}
_logger_lock = threading.Lock()


def get_logger(module: str = "default") -> StructuredLogger:
    """获取指定模块的日志记录器单例"""
    global _logger_instances
    if module not in _logger_instances:
        with _logger_lock:
            if module not in _logger_instances:
                _logger_instances[module] = StructuredLogger(module=module)
    return _logger_instances[module]
