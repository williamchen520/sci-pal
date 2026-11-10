"""
Online Downloader: 在线文献下载+增量导入+增量建索引
V1.0 - 混合检索系统 P1 模块

接收用户勾选的在线文献（PMCID 列表），后台异步执行：
  1. 下载 PMC XML 全文（复用 download_pmc_xml.py，自动过滤只有摘要的）
  2. 增量导入到 research.db（只导入新的，不清空旧数据）
  3. 增量建向量索引（只对新论文的段落做 embedding，追加到 chroma）

核心原则：不重建整个库，只增量追加，秒级完成索引更新。
检索层代码一行不用改，新数据自动被检索覆盖。

支持后台任务管理：
  - 启动下载任务（异步，不阻塞前端）
  - 查询任务进度（下载/导入/索引各阶段进度）
  - 任务完成后自动刷新结果
"""

import hashlib
import threading
import time
import uuid
from pathlib import Path

from services.papers import pg_writes as paper_pg_writes
from typing import Dict, List, Optional

# Windows 控制台编码修复
import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


# 路径配置（跟项目保持一致）
from config.paths import EMBEDDING_MODEL, MODELS_DIR, XML_DIR
XML_OUTPUT_DIR = str(XML_DIR)

# Embedding 模型（跟主程序一致：bge-base-en-v1.5）
# 本地模型路径（如果有的话优先用本地）
LOCAL_EMBEDDING_PATH = str(MODELS_DIR / "bge-base-en-v1.5")


# ============================================================
# 后台任务管理器
# ============================================================

class DownloadTask:
    """
    下载任务状态跟踪。
    """
    def __init__(self, task_id: str, pmc_ids: List[str]):
        self.task_id = task_id
        self.pmc_ids = pmc_ids
        self.total = len(pmc_ids)

        # 阶段：pending → queued → downloading → importing → indexing → completed / failed
        self.status = "pending"
        self.current_stage = "pending"

        # 各阶段进度
        self.downloaded = 0
        self.download_failed = 0
        self.download_skipped = 0  # 已存在的
        self.imported = 0
        self.indexed = 0

        # 新下载的论文 ID（用于增量导入和索引）
        self.new_paper_ids: List[str] = []

        # V33.3: 下载失败的 PMCID 列表（用于重试）
        self.failed_pmc_ids: List[str] = []

        # 错误信息
        self.error: Optional[str] = None

        # 时间
        self.start_time = time.time()
        self.end_time: Optional[float] = None

    def to_dict(self) -> Dict:
        elapsed = (self.end_time or time.time()) - self.start_time
        return {
            "task_id": self.task_id,
            "status": self.status,
            "current_stage": self.current_stage,
            "total": self.total,
            "downloaded": self.downloaded,
            "download_failed": self.download_failed,
            "download_skipped": self.download_skipped,
            "imported": self.imported,
            "indexed": self.indexed,
            "new_paper_count": len(self.new_paper_ids),
            "failed_pmc_ids": self.failed_pmc_ids,  # V33.3: 失败列表
            "error": self.error,
            "elapsed_seconds": round(elapsed, 1),
            "progress_percent": self._progress_percent(),
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.start_time)),
        }

    def _progress_percent(self) -> int:
        """计算总进度百分比（下载40% + 导入30% + 索引30%）。"""
        if self.total == 0:
            return 100 if self.status == "completed" else 0

        download_pct = (self.downloaded + self.download_skipped) / self.total * 40
        import_pct = (self.imported / max(len(self.new_paper_ids), 1)) * 30 if self.new_paper_ids else 0
        index_pct = (self.indexed / max(len(self.new_paper_ids), 1)) * 30 if self.new_paper_ids else 0

        return min(100, int(download_pct + import_pct + index_pct))


