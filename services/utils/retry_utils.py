"""
Sci-Pal ç»Ÿä¸€é”™è¯¯å¤„ç†ä¸Žé‡è¯•æ¨¡å— V33.6

ç”¨é€”ï¼šæä¾›ç»Ÿä¸€çš„é”™è¯¯å¤„ç†ã€é‡è¯•ã€é™çº§å’Œæ­»ä¿¡é˜Ÿåˆ—æœºåˆ¶ã€‚
- @retry è£…é¥°å™¨ï¼šæŒ‡æ•°é€€é¿é‡è¯•ï¼Œæ”¯æŒå¯é‡è¯•å¼‚å¸¸ç±»åž‹
- LLM è°ƒç”¨é‡è¯•+é™çº§ï¼šä¸»æ¨¡åž‹å¤±è´¥æ—¶è‡ªåŠ¨åˆ‡æ¢åˆ°å¤‡ç”¨æ¨¡åž‹
- è§£æžå™¨ fallback é“¾ï¼šDoclingå¤±è´¥â†’GROBIDâ†’MinerUâ†’pdfplumber
- æ­»ä¿¡é˜Ÿåˆ—ï¼šå¤šæ¬¡å¤±è´¥çš„ä»»åŠ¡è¿›å…¥æ­»ä¿¡é˜Ÿåˆ—ï¼Œæ”¯æŒäººå·¥é‡è¯•
- é”™è¯¯ç»Ÿè®¡ï¼šè®°å½•å„ç±»é”™è¯¯çš„å‘ç”Ÿæ¬¡æ•°ï¼Œä¾¿äºŽå‘çŽ°ç³»ç»Ÿæ€§é—®é¢˜

è®¾è®¡åŽŸåˆ™ï¼š
- ä¼˜é›…é™çº§ï¼šå¤±è´¥æ—¶å°½é‡æä¾›å¯ç”¨çš„é™çº§æ–¹æ¡ˆï¼Œè€Œä¸æ˜¯ç›´æŽ¥æŠ¥é”™
- æŒ‡æ•°é€€é¿ï¼šé‡è¯•é—´éš”æŒ‡æ•°å¢žé•¿ï¼Œé¿å…æ‰“çˆ†ä¸‹æ¸¸æœåŠ¡
- å¯è§‚æµ‹ï¼šæ‰€æœ‰é‡è¯•å’Œé™çº§éƒ½æœ‰æ—¥å¿—è®°å½•
- å¯é…ç½®ï¼šé‡è¯•æ¬¡æ•°ã€é—´éš”ã€å¼‚å¸¸ç±»åž‹éƒ½å¯é…ç½®
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
# æ•°æ®ç»“æž„
# =============================================================================

class RetryStatus(str, Enum):
    """é‡è¯•çŠ¶æ€"""
    PENDING = "pending"
    RETRYING = "retrying"
    SUCCESS = "success"
    FAILED = "failed"
    DEAD_LETTER = "dead_letter"


@dataclass
class RetryRecord:
    """é‡è¯•è®°å½•"""
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
    """æ­»ä¿¡é˜Ÿåˆ—ä»»åŠ¡"""
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
    """é”™è¯¯ç»Ÿè®¡"""
    total_errors: int = 0
    total_retries: int = 0
    total_success_after_retry: int = 0
    total_dead_letters: int = 0
    success_rate: float = 0.0
    by_error_type: dict[str, int] = field(default_factory=dict)
    by_task_name: dict[str, int] = field(default_factory=dict)
    recent_errors: list[dict] = field(default_factory=list)


# =============================================================================
# é‡è¯•è£…é¥°å™¨
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
    é‡è¯•è£…é¥°å™¨ï¼ˆæŒ‡æ•°é€€é¿ï¼‰

    Args:
        max_attempts: æœ€å¤§å°è¯•æ¬¡æ•°ï¼ˆåŒ…æ‹¬ç¬¬ä¸€æ¬¡ï¼‰
        base_delay: åŸºç¡€å»¶è¿Ÿï¼ˆç§’ï¼‰
        max_delay: æœ€å¤§å»¶è¿Ÿï¼ˆç§’ï¼‰
        backoff_factor: é€€é¿å› å­
        retryable_exceptions: å¯é‡è¯•çš„å¼‚å¸¸ç±»åž‹å…ƒç»„
        on_retry: é‡è¯•å›žè°ƒå‡½æ•°ï¼ˆattempt, error, delayï¼‰
        on_success: æˆåŠŸå›žè°ƒå‡½æ•°ï¼ˆresult, attemptï¼‰
        on_failure: æœ€ç»ˆå¤±è´¥å›žè°ƒå‡½æ•°ï¼ˆerrorï¼‰
        jitter: æ˜¯å¦æ·»åŠ éšæœºæŠ–åŠ¨

    ç”¨æ³•ï¼š
        @retry(max_attempts=3, base_delay=1.0)
        def call_llm(prompt):
            ...

        # åªé‡è¯•ç‰¹å®šå¼‚å¸¸
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
                        # è®¡ç®—å»¶è¿Ÿ
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
                    # ä¸å¯é‡è¯•çš„å¼‚å¸¸ï¼Œç›´æŽ¥æŠ›å‡º
                    raise

            raise last_error
        return wrapper
    return decorator


# =============================================================================
# LLM è°ƒç”¨é‡è¯•+é™çº§
# =============================================================================

class LLMRouter:
    """
    LLM è°ƒç”¨è·¯ç”±å™¨ï¼ˆé‡è¯•+é™çº§ï¼‰

    ç”¨æ³•ï¼š
        router = LLMRouter()

        # æ³¨å†Œä¸»æ¨¡åž‹å’Œå¤‡ç”¨æ¨¡åž‹
        router.register_model('primary', call_primary_func)
        router.register_model('fallback1', call_fallback1_func)
        router.register_model('fallback2', call_fallback2_func)

        # è°ƒç”¨ï¼ˆè‡ªåŠ¨é‡è¯•å’Œé™çº§ï¼‰
        result = router.call(prompt='...', max_retries=2)
    """

    def __init__(self):
        self._models: dict[str, Callable] = {}
        self._model_order: list[str] = []
        self._lock = threading.Lock()
        self._stats = {"total_calls": 0, "primary_success": 0, "fallback_used": 0, "total_failures": 0}

    def register_model(self, name: str, call_func: Callable, priority: int = -1):
        """æ³¨å†Œæ¨¡åž‹"""
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
        è°ƒç”¨ LLMï¼ˆè‡ªåŠ¨é‡è¯•å’Œé™çº§ï¼‰

        ç­–ç•¥ï¼š
        1. å…ˆè°ƒç”¨ä¸»æ¨¡åž‹ï¼Œå¤±è´¥åŽé‡è¯• max_retries_per_model æ¬¡
        2. ä¸»æ¨¡åž‹å½»åº•å¤±è´¥åŽï¼Œä¾æ¬¡å°è¯•å¤‡ç”¨æ¨¡åž‹
        3. æ‰€æœ‰æ¨¡åž‹éƒ½å¤±è´¥åŽï¼ŒæŠ›å‡ºæœ€åŽä¸€ä¸ªé”™è¯¯
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
        """èŽ·å–ç»Ÿè®¡ä¿¡æ¯"""
        return dict(self._stats)


# æ­»ä¿¡é˜Ÿåˆ—
# =============================================================================

class DeadLetterQueue:
    """
    æ­»ä¿¡é˜Ÿåˆ—

    ç”¨æ³•ï¼š
        dlq = DeadLetterQueue()

        # æ·»åŠ å¤±è´¥ä»»åŠ¡
        dlq.add_task(
            task_name='call_llm',
            task_type='llm_call',
            payload={'prompt': '...'},
            error_message='Timeout',
        )

        # èŽ·å–å¾…å¤„ç†ä»»åŠ¡
        tasks = dlq.get_pending_tasks()

        # é‡è¯•ä»»åŠ¡
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
        """æ·»åŠ å¤±è´¥ä»»åŠ¡åˆ°æ­»ä¿¡é˜Ÿåˆ—"""
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
        """èŽ·å–æ­»ä¿¡ä»»åŠ¡"""
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
        """èŽ·å–å¾…å¤„ç†çš„æ­»ä¿¡ä»»åŠ¡"""
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
        é‡è¯•æ­»ä¿¡ä»»åŠ¡

        Args:
            task_id: ä»»åŠ¡ ID
            handler: å¤„ç†å‡½æ•°ï¼ŒæŽ¥æ”¶ payloadï¼Œè¿”å›ž True è¡¨ç¤ºæˆåŠŸ

        Returns:
            æ˜¯å¦æˆåŠŸ
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
        """é©³å›ž/å¿½ç•¥æ­»ä¿¡ä»»åŠ¡"""
        task = self.get_task(task_id)
        if not task:
            return False
        task.status = "dismissed"
        task.resolved_at = datetime.now().isoformat()
        task.resolution_notes = reason
        self._save_task(task)
        return True

    def get_stats(self) -> dict:
        """èŽ·å–ç»Ÿè®¡ä¿¡æ¯"""
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
        """ä¿å­˜ä»»åŠ¡"""
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
            print(f"âš ï¸  ä¿å­˜æ­»ä¿¡ä»»åŠ¡å¤±è´¥: {e}")

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
# å…¨å±€å•ä¾‹
# =============================================================================

