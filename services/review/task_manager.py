"""V26.3 / V33.17-6A —— 任务管理器（SQLite 持久化）。

历史
    V26.3 时是纯内存 dict（`self._tasks`），**Flask 一重启全部丢失**：
    DSH 里模型拿到的 `task_id` 一旦遇到看门狗拉起/改代码重启就变成 404，
    模型只能判定「任务失败」，且历史结果完全无法回溯。

现在
    改为 `tasks` 表适配器。**9 个方法签名、7 键返回、条件语义三者全不变**，
    所以 `api_server.py` 与 `review_generator.py` 一行都不用改。

对外契约（前端与 MCP 的 `review_task_status` 都直接透传 get_task 的返回）
    task_id / task_type / status / progress / result / error / cancelled

    表列是 `type` / `progress_text`，必须映射；`cancelled` 表里没有，由
    `status == "cancelled"` 派生。**不要顺手加 created_at / params** —— 加字段
    会改变前端与 MCP 看到的 JSON，属未授权变更。

为什么不用 services/unified_task_manager.py
    它的 `complete_task` / `fail_task` / `cancel_task` 的 SQL **不判 status**
    （无条件 UPDATE），而 review 侧的语义是「仅 running 生效」。直接复用会导致
    **已取消的任务被后台线程改写成 completed**（用户取消了却显示完成）。
    它还带 SSE `_broadcast`，review 路由用不上，引入只会多一层耦合。
    故：自己写 SQL，条件逐条对齐旧内存实现。
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

# 绝对路径：**不要**照抄 Path("data/research.db")（依赖 cwd，
# 计划任务从 C:\Windows\System32 启动时会写错库）。
# parents[0]=services/review, [1]=services, [2]=项目根
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = PROJECT_ROOT / "data" / "research.db"

# 持久化任务类型白名单（6-A 名为 REVIEW_TASK_TYPES，6-B 加入 parse_paper 后改名）。
#
# ⚠️ **另一份在 `api_server.py` 的 `PERSISTED_TASK_TYPES`，两处值必须完全一致。**
# 这个白名单同时决定两件事：
#   1. 启动对账收哪些僵尸（run_db_migrations 之后那次 UPDATE）；
#   2. `/api/review/running_task` 看哪些类型。
#
# `download_online` 属于 services/search/online_downloader.py 的**另一套**任务体系，
# 虽然同表，但**永远不许**进这个白名单。
PERSISTED_TASK_TYPES = (
    "qa_ask",
    "agentic_search",
    "generate_outline",
    "generate_review",
    "parse_paper",
)

# 只取需要的列（新增列不影响本适配器）
_SELECT_COLUMNS = (
    "task_id, type, status, progress_text, result, error, created_at, "
    "started_at, finished_at, progress_pct, params"
)


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _connect() -> sqlite3.Connection:
    """短生命周期连接（与 unified_task_manager 一致）。

    timeout=5 是**必须**的：后台任务线程与 Flask 路由线程会并发写同一张表，
    不设重试窗口会直接抛 `database is locked`。
    """
    conn = sqlite3.connect(str(DB_PATH), timeout=5)
    conn.row_factory = sqlite3.Row
    return conn


def _row_to_task(row: sqlite3.Row) -> Dict[str, Any]:
    """把 DB 行映射成**恰好 7 个键**的对外 dict（A-2）。"""
    raw_result = row["result"]
    if raw_result is None:
        result: Any = None
    else:
        try:
            result = json.loads(raw_result)
        except (TypeError, ValueError):
            # 脏数据降级为原始字符串 —— 一条坏记录不能让整个路由 500
            result = raw_result

    status = row["status"]
    return {
        "task_id": row["task_id"],
        "task_type": row["type"],
        "status": status,
        "progress": row["progress_text"] or "",
        "result": result,
        "error": row["error"],
        "cancelled": status == "cancelled",
    }


class TaskManager:
    """review 侧任务管理器（SQLite 版）。

    所有写操作都带 `WHERE task_id = ? AND status = 'running'`，
    并用 `cursor.rowcount` 判断是否真的生效 —— 与旧内存实现逐条对齐。
    """

    def create_task(self, task_type: str) -> str:
        """创建一个新任务，返回 uuid4（36 字符，保持既有 id 形态不变）。"""
        task_id = str(uuid.uuid4())
        now = _now()
        conn = _connect()
        try:
            conn.execute(
                "INSERT INTO tasks ("
                "  task_id, type, status, progress_text, result, error, "
                "  created_at, started_at, progress_pct"
                ") VALUES (?, ?, 'running', '初始化中...', NULL, NULL, ?, ?, 0)",
                (task_id, task_type, now, now),
            )
            conn.commit()
        finally:
            conn.close()
        return task_id

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务（7 键副本）；不存在返回 None。"""
        conn = _connect()
        try:
            row = conn.execute(
                f"SELECT {_SELECT_COLUMNS} FROM tasks WHERE task_id = ?", (task_id,)
            ).fetchone()
        finally:
            conn.close()
        return _row_to_task(row) if row else None

    def cancel_task(self, task_id: str) -> bool:
        """仅当 running 时取消；返回**是否真的取消成功**（路由靠它给 404）。"""
        conn = _connect()
        try:
            cursor = conn.execute(
                "UPDATE tasks SET status='cancelled', finished_at=? "
                "WHERE task_id = ? AND status = 'running'",
                (_now(), task_id),
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def complete_task(self, task_id: str, result: Any) -> None:
        """仅当 running 时置 completed。已 cancelled 的任务**必须无效**。"""
        if result is None:
            payload = None
        else:
            try:
                payload = json.dumps(result, ensure_ascii=False)
            except (TypeError, ValueError):
                payload = json.dumps(str(result), ensure_ascii=False)

        conn = _connect()
        try:
            conn.execute(
                "UPDATE tasks SET status='completed', result=?, progress_pct=100, finished_at=? "
                "WHERE task_id = ? AND status = 'running'",
                (payload, _now(), task_id),
            )
            conn.commit()
        finally:
            conn.close()

    def fail_task(self, task_id: str, error: str) -> None:
        """仅当 running 时置 failed。"""
        conn = _connect()
        try:
            conn.execute(
                "UPDATE tasks SET status='failed', error=?, finished_at=? "
                "WHERE task_id = ? AND status = 'running'",
                (error, _now(), task_id),
            )
            conn.commit()
        finally:
            conn.close()

    def is_cancelled(self, task_id: str) -> bool:
        """后台任务在阶段间调用；不存在返回 False。"""
        conn = _connect()
        try:
            row = conn.execute(
                "SELECT status FROM tasks WHERE task_id = ?", (task_id,)
            ).fetchone()
        finally:
            conn.close()
        return bool(row and row["status"] == "cancelled")

    def update_progress(self, task_id: str, progress: str) -> None:
        """仅当 running 时更新进度文案。"""
        conn = _connect()
        try:
            conn.execute(
                "UPDATE tasks SET progress_text=? WHERE task_id = ? AND status = 'running'",
                (progress, task_id),
            )
            conn.commit()
        finally:
            conn.close()

    def get_running_task(self) -> Optional[Dict[str, Any]]:
        """取最早创建的 **review** running 任务（对应旧实现的「第一个」）；无则 None。

        ⚠️ 必须按 PERSISTED_TASK_TYPES 过滤：`tasks` 表是 review 与 online_downloader
        共用的，不过滤就会把 `download_online` 任务当成 review 任务返回给
        `/api/review/running_task` —— 旧的内存实现里根本不存在这种情况。
        """
        placeholders = ",".join("?" for _ in PERSISTED_TASK_TYPES)
        conn = _connect()
        try:
            row = conn.execute(
                f"SELECT {_SELECT_COLUMNS} FROM tasks "
                f"WHERE status = 'running' AND type IN ({placeholders}) "
                "ORDER BY created_at ASC LIMIT 1",
                PERSISTED_TASK_TYPES,
            ).fetchone()
        finally:
            conn.close()
        return _row_to_task(row) if row else None

    def cleanup_old_tasks(self, max_count: int = 100) -> None:
        """超出 max_count 时删最早的（全仓库无调用方，保留签名）。

        同样只统计/删除 review 的 4 个类型：`tasks` 表与 online_downloader 共用，
        不能替别人清历史。
        """
        placeholders = ",".join("?" for _ in PERSISTED_TASK_TYPES)
        conn = _connect()
        try:
            total = conn.execute(
                f"SELECT COUNT(*) FROM tasks WHERE type IN ({placeholders})",
                PERSISTED_TASK_TYPES,
            ).fetchone()[0]
            if total <= max_count:
                return
            conn.execute(
                "DELETE FROM tasks WHERE task_id IN ("
                f"  SELECT task_id FROM tasks WHERE type IN ({placeholders}) "
                "  ORDER BY created_at ASC LIMIT ?"
                ")",
                (*PERSISTED_TASK_TYPES, total - max_count),
            )
            conn.commit()
        finally:
            conn.close()


# 全局任务管理器实例（api_server.py 的 `from ... import task_manager` 不能变）
task_manager = TaskManager()