class DownloadTaskManager:
    """
    后台下载任务管理器（单例）。

    V33.3 新增：
      - 任务持久化：保存到 data/download_tasks.json，重启不丢失
      - 任务队列：同时只执行一个下载任务（避免 NCBI 限速），其余排队
      - 失败重试：记录失败的 PMCID，可单独重试
    """

    PERSIST_FILE = Path("data/download_tasks.json")
    MAX_HISTORY = 50  # 最多保留 50 条历史记录

    def __init__(self):
        self.tasks: Dict[str, DownloadTask] = {}
        self._lock = threading.Lock()
        self._queue: List[str] = []  # 任务队列（task_id 列表）
        self._current_task_id: Optional[str] = None  # 当前正在执行的任务
        self._load_from_disk()  # 启动时加载历史任务

    def _load_from_disk(self):
        """从 JSON 文件加载历史任务（持久化）。"""
        try:
            if self.PERSIST_FILE.exists():
                import json
                with open(self.PERSIST_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                # 只恢复已完成/失败的任务（正在运行的重启后标记为 failed）
                for task_data in data.get("tasks", []):
                    task_id = task_data.get("task_id")
                    if not task_id:
                        continue
                    # 重建 DownloadTask 对象（只恢复关键字段）
                    task = DownloadTask(task_id, task_data.get("pmc_ids", []))
                    task.status = task_data.get("status", "failed")
                    task.current_stage = task_data.get("current_stage", "failed")
                    task.downloaded = task_data.get("downloaded", 0)
                    task.download_failed = task_data.get("download_failed", 0)
                    task.download_skipped = task_data.get("download_skipped", 0)
                    task.imported = task_data.get("imported", 0)
                    task.indexed = task_data.get("indexed", 0)
                    task.new_paper_ids = task_data.get("new_paper_ids", [])
                    task.failed_pmc_ids = task_data.get("failed_pmc_ids", [])
                    task.error = task_data.get("error")
                    task.start_time = task_data.get("start_time", time.time())
                    task.end_time = task_data.get("end_time")
                    # 如果重启时任务还在运行，标记为失败
                    if task.status in ("running", "pending", "queued"):
                        task.status = "failed"
                        task.current_stage = "failed"
                        task.error = "服务重启，任务中断"
                        task.end_time = time.time()
                    self.tasks[task_id] = task
                print(f"📂 加载了 {len(self.tasks)} 条下载历史记录")
        except Exception as e:
            print(f"⚠️  加载下载历史失败: {e}")

    def _save_to_disk(self):
        """保存任务到 JSON 文件（持久化）。"""
        try:
            import json
            self.PERSIST_FILE.parent.mkdir(parents=True, exist_ok=True)
            # 只保存已完成/失败的任务（不保存正在运行的，避免重启后状态混乱）
            # 但保留最近 MAX_HISTORY 条
            all_tasks = sorted(
                self.tasks.values(),
                key=lambda t: t.start_time,
                reverse=True,
            )[:self.MAX_HISTORY]

            data = {
                "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "tasks": [
                    {
                        "task_id": t.task_id,
                        "pmc_ids": t.pmc_ids,
                        "status": t.status,
                        "current_stage": t.current_stage,
                        "total": t.total,
                        "downloaded": t.downloaded,
                        "download_failed": t.download_failed,
                        "download_skipped": t.download_skipped,
                        "imported": t.imported,
                        "indexed": t.indexed,
                        "new_paper_ids": t.new_paper_ids,
                        "failed_pmc_ids": t.failed_pmc_ids,
                        "error": t.error,
                        "start_time": t.start_time,
                        "end_time": t.end_time,
                    }
                    for t in all_tasks
                ],
            }
            with open(self.PERSIST_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"⚠️  保存下载历史失败: {e}")

    def create_task(self, pmc_ids: List[str]) -> DownloadTask:
        """创建下载任务。如果当前有任务在运行，新任务进入队列。"""
        task_id = f"dl_{uuid.uuid4().hex[:12]}"
        task = DownloadTask(task_id, pmc_ids)

        with self._lock:
            self.tasks[task_id] = task

            # 判断是否需要排队
            if self._current_task_id is not None:
                task.status = "queued"
                task.current_stage = "queued"
                self._queue.append(task_id)
                print(f"📋 任务 {task_id} 已加入队列（当前队列长度: {len(self._queue)}）")
            else:
                self._current_task_id = task_id

        self._save_to_disk()

        # V33.12: 同步到统一任务表（用同一个 task_id）
        try:
            from services.unified_task_manager import create_task as _ut_create
            _ut_create("download", {"pmc_ids": pmc_ids}, task_id=task_id)
        except:
            pass
        return task

    def mark_task_started(self, task_id: str):
        """标记任务开始执行。"""
        with self._lock:
            self._current_task_id = task_id
            task = self.tasks.get(task_id)
            if task:
                task.status = "running"
                task.current_stage = "downloading"

    def mark_task_completed(self, task_id: str):
        """标记任务完成，并启动队列中的下一个任务。"""
        with self._lock:
            self._current_task_id = None
            task = self.tasks.get(task_id)
            if task:
                task.status = "completed"
                task.current_stage = "completed"
                task.end_time = time.time()

            # 启动队列中的下一个任务
            next_task_id = None
            if self._queue:
                next_task_id = self._queue.pop(0)
                self._current_task_id = next_task_id
                next_task = self.tasks.get(next_task_id)
                if next_task:
                    next_task.status = "running"
                    next_task.current_stage = "downloading"

        self._save_to_disk()

        # V33.12: 同步到统一任务表
        try:
            from services.unified_task_manager import complete_task as _ut_complete
            _ut_complete(task_id, {"downloaded": task.total_papers if task else 0})
        except:
            pass

        # 启动下一个任务（在锁外执行，避免死锁）
        if next_task_id:
            print(f"🔄 启动队列中的下一个任务: {next_task_id}")
            from services.search.online_downloader import get_online_downloader
            downloader = get_online_downloader()
            next_task = self.get_task(next_task_id)
            if next_task:
                thread = threading.Thread(
                    target=downloader._run_download,
                    args=(next_task,),
                    daemon=True,
                )
                thread.start()

    def mark_task_failed(self, task_id: str, error: str):
        """标记任务失败，并启动队列中的下一个任务。"""
        with self._lock:
            self._current_task_id = None
            task = self.tasks.get(task_id)
            if task:
                task.status = "failed"
                task.current_stage = "failed"
                task.error = error
                task.end_time = time.time()

            # 启动队列中的下一个任务
            next_task_id = None
            if self._queue:
                next_task_id = self._queue.pop(0)
                self._current_task_id = next_task_id
                next_task = self.tasks.get(next_task_id)
                if next_task:
                    next_task.status = "running"
                    next_task.current_stage = "downloading"

        self._save_to_disk()

        # V33.12: 同步到统一任务表
        try:
            from services.unified_task_manager import fail_task as _ut_fail
            _ut_fail(task_id, error)
        except:
            pass

        # 启动下一个任务
        if next_task_id:
            print(f"🔄 启动队列中的下一个任务: {next_task_id}")
            from services.search.online_downloader import get_online_downloader
            downloader = get_online_downloader()
            next_task = self.get_task(next_task_id)
            if next_task:
                thread = threading.Thread(
                    target=downloader._run_download,
                    args=(next_task,),
                    daemon=True,
                )
                thread.start()

    def get_task(self, task_id: str) -> Optional[DownloadTask]:
        with self._lock:
            return self.tasks.get(task_id)

    def list_tasks(self, limit: int = 20) -> List[Dict]:
        """列出历史任务（按时间倒序）。"""
        with self._lock:
            all_tasks = sorted(
                self.tasks.values(),
                key=lambda t: t.start_time,
                reverse=True,
            )[:limit]
            return [t.to_dict() for t in all_tasks]

    def get_queue_status(self) -> Dict:
        """获取队列状态。"""
        with self._lock:
            return {
                "current_task_id": self._current_task_id,
                "queue_length": len(self._queue),
                "queued_task_ids": list(self._queue),
            }

    def clear_history(self) -> int:
        """清空历史记录（只保留正在运行的）。"""
        with self._lock:
            to_remove = []
            for task_id, task in self.tasks.items():
                if task.status in ("completed", "failed") and task_id != self._current_task_id:
                    to_remove.append(task_id)
            for task_id in to_remove:
                del self.tasks[task_id]
        self._save_to_disk()
        return len(to_remove)