class ParserFallbackError(RuntimeError):
    """All parsers in the fallback chain failed."""


class ParserFallbackChain:
    """Try parsers in order; return the first successful result.

    A parser may be an object with ``parse(*args, **kwargs)`` or a callable.
    """

    def __init__(self, parsers=None):
        self._parsers = []
        self._stats = {}
        for item in parsers or []:
            if isinstance(item, (tuple, list)) and len(item) == 2:
                self.add_parser(item[0], item[1])
            else:
                name = getattr(item, "name", item.__class__.__name__)
                self.add_parser(name, item)

    def add_parser(self, name, parser):
        self._parsers.append((name, parser))
        self._stats.setdefault(name, {"attempts": 0, "successes": 0, "failures": 0})
        return self

    def parse(self, *args, **kwargs):
        if not self._parsers:
            raise ParserFallbackError("no parsers registered")
        last_error = None
        for name, parser in self._parsers:
            self._stats[name]["attempts"] += 1
            try:
                func = parser.parse if hasattr(parser, "parse") else parser
                result = func(*args, **kwargs)
                if result is None:
                    raise ValueError("parser returned None")
                self._stats[name]["successes"] += 1
                return result
            except Exception as exc:  # noqa: BLE001
                self._stats[name]["failures"] += 1
                last_error = exc
        raise ParserFallbackError(
            f"all {len(self._parsers)} parsers failed; last={last_error}"
        ) from last_error

    def get_stats(self):
        return {
            "parsers": [
                {"name": name, **dict(counts)} for name, counts in self._stats.items()
            ],
            "total_attempts": sum(item["attempts"] for item in self._stats.values()),
            "total_successes": sum(item["successes"] for item in self._stats.values()),
            "total_failures": sum(item["failures"] for item in self._stats.values()),
        }


_dlq_instance: Optional[DeadLetterQueue] = None
_dlq_lock = threading.Lock()


def get_dead_letter_queue() -> DeadLetterQueue:
    """èŽ·å–å…¨å±€æ­»ä¿¡é˜Ÿåˆ—å•ä¾‹"""
    global _dlq_instance
    if _dlq_instance is None:
        with _dlq_lock:
            if _dlq_instance is None:
                _dlq_instance = DeadLetterQueue()
    return _dlq_instance
