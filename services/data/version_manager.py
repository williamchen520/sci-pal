"""
Sci-Pal 版本管理与增量同步模块 V33.6

用途：管理数据源的版本信息和增量同步，避免每次全量重建向量库。
- 版本管理：每个数据源记录 last_sync 时间戳、version、同步状态
- 增量拉取：只拉取 last_sync 之后的新论文
- 增量索引：向量库支持 upsert 而非全量重建
- 任务管理：同步任务的创建/查询/取消

设计原则：
- 不重建，只追加：旧数据不动，新数据 upsert 进去
- 可追溯：每次同步都有版本记录，支持回滚
- 可中断：同步任务支持断点续传，中断后可继续
- 低开销：增量同步只处理新数据，不重复处理已有数据
"""

import json
import time
import uuid
import threading
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Callable
from dataclasses import dataclass, field, asdict
from enum import Enum


# =============================================================================
# 数据结构
# =============================================================================

class DataSourceType(str, Enum):
    """数据源类型"""
    PUBMED = "pubmed"
    PMC = "pmc"
    OPENALEX = "openalex"
    ARXIV = "arxiv"
    ZOTERO = "zotero"
    LOCAL = "local"


class SyncStatus(str, Enum):
    """同步状态"""
    IDLE = "idle"              # 空闲
    PENDING = "pending"        # 等待中
    RUNNING = "running"        # 运行中
    PAUSED = "paused"          # 已暂停
    COMPLETED = "completed"    # 已完成
    FAILED = "failed"          # 失败
    CANCELLED = "cancelled"    # 已取消


@dataclass
class DataSourceVersion:
    """数据源版本信息"""
    source_id: str = ""
    source_type: str = DataSourceType.LOCAL.value
    name: str = ""
    description: str = ""

    # 版本信息
    current_version: int = 0
    last_sync_at: str = ""  # 上次同步时间（ISO 格式）
    last_sync_unix: float = 0.0
    next_sync_at: str = ""  # 下次计划同步时间

    # 统计信息
    total_papers: int = 0  # 总论文数
    last_sync_added: int = 0  # 上次同步新增论文数
    last_sync_updated: int = 0  # 上次同步更新论文数
    last_sync_failed: int = 0  # 上次同步失败论文数

    # 配置
    enabled: bool = True
    auto_sync: bool = False  # 是否自动同步
    sync_interval_hours: int = 24  # 自动同步间隔（小时）
    max_papers_per_sync: int = 1000  # 每次同步最大论文数

    # 状态
    status: str = SyncStatus.IDLE.value
    current_task_id: str = ""

    # 元数据
    metadata: dict = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class SyncTask:
    """同步任务"""
    task_id: str = field(default_factory=lambda: f"sync_{uuid.uuid4().hex[:12]}")
    source_id: str = ""
    source_type: str = ""

    # 任务状态
    status: str = SyncStatus.PENDING.value
    progress: float = 0.0  # 0-100
    current_step: str = ""  # 当前步骤描述

    # 统计
    total_to_process: int = 0
    processed: int = 0
    added: int = 0
    updated: int = 0
    failed: int = 0
    failed_ids: list[str] = field(default_factory=list)

    # 时间
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    started_at: str = ""
    completed_at: str = ""
    estimated_remaining_seconds: float = 0.0

    # 配置
    incremental: bool = True  # 是否增量同步
    since_timestamp: float = 0.0  # 增量同步的起始时间戳
    max_papers: int = 1000

    # 错误信息
    error_message: str = ""

    # 元数据
    metadata: dict = field(default_factory=dict)


@dataclass
class SyncStats:
    """同步统计信息"""
    total_sources: int = 0
    enabled_sources: int = 0
    auto_sync_sources: int = 0

    total_tasks: int = 0
    running_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0

    total_papers: int = 0
    papers_added_last_7d: int = 0
    papers_added_last_30d: int = 0

    last_sync_time: str = ""
    next_planned_sync: str = ""


# =============================================================================
# 版本管理器
# =============================================================================