# 全局单例
_task_manager = DownloadTaskManager()


def get_task_manager() -> DownloadTaskManager:
    return _task_manager


# ============================================================
# 在线下载器
# ============================================================

class OnlineDownloader:
    """
    在线文献下载器：下载 → 增量导入 → 增量建索引。

    使用方法：
        downloader = OnlineDownloader()
        task_id = downloader.start_download(["PMC1234567", "PMC7654321"])
        # 前端轮询 /api/search/download_status?task_id=xxx 获取进度
    """

    def __init__(self, verbose: bool = True):
        self.verbose = verbose
        self._downloader = None  # 懒加载 PMCXMLDownloader

    def _get_pmc_downloader(self):
        """懒加载 PMC XML 下载器。"""
        if self._downloader is None:
            from download_pmc_xml import PMCXMLDownloader
            self._downloader = PMCXMLDownloader(
                output_dir=XML_OUTPUT_DIR,
                verbose=self.verbose,
            )
        return self._downloader

    def start_download(self, pmc_ids: List[str]) -> str:
        """
        启动后台下载任务（异步，立即返回 task_id）。

        如果当前有任务正在执行，新任务会进入队列等待。

        Args:
            pmc_ids: PMCID 列表（如 ["PMC1234567", "PMC7654321"]）

        Returns:
            task_id: 任务 ID，用于查询进度
        """
        task = get_task_manager().create_task(pmc_ids)

        # 如果任务是 queued 状态，不立即启动（等队列调度）
        if task.status == "queued":
            if self.verbose:
                print(f"📋 下载任务已加入队列: {task.task_id}（{len(pmc_ids)} 篇），当前队列位置: {len(get_task_manager()._queue)}")
            return task.task_id

        # 后台线程执行
        thread = threading.Thread(
            target=self._run_download,
            args=(task,),
            daemon=True,
        )
        thread.start()

        if self.verbose:
            print(f"🚀 下载任务已启动: {task.task_id}（{len(pmc_ids)} 篇）")

        return task.task_id

    def _run_download(self, task: DownloadTask):
        """
        后台执行完整下载流程：下载 → 导入 → 建索引。
        """
        try:
            # V33.3: 标记任务开始执行
            get_task_manager().mark_task_started(task.task_id)

            # ===== 阶段1：下载 =====
            if self.verbose:
                print(f"\n{'='*60}")
                print(f"📥 阶段 1/3: 下载 {len(task.pmc_ids)} 篇 PMC 全文")
                print(f"{'='*60}")

            downloader = self._get_pmc_downloader()

            for i, pmc_id in enumerate(task.pmc_ids, 1):
                if self.verbose:
                    print(f"  [{i}/{len(task.pmc_ids)}] {pmc_id}", end=" ")

                # 检查是否已存在
                xml_file = Path(XML_OUTPUT_DIR) / f"{pmc_id}.xml"
                if xml_file.exists() and xml_file.stat().st_size > 1024:
                    if self.verbose:
                        print("⏭️  已存在，跳过")
                    task.download_skipped += 1
                    task.new_paper_ids.append(pmc_id)
                    continue

                # 下载
                success = downloader.download_xml(pmc_id)
                if success:
                    task.downloaded += 1
                    task.new_paper_ids.append(pmc_id)
                else:
                    task.download_failed += 1
                    task.failed_pmc_ids.append(pmc_id)  # V33.3: 记录失败的 PMCID

            if self.verbose:
                print(f"\n  ✅ 下载完成: 新下载 {task.downloaded} + 已存在 {task.download_skipped} + 失败 {task.download_failed}")
                print(f"  📚 待导入论文: {len(task.new_paper_ids)} 篇")

            # ===== 阶段2：增量导入 =====
            task.current_stage = "importing"

            if self.verbose:
                print(f"\n{'='*60}")
                print(f"📥 阶段 2/3: 增量导入到数据库（{len(task.new_paper_ids)} 篇）")
                print(f"{'='*60}")

            self._import_new_papers(task)

            # ===== 阶段3：增量建索引 =====
            task.current_stage = "indexing"

            if self.verbose:
                print(f"\n{'='*60}")
                print(f"🔢 阶段 3/3: 增量建向量索引（{len(task.new_paper_ids)} 篇）")
                print(f"{'='*60}")

            self._incremental_index(task)

            # ===== 完成 =====
            # V33.3: 使用任务管理器标记完成（会自动启动队列中的下一个任务）
            get_task_manager().mark_task_completed(task.task_id)

            if self.verbose:
                print(f"\n{'='*60}")
                print(f"✅ 下载任务完成!")
                print(f"   新下载: {task.downloaded} 篇")
                print(f"   已存在: {task.download_skipped} 篇")
                print(f"   失败: {task.download_failed} 篇")
                print(f"   导入: {task.imported} 篇")
                print(f"   索引: {task.indexed} 篇")
                if task.failed_pmc_ids:
                    print(f"   失败列表: {', '.join(task.failed_pmc_ids)}")
                print(f"   总耗时: {task.end_time - task.start_time:.1f} 秒")
                print(f"{'='*60}")

        except Exception as e:
            # V33.3: 使用任务管理器标记失败（会自动启动队列中的下一个任务）
            get_task_manager().mark_task_failed(task.task_id, str(e))
            import traceback
            traceback.print_exc()
            if self.verbose:
                print(f"❌ 下载任务失败: {e}")

    def _import_new_papers(self, task: DownloadTask):
        """Import newly downloaded XML directly into PostgreSQL."""
        from import_xml_v2 import parse_jats_xml

        if not paper_pg_writes.enabled():
            raise RuntimeError("paper write backend unavailable")

        children: list[tuple[str, list[dict], list[dict]]] = []
        paper_rows: list[dict] = []
        for i, pmc_id in enumerate(task.new_paper_ids, 1):
            xml_file = Path(XML_OUTPUT_DIR) / f"{pmc_id}.xml"
            if not xml_file.exists():
                continue
            try:
                data = parse_jats_xml(xml_file)
                if data is None or not data["title"]:
                    continue
                paper_id = f"paper_{pmc_id}_{hashlib.md5(pmc_id.encode()).hexdigest()[:8]}_xml"
                paper_rows.append(
                    {
                        "paper_id": paper_id,
                        "filename": f"{pmc_id}.xml",
                        "title": data["title"],
                        "abstract": data["abstract"] or "",
                        "authors": data["authors"] or "",
                        "journal": data.get("journal") or "",
                        "year": data.get("year"),
                        "doi": data.get("doi") or "",
                    }
                )
                paper_paragraphs = [
                    {
                        "para_id": f"{paper_id}_para_{j:05d}",
                        "section_level1": para["section"],
                        "text": para["text"],
                        "sequence": para["sequence"],
                    }
                    for j, para in enumerate(data["paragraphs"])
                ]
                children.append((paper_id, paper_paragraphs, []))
                task.imported += 1
            except Exception as bex:  # noqa: BLE001
                if self.verbose:
                    print(f"  FAIL {pmc_id}: {str(bex)[:100]}")
        paper_pg_writes.write_papers_batch(paper_rows, children)

    def _incremental_index(self, task: DownloadTask):
        """Embed only newly downloaded papers into pgvector."""
        if not task.new_paper_ids:
            return
        if os.environ.get("SCIPAL_VECTOR_BACKEND", "").strip().lower() not in {
            "pgvector", "pg_vec", "postgres"
        }:
            raise RuntimeError("pgvector backend is required for incremental indexing")

        from sentence_transformers import SentenceTransformer
        from services.db.pg_pool import ingest_connection

        model_path = LOCAL_EMBEDDING_PATH if Path(LOCAL_EMBEDDING_PATH).exists() else EMBEDDING_MODEL
        model = getattr(self, "_model", None)
        if model is None:
            model = SentenceTransformer(str(model_path), device=os.environ.get("SCIPAL_INGEST_DEVICE", "cpu"))
            self._model = model
        paper_ids = [
            f"paper_{pmc_id}_{hashlib.md5(pmc_id.encode()).hexdigest()[:8]}_xml"
            for pmc_id in task.new_paper_ids
        ]
        pg = ingest_connection()
        try:
            rows = pg.execute(
                "SELECT para_id,paper_id,section_level1,text FROM paragraphs "
                "WHERE paper_id = ANY(%s) AND length(btrim(text)) >= 10",
                (paper_ids,),
            ).fetchall()
            for start in range(0, len(rows), 256):
                batch = rows[start:start + 256]
                vectors = model.encode(
                    [row["text"] for row in batch],
                    normalize_embeddings=True,
                    show_progress_bar=False,
                )
                with pg.cursor() as cur:
                    cur.executemany(
                        "INSERT INTO paragraph_embeddings (para_id,paper_id,embedding) "
                        "VALUES (%s,%s,%s::vector) ON CONFLICT (para_id) DO NOTHING",
                        [
                            (row["para_id"], row["paper_id"], "[" + ",".join(f"{float(v):.6f}" for v in vec) + "]")
                            for row, vec in zip(batch, vectors)
                        ],
                    )
                pg.commit()
        finally:
            pg.close()
        task.indexed = len({row["paper_id"] for row in rows})

_online_downloader: Optional[OnlineDownloader] = None


def get_online_downloader() -> OnlineDownloader:
    """获取在线下载器单例。"""
    global _online_downloader
    if _online_downloader is None:
        _online_downloader = OnlineDownloader()
    return _online_downloader
