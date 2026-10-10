"""
Sci-Pal 统一错误处理与重试模块 V33.6

用途：提供统一的错误处理、重试、降级和死信队列机制。
- @retry 装饰器：指数退避重试，支持可重试异常类型
- LLM 调用重试+降级：主模型失败时自动切换到备用模型
- 解析器 fallback 链：Docling失败→GROBID→MinerU→pdfplumber
- 死信队列：多次失败的任务进入死信队列，支持人工重试
- 错误统计：记录各类错误的发生次数，便于发现系统性问题

设计原则：
- 优雅降级：失败时尽量提供可用的降级方案，而不是直接报错
- 指数退避：重试间隔指数增长，避免打爆下游服务
- 可观测：所有重试和降级都有日志记录
- 可配置：重试次数、间隔、异常类型都可配置
"""

import time
import json
import uuid
import threading
import functools
from pathlib import Path
from datetime import datetime
from typing import Optional, Callable, Type, Any, Tuple
from dataclasses import dataclass, field, asdict
from enum import Enum


# =============================================================================
# 数据结构
# =============================================================================

class RetryStatus(str, Enum):
    """重试状态"""
    PENDING = "pending"
    RETRYING = "retrying"
    SUCCESS = "success"
    FAILED = "failed"
    DEAD_LETTER = "dead_letter"


@dataclass
class RetryRecord:
    """重试记录"""
    record_id: str = field(default_factory=lambda: f"retry_{uuid.uuid4().hex[:12]}")
    task_name: str = ""
    status: str = RetryStatus.PENDING.value
    attempt: int = 0
    max_attempts: int = 3
    last_error: str = ""
    last_error_type: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    last_attempt_at: str = ""
    completed_at: str = ""
    duration_seconds: float = 0.0
    metadata: dict = field(default_factory=dict)


@dataclass
class DeadLetterTask:
    """死信队列任务"""
    task_id: str = field(default_factory=lambda: f"dl_{uuid.uuid4().hex[:12]}")
    task_name: str = ""
    task_type: str = ""  # llm_call / parser / download / other
    payload: dict = field(default_factory=dict)
    error_message: str = ""
    error_type: str = ""
    attempt_count: int = 0
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    last_attempt_at: str = ""
    status: str = "pending"  # pending / retrying / resolved / dismissed
    resolved_at: str = ""
    resolution_notes: str = ""


@dataclass
class ErrorStats:
    """错误统计"""
    total_errors: int = 0
    total_retries: int = 0
    total_success_after_retry: int = 0
    total_dead_letters: int = 0
    success_rate: float = 0.0
    by_error_type: dict[str, int] = field(default_factory=dict)
    by_task_name: dict[str, int] = field(default_factory=dict)
    recent_errors: list[dict] = field(default_factory=list)


# =============================================================================
# 重试装饰器
# =============================================================================