class VersionManager:
    """
    版本管理与增量同步管理器

    用法：
        manager = VersionManager()

        # 注册数据源
        source = manager.register_source(
            source_id="pubmed_stat1",
            source_type="pubmed",
            name="PubMed STAT1",
            description="PubMed 中 STAT1 相关论文",
        )

        # 创建同步任务
        task = manager.create_sync_task(
            source_id="pubmed_stat1",
            incremental=True,
        )

        # 更新任务进度
        manager.update_task_progress(
            task_id=task.task_id,
            progress=50.0,
            current_step="正在下载论文...",
            processed=50,
            added=45,
        )

        # 完成任务
        manager.complete_task(task.task_id)

        # 查询
        source = manager.get_source("pubmed_stat1")
        task = manager.get_task(task.task_id)
        stats = manager.get_stats()
    """

    def __init__(
        self,
        storage_dir: Optional[str] = None,
        max_tasks: int = 1000,
    ):
        """
        Args:
            storage_dir: 存储目录，默认 data/version_manager/
            max_tasks: 最多保留的任务数
        """
        self.max_tasks = max_tasks
        self._lock = threading.Lock()

        # 存储目录
        if storage_dir:
            self.storage_dir = Path(storage_dir)
        else:
            self.storage_dir = Path(__file__).parent.parent.parent / "data" / "version_manager"
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        # 数据源目录
        self._sources_dir = self.storage_dir / "sources"
        self._sources_dir.mkdir(exist_ok=True)

        # 任务目录
        self._tasks_dir = self.storage_dir / "tasks"
        self._tasks_dir.mkdir(exist_ok=True)

        # 索引文件
        self._sources_index_file = self.storage_dir / "sources_index.json"
        self._tasks_index_file = self.storage_dir / "tasks_index.json"

        # 加载索引
        self._sources_index: dict[str, dict] = self._load_json(self._sources_index_file, {})
        self._tasks_index: list[dict] = self._load_json(self._tasks_index_file, [])

    # -------------------------------------------------------------------------
    # 数据源管理
    # -------------------------------------------------------------------------

    def register_source(
        self,
        source_id: str,
        source_type: str,
        name: str,
        description: str = "",
        auto_sync: bool = False,
        sync_interval_hours: int = 24,
        max_papers_per_sync: int = 1000,
    ) -> DataSourceVersion:
        """注册或更新数据源"""
        source = DataSourceVersion(
            source_id=source_id,
            source_type=source_type,
            name=name,
            description=description,
            auto_sync=auto_sync,
            sync_interval_hours=sync_interval_hours,
            max_papers_per_sync=max_papers_per_sync,
        )

        # 如果已存在，保留统计信息
        existing = self.get_source(source_id)
        if existing:
            source.current_version = existing.current_version
            source.last_sync_at = existing.last_sync_at
            source.last_sync_unix = existing.last_sync_unix
            source.total_papers = existing.total_papers
            source.last_sync_added = existing.last_sync_added

        self._save_source(source)
        return source

    def get_source(self, source_id: str) -> Optional[DataSourceVersion]:
        """获取数据源信息"""
        source_file = self._sources_dir / f"{source_id}.json"
        if source_file.is_file():
            try:
                with open(source_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return DataSourceVersion(**data)
            except Exception as e:
                print(f"⚠️  读取数据源失败 {source_id}: {e}")
        return None

    def list_sources(self, enabled_only: bool = False) -> list[DataSourceVersion]:
        """列出所有数据源"""
        sources = []
        for source_id in self._sources_index.keys():
            source = self.get_source(source_id)
            if source:
                if not enabled_only or source.enabled:
                    sources.append(source)
        return sources

    def update_source_stats(
        self,
        source_id: str,
        added: int = 0,
        updated: int = 0,
        failed: int = 0,
    ):
        """更新数据源统计信息（同步完成后调用）"""
        source = self.get_source(source_id)
        if not source:
            return

        source.current_version += 1
        source.last_sync_at = datetime.now().isoformat()
        source.last_sync_unix = time.time()
        source.total_papers += added
        source.last_sync_added = added
        source.last_sync_updated = updated
        source.last_sync_failed = failed
        source.status = SyncStatus.IDLE.value
        source.current_task_id = ""

        # 计算下次同步时间
        if source.auto_sync:
            next_time = datetime.now() + timedelta(hours=source.sync_interval_hours)
            source.next_sync_at = next_time.isoformat()

        self._save_source(source)

    # -------------------------------------------------------------------------
    # 同步任务管理
    # -------------------------------------------------------------------------

    def create_sync_task(
        self,
        source_id: str,
        incremental: bool = True,
        max_papers: int = 1000,
    ) -> Optional[SyncTask]:
        """创建同步任务"""
        source = self.get_source(source_id)
        if not source:
            return None

        # 检查是否已有运行中的任务
        if source.status == SyncStatus.RUNNING.value:
            return None

        task = SyncTask(
            source_id=source_id,
            source_type=source.source_type,
            incremental=incremental,
            since_timestamp=source.last_sync_unix if incremental else 0,
            max_papers=min(max_papers, source.max_papers_per_sync),
        )

        # 更新数据源状态
        source.status = SyncStatus.RUNNING.value
        source.current_task_id = task.task_id
        self._save_source(source)

        self._save_task(task)
        return task

    def get_task(self, task_id: str) -> Optional[SyncTask]:
        """获取同步任务"""
        task_file = self._tasks_dir / f"{task_id}.json"
        if task_file.is_file():
            try:
                with open(task_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return SyncTask(**data)
            except Exception as e:
                print(f"⚠️  读取同步任务失败 {task_id}: {e}")
        return None

    def update_task_progress(
        self,
        task_id: str,
        progress: float,
        current_step: str = "",
        processed: int = 0,
        added: int = 0,
        updated: int = 0,
        failed: int = 0,
        failed_id: str = "",
    ):
        """更新任务进度"""
        task = self.get_task(task_id)
        if not task or task.status not in [SyncStatus.RUNNING.value, SyncStatus.PENDING.value]:
            return

        task.status = SyncStatus.RUNNING.value
        if not task.started_at:
            task.started_at = datetime.now().isoformat()
        task.progress = min(progress, 100.0)
        task.current_step = current_step
        if processed:
            task.processed = processed
        if added:
            task.added += added
        if updated:
            task.updated += updated
        if failed:
            task.failed += failed
        if failed_id and failed_id not in task.failed_ids:
            task.failed_ids.append(failed_id)

        # 估算剩余时间
        if task.processed > 0 and task.total_to_process > 0:
            elapsed = time.time() - datetime.fromisoformat(task.started_at).timestamp()
            rate = task.processed / elapsed if elapsed > 0 else 0
            if rate > 0:
                task.estimated_remaining_seconds = (task.total_to_process - task.processed) / rate

        self._save_task(task)

    def complete_task(self, task_id: str) -> bool:
        """完成任务"""
        task = self.get_task(task_id)
        if not task:
            return False

        task.status = SyncStatus.COMPLETED.value
        task.progress = 100.0
        task.completed_at = datetime.now().isoformat()
        task.estimated_remaining_seconds = 0
        self._save_task(task)

        # 更新数据源统计
        self.update_source_stats(
            source_id=task.source_id,
            added=task.added,
            updated=task.updated,
            failed=task.failed,
        )
        return True

    def fail_task(self, task_id: str, error_message: str) -> bool:
        """标记任务失败"""
        task = self.get_task(task_id)
        if not task:
            return False

        task.status = SyncStatus.FAILED.value
        task.error_message = error_message
        task.completed_at = datetime.now().isoformat()
        self._save_task(task)

        # 更新数据源状态
        source = self.get_source(task.source_id)
        if source:
            source.status = SyncStatus.IDLE.value
            source.current_task_id = ""
            self._save_source(source)
        return True

    def cancel_task(self, task_id: str) -> bool:
        """取消任务"""
        task = self.get_task(task_id)
        if not task or task.status not in [SyncStatus.RUNNING.value, SyncStatus.PENDING.value]:
            return False

        task.status = SyncStatus.CANCELLED.value
        task.completed_at = datetime.now().isoformat()
        self._save_task(task)

        # 更新数据源状态
        source = self.get_source(task.source_id)
        if source:
            source.status = SyncStatus.IDLE.value
            source.current_task_id = ""
            self._save_source(source)
        return True

    def list_tasks(
        self,
        source_id: str = "",
        status: str = "",
        limit: int = 50,
    ) -> list[SyncTask]:
        """列出同步任务"""
        with self._lock:
            task_ids = [idx["task_id"] for idx in reversed(self._tasks_index)]

        results = []
        for tid in task_ids:
            task = self.get_task(tid)
            if not task:
                continue
            if source_id and task.source_id != source_id:
                continue
            if status and task.status != status:
                continue
            results.append(task)
            if len(results) >= limit:
                break
        return results

    # -------------------------------------------------------------------------
    # 增量同步辅助
    # -------------------------------------------------------------------------

    def get_incremental_query_params(self, source_id: str) -> dict:
        """获取增量同步的查询参数（用于下载脚本）"""
        source = self.get_source(source_id)
        if not source:
            return {}

        return {
            "incremental": True,
            "since_timestamp": source.last_sync_unix,
            "since_date": source.last_sync_at[:10] if source.last_sync_at else "",
            "max_papers": source.max_papers_per_sync,
        }

    def should_auto_sync(self, source_id: str) -> bool:
        """检查是否应该自动同步"""
        source = self.get_source(source_id)
        if not source or not source.auto_sync or source.enabled:
            return False
        if source.status == SyncStatus.RUNNING.value:
            return False
        if not source.next_sync_at:
            return True
        try:
            next_time = datetime.fromisoformat(source.next_sync_at)
            return datetime.now() >= next_time
        except Exception:
            return False

    def get_due_auto_sync_sources(self) -> list[DataSourceVersion]:
        """获取需要自动同步的数据源列表"""
        return [s for s in self.list_sources(enabled_only=True) if self.should_auto_sync(s.source_id)]

    # -------------------------------------------------------------------------
    # 统计
    # -------------------------------------------------------------------------

    def get_stats(self) -> SyncStats:
        """获取同步统计信息"""
        sources = self.list_sources()
        tasks = self.list_tasks(limit=1000)

        stats = SyncStats(
            total_sources=len(sources),
            enabled_sources=sum(1 for s in sources if s.enabled),
            auto_sync_sources=sum(1 for s in sources if s.auto_sync),
            total_tasks=len(tasks),
            running_tasks=sum(1 for t in tasks if t.status == SyncStatus.RUNNING.value),
            completed_tasks=sum(1 for t in tasks if t.status == SyncStatus.COMPLETED.value),
            failed_tasks=sum(1 for t in tasks if t.status == SyncStatus.FAILED.value),
            total_papers=sum(s.total_papers for s in sources),
        )

        # 最近 7 天/30 天新增论文
        now = time.time()
        seven_days_ago = now - 7 * 24 * 3600
        thirty_days_ago = now - 30 * 24 * 3600

        for task in tasks:
            if task.status == SyncStatus.COMPLETED.value and task.completed_at:
                try:
                    task_time = datetime.fromisoformat(task.completed_at).timestamp()
                    if task_time >= seven_days_ago:
                        stats.papers_added_last_7d += task.added
                    if task_time >= thirty_days_ago:
                        stats.papers_added_last_30d += task.added
                except Exception:
                    pass

        # 最近同步时间和下次计划同步
        completed_tasks = [t for t in tasks if t.status == SyncStatus.COMPLETED.value]
        if completed_tasks:
            stats.last_sync_time = completed_tasks[0].completed_at

        auto_sources = [s for s in sources if s.auto_sync and s.next_sync_at]
        if auto_sources:
            stats.next_planned_sync = min(s.next_sync_at for s in auto_sources)

        return stats

    # -------------------------------------------------------------------------
    # 内部方法
    # -------------------------------------------------------------------------

    def _save_source(self, source: DataSourceVersion):
        """保存数据源"""
        try:
            source.updated_at = datetime.now().isoformat()
            source_file = self._sources_dir / f"{source.source_id}.json"
            with open(source_file, "w", encoding="utf-8") as f:
                json.dump(asdict(source), f, ensure_ascii=False, indent=2)

            with self._lock:
                self._sources_index[source.source_id] = {
                    "source_id": source.source_id,
                    "name": source.name,
                    "source_type": source.source_type,
                    "enabled": source.enabled,
                    "status": source.status,
                    "updated_at": source.updated_at,
                }
                self._save_json(self._sources_index_file, self._sources_index)
        except Exception as e:
            print(f"⚠️  保存数据源失败: {e}")

    def _save_task(self, task: SyncTask):
        """保存任务"""
        try:
            task_file = self._tasks_dir / f"{task.task_id}.json"
            with open(task_file, "w", encoding="utf-8") as f:
                json.dump(asdict(task), f, ensure_ascii=False, indent=2)

            with self._lock:
                # 检查是否已存在
                existing = next((i for i, idx in enumerate(self._tasks_index) if idx["task_id"] == task.task_id), None)
                task_idx = {
                    "task_id": task.task_id,
                    "source_id": task.source_id,
                    "status": task.status,
                    "progress": task.progress,
                    "created_at": task.created_at,
                }
                if existing is not None:
                    self._tasks_index[existing] = task_idx
                else:
                    self._tasks_index.append(task_idx)

                # 限制任务数量
                if len(self._tasks_index) > self.max_tasks:
                    old_tasks = self._tasks_index[:-self.max_tasks]
                    for old in old_tasks:
                        task_file = self._tasks_dir / f"{old['task_id']}.json"
                        if task_file.is_file():
                            task_file.unlink()
                    self._tasks_index = self._tasks_index[-self.max_tasks:]

                self._save_json(self._tasks_index_file, self._tasks_index)
        except Exception as e:
            print(f"⚠️  保存同步任务失败: {e}")

    def _load_json(self, file_path: Path, default):
        """加载 JSON 文件"""
        if file_path.is_file():
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return default
        return default

    def _save_json(self, file_path: Path, data):
        """保存 JSON 文件"""
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"⚠️  保存 JSON 失败: {e}")


# =============================================================================
# 全局单例
# =============================================================================

_version_manager_instance: Optional[VersionManager] = None
_version_manager_lock = threading.Lock()


def get_version_manager() -> VersionManager:
    """获取全局版本管理器单例"""
    global _version_manager_instance
    if _version_manager_instance is None:
        with _version_manager_lock:
            if _version_manager_instance is None:
                _version_manager_instance = VersionManager()
    return _version_manager_instance