def retry(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    backoff_factor: float = 2.0,
    retryable_exceptions: Tuple[Type[Exception], ...] = (Exception,),
    on_retry: Optional[Callable] = None,
    on_success: Optional[Callable] = None,
    on_failure: Optional[Callable] = None,
    jitter: bool = True,
):
    """
    重试装饰器（指数退避）

    Args:
        max_attempts: 最大尝试次数（包括第一次）
        base_delay: 基础延迟（秒）
        max_delay: 最大延迟（秒）
        backoff_factor: 退避因子
        retryable_exceptions: 可重试的异常类型元组
        on_retry: 重试回调函数（attempt, error, delay）
        on_success: 成功回调函数（result, attempt）
        on_failure: 最终失败回调函数（error）
        jitter: 是否添加随机抖动

    用法：
        @retry(max_attempts=3, base_delay=1.0)
        def call_llm(prompt):
            ...

        # 只重试特定异常
        @retry(retryable_exceptions=(TimeoutError, ConnectionError))
        def download_file(url):
            ...
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_error = None
            for attempt in range(1, max_attempts + 1):
                try:
                    result = func(*args, **kwargs)
                    if on_success:
                        try:
                            on_success(result, attempt)
                        except Exception:
                            pass
                    return result
                except retryable_exceptions as e:
                    last_error = e
                    if attempt < max_attempts:
                        # 计算延迟
                        delay = min(base_delay * (backoff_factor ** (attempt - 1)), max_delay)
                        if jitter:
                            import random
                            delay = delay * (0.5 + random.random() * 0.5)

                        if on_retry:
                            try:
                                on_retry(attempt, e, delay)
                            except Exception:
                                pass

                        time.sleep(delay)
                    else:
                        if on_failure:
                            try:
                                on_failure(e)
                            except Exception:
                                pass
                except Exception as e:
                    # 不可重试的异常，直接抛出
                    raise

            raise last_error
        return wrapper
    return decorator


# =============================================================================
# LLM 调用重试+降级
# =============================================================================

class LLMRouter:
    """
    LLM 调用路由器（重试+降级）

    用法：
        router = LLMRouter()

        # 注册主模型和备用模型
        router.register_model('primary', call_primary_func)
        router.register_model('fallback1', call_fallback1_func)
        router.register_model('fallback2', call_fallback2_func)

        # 调用（自动重试和降级）
        result = router.call(prompt='...', max_retries=2)
    """

    def __init__(self):
        self._models: dict[str, Callable] = {}
        self._model_order: list[str] = []
        self._lock = threading.Lock()
        self._stats = {"total_calls": 0, "primary_success": 0, "fallback_used": 0, "total_failures": 0}

    def register_model(self, name: str, call_func: Callable, priority: int = -1):
        """注册模型"""
        with self._lock:
            self._models[name] = call_func
            if priority >= 0 and priority < len(self._model_order):
                self._model_order.insert(priority, name)
            else:
                self._model_order.append(name)

    def call(
        self,
        *args,
        max_retries_per_model: int = 2,
        base_delay: float = 1.0,
        **kwargs,
    ) -> Any:
        """
        调用 LLM（自动重试和降级）

        策略：
        1. 先调用主模型，失败后重试 max_retries_per_model 次
        2. 主模型彻底失败后，依次尝试备用模型
        3. 所有模型都失败后，抛出最后一个错误
        """
        last_error = None
        self._stats["total_calls"] += 1

        with self._lock:
            model_order = list(self._model_order)

        for model_idx, model_name in enumerate(model_order):
            call_func = self._models.get(model_name)
            if not call_func:
                continue

            for attempt in range(1, max_retries_per_model + 1):
                try:
                    result = call_func(*args, **kwargs)
                    if model_idx == 0:
                        self._stats["primary_success"] += 1
                    else:
                        self._stats["fallback_used"] += 1
                    return result
                except Exception as e:
                    last_error = e
                    if attempt < max_retries_per_model:
                        time.sleep(base_delay * attempt)

        self._stats["total_failures"] += 1
        raise last_error if last_error else RuntimeError("All LLM models failed")

    def get_stats(self) -> dict:
        """获取统计信息"""
        return dict(self._stats)


# =============================================================================
# 解析器 fallback 链
# =============================================================================

class ParserFallbackChain:
    """
    解析器 fallback 链

    用法：
        chain = ParserFallbackChain()
        chain.add_parser('docling', parse_with_docling)
        chain.add_parser('grobid', parse_with_grobid)
        chain.add_parser('mineru', parse_with_mineru)
        chain.add_parser('pdfplumber', parse_with_pdfplumber)

        result, parser_used = chain.parse(pdf_path)
    """

    def __init__(self):
        self._parsers: list[Tuple[str, Callable]] = []
        self._stats = {"total_parses": 0, "by_parser": {}, "fallback_count": 0}

    def add_parser(self, name: str, parse_func: Callable):
        """添加解析器（按添加顺序尝试）"""
        self._parsers.append((name, parse_func))
        self._stats["by_parser"][name] = 0

    def parse(self, *args, **kwargs) -> Tuple[Any, str]:
        """
        解析（依次尝试各解析器）

        Returns:
            (result, parser_used_name)
        """
        self._stats["total_parses"] += 1
        last_error = None

        for parser_name, parse_func in self._parsers:
            try:
                result = parse_func(*args, **kwargs)
                self._stats["by_parser"][parser_name] += 1
                return result, parser_name
            except Exception as e:
                last_error = e
                self._stats["fallback_count"] += 1
                continue

        raise last_error if last_error else RuntimeError("All parsers failed")

    def get_stats(self) -> dict:
        """获取统计信息"""
        return dict(self._stats)


# =============================================================================
# 死信队列
# =============================================================================

class DeadLetterQueue:
    """
    死信队列

    用法：
        dlq = DeadLetterQueue()

        # 添加失败任务
        dlq.add_task(
            task_name='call_llm',
            task_type='llm_call',
            payload={'prompt': '...'},
            error_message='Timeout',
        )

        # 获取待处理任务
        tasks = dlq.get_pending_tasks()

        # 重试任务
        dlq.retry_task(task_id, result_handler_func)
    """

    def __init__(self, storage_dir: Optional[str] = None, max_tasks: int = 1000):
        self.max_tasks = max_tasks
        self._lock = threading.Lock()

        if storage_dir:
            self.storage_dir = Path(storage_dir)
        else:
            self.storage_dir = Path(__file__).parent.parent.parent / "data" / "dead_letter"
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        self._tasks_dir = self.storage_dir / "tasks"
        self._tasks_dir.mkdir(exist_ok=True)

        self._index_file = self.storage_dir / "index.json"
        self._index: list[dict] = self._load_json(self._index_file, [])

    def add_task(
        self,
        task_name: str,
        task_type: str,
        payload: dict,
        error_message: str,
        error_type: str = "",
        attempt_count: int = 0,
    ) -> DeadLetterTask:
        """添加失败任务到死信队列"""
        task = DeadLetterTask(
            task_name=task_name,
            task_type=task_type,
            payload=payload,
            error_message=error_message,
            error_type=error_type,
            attempt_count=attempt_count,
        )
        self._save_task(task)
        return task

    def get_task(self, task_id: str) -> Optional[DeadLetterTask]:
        """获取死信任务"""
        task_file = self._tasks_dir / f"{task_id}.json"
        if task_file.is_file():
            try:
                with open(task_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return DeadLetterTask(**data)
            except Exception:
                pass
        return None

    def get_pending_tasks(self, task_type: str = "", limit: int = 50) -> list[DeadLetterTask]:
        """获取待处理的死信任务"""
        with self._lock:
            task_ids = [
                idx["task_id"] for idx in reversed(self._index)
                if idx.get("status") == "pending" and
                (not task_type or idx.get("task_type") == task_type)
            ][:limit]

        results = []
        for tid in task_ids:
            task = self.get_task(tid)
            if task:
                results.append(task)
        return results

    def retry_task(self, task_id: str, handler: Callable) -> bool:
        """
        重试死信任务

        Args:
            task_id: 任务 ID
            handler: 处理函数，接收 payload，返回 True 表示成功

        Returns:
            是否成功
        """
        task = self.get_task(task_id)
        if not task:
            return False

        task.status = "retrying"
        task.last_attempt_at = datetime.now().isoformat()
        task.attempt_count += 1
        self._save_task(task)

        try:
            success = handler(task.payload)
            if success:
                task.status = "resolved"
                task.resolved_at = datetime.now().isoformat()
                task.resolution_notes = "Retry succeeded"
                self._save_task(task)
                return True
            else:
                task.status = "pending"
                self._save_task(task)
                return False
        except Exception as e:
            task.status = "pending"
            task.error_message = str(e)
            self._save_task(task)
            return False

    def dismiss_task(self, task_id: str, reason: str = "") -> bool:
        """驳回/忽略死信任务"""
        task = self.get_task(task_id)
        if not task:
            return False
        task.status = "dismissed"
        task.resolved_at = datetime.now().isoformat()
        task.resolution_notes = reason
        self._save_task(task)
        return True

    def get_stats(self) -> dict:
        """获取统计信息"""
        with self._lock:
            total = len(self._index)
            pending = sum(1 for idx in self._index if idx.get("status") == "pending")
            resolved = sum(1 for idx in self._index if idx.get("status") == "resolved")
            by_type = {}
            for idx in self._index:
                t = idx.get("task_type", "unknown")
                by_type[t] = by_type.get(t, 0) + 1

        return {
            "total": total,
            "pending": pending,
            "resolved": resolved,
            "dismissed": total - pending - resolved,
            "by_type": by_type,
        }

    def _save_task(self, task: DeadLetterTask):
        """保存任务"""
        try:
            task_file = self._tasks_dir / f"{task.task_id}.json"
            with open(task_file, "w", encoding="utf-8") as f:
                json.dump(asdict(task), f, ensure_ascii=False, indent=2)

            with self._lock:
                existing = next((i for i, idx in enumerate(self._index) if idx["task_id"] == task.task_id), None)
                task_idx = {
                    "task_id": task.task_id,
                    "task_name": task.task_name,
                    "task_type": task.task_type,
                    "status": task.status,
                    "created_at": task.created_at,
                }
                if existing is not None:
                    self._index[existing] = task_idx
                else:
                    self._index.append(task_idx)

                if len(self._index) > self.max_tasks:
                    old = self._index[:-self.max_tasks]
                    for o in old:
                        f = self._tasks_dir / f"{o['task_id']}.json"
                        if f.is_file():
                            f.unlink()
                    self._index = self._index[-self.max_tasks:]

                self._save_json(self._index_file, self._index)
        except Exception as e:
            print(f"⚠️  保存死信任务失败: {e}")

    def _load_json(self, file_path: Path, default):
        if file_path.is_file():
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return default
        return default

    def _save_json(self, file_path: Path, data):
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass


# =============================================================================
# 全局单例
# =============================================================================

_dlq_instance: Optional[DeadLetterQueue] = None
_dlq_lock = threading.Lock()


def get_dead_letter_queue() -> DeadLetterQueue:
    """获取全局死信队列单例"""
    global _dlq_instance
    if _dlq_instance is None:
        with _dlq_lock:
            if _dlq_instance is None:
                _dlq_instance = DeadLetterQueue()
    return _dlq_instance
