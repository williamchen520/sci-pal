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
import sqlite3
import threading
import time
import uuid
from pathlib import Path
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
DB_PATH = "data/research.db"
CHROMA_PATH = "data/chroma"
XML_OUTPUT_DIR = "documents_xml"
COLLECTION_NAME = "sci_pal_paragraphs"

# Embedding 模型（跟主程序一致：bge-base-en-v1.5）
EMBEDDING_MODEL = "BAAI/bge-base-en-v1.5"
# 本地模型路径（如果有的话优先用本地）
LOCAL_EMBEDDING_PATH = "D:/models/models/BAAI--bge-base-en-v1.5"


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

        # 阶段：pending → downloading → importing → indexing → completed / failed
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
            "error": self.error,
            "elapsed_seconds": round(elapsed, 1),
            "progress_percent": self._progress_percent(),
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
    """
    def __init__(self):
        self.tasks: Dict[str, DownloadTask] = {}
        self._lock = threading.Lock()

    def create_task(self, pmc_ids: List[str]) -> DownloadTask:
        task_id = f"dl_{uuid.uuid4().hex[:12]}"
        task = DownloadTask(task_id, pmc_ids)
        with self._lock:
            self.tasks[task_id] = task
        return task

    def get_task(self, task_id: str) -> Optional[DownloadTask]:
        with self._lock:
            return self.tasks.get(task_id)

    def list_tasks(self) -> List[Dict]:
        with self._lock:
            return [t.to_dict() for t in self.tasks.values()]


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

        Args:
            pmc_ids: PMCID 列表（如 ["PMC1234567", "PMC7654321"]）

        Returns:
            task_id: 任务 ID，用于查询进度
        """
        task = get_task_manager().create_task(pmc_ids)

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
            task.status = "running"
            task.current_stage = "downloading"

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
            task.status = "completed"
            task.current_stage = "completed"
            task.end_time = time.time()

            if self.verbose:
                print(f"\n{'='*60}")
                print(f"✅ 下载任务完成!")
                print(f"   新下载: {task.downloaded} 篇")
                print(f"   已存在: {task.download_skipped} 篇")
                print(f"   失败: {task.download_failed} 篇")
                print(f"   导入: {task.imported} 篇")
                print(f"   索引: {task.indexed} 篇")
                print(f"   总耗时: {task.end_time - task.start_time:.1f} 秒")
                print(f"{'='*60}")

        except Exception as e:
            task.status = "failed"
            task.error = str(e)
            task.end_time = time.time()
            import traceback
            traceback.print_exc()
            if self.verbose:
                print(f"❌ 下载任务失败: {e}")

    def _import_new_papers(self, task: DownloadTask):
        """
        增量导入新下载的论文到数据库（只导入新的，不清空旧数据）。
        """
        from import_xml_v2 import parse_jats_xml

        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()

        for i, pmc_id in enumerate(task.new_paper_ids, 1):
            xml_file = Path(XML_OUTPUT_DIR) / f"{pmc_id}.xml"

            if not xml_file.exists():
                if self.verbose:
                    print(f"  ⚠️  {pmc_id}: 文件不存在，跳过")
                continue

            try:
                data = parse_jats_xml(xml_file)

                if data is None or not data["title"]:
                    if self.verbose:
                        print(f"  ⚠️  {pmc_id}: 无标题，跳过")
                    continue

                # 生成 paper_id（跟 import_xml_v2.py 一致）
                paper_hash = hashlib.md5(pmc_id.encode()).hexdigest()[:8]
                paper_id = f"paper_{pmc_id}_{paper_hash}_xml"

                # INSERT OR REPLACE：如果已存在就更新，不存在就插入
                c.execute("""
                    INSERT OR REPLACE INTO papers
                    (paper_id, filename, title, abstract, authors, parse_engine)
                    VALUES (?, ?, ?, ?, ?, 'xml')
                """, (paper_id, f"{pmc_id}.xml", data["title"], data["abstract"], data["authors"]))

                # 先删除这篇论文旧的段落（如果有），再插入新的
                c.execute("DELETE FROM paragraphs WHERE paper_id = ?", (paper_id,))

                # 插入段落
                for j, para in enumerate(data["paragraphs"]):
                    para_id = f"{paper_id}_para_{j:05d}"
                    c.execute("""
                        INSERT OR REPLACE INTO paragraphs
                        (para_id, paper_id, section_level1, text, sequence, parse_engine)
                        VALUES (?, ?, ?, ?, ?, 'xml')
                    """, (para_id, paper_id, para["section"], para["text"], para["sequence"]))

                task.imported += 1

                if self.verbose:
                    print(f"  ✅ [{i}/{len(task.new_paper_ids)}] {pmc_id}: {len(data['paragraphs'])} 段落")

            except Exception as e:
                if self.verbose:
                    print(f"  ❌ [{i}/{len(task.new_paper_ids)}] {pmc_id}: {str(e)[:100]}")

        conn.commit()
        conn.close()

        if self.verbose:
            print(f"  ✅ 增量导入完成: {task.imported} 篇")

    def _incremental_index(self, task: DownloadTask):
        """
        增量建向量索引（只对新论文的段落做 embedding，追加到 chroma，不重建整个库）。
        """
        if not task.new_paper_ids:
            if self.verbose:
                print("  ℹ️  无新论文，跳过索引")
            return

        try:
            import chromadb
            from sentence_transformers import SentenceTransformer
        except ImportError as e:
            if self.verbose:
                print(f"  ⚠️  缺少依赖: {e}，跳过索引")
            return

        # 1. 加载 embedding 模型（优先本地路径）
        model_path = LOCAL_EMBEDDING_PATH if Path(LOCAL_EMBEDDING_PATH).exists() else EMBEDDING_MODEL
        if self.verbose:
            print(f"  📥 加载 embedding 模型: {model_path}")

        try:
            model = SentenceTransformer(model_path)
        except Exception as e:
            if self.verbose:
                print(f"  ⚠️  本地模型加载失败，尝试在线加载: {e}")
            model = SentenceTransformer(EMBEDDING_MODEL)

        # 2. 连接 ChromaDB（获取现有 collection，不删除！）
        if self.verbose:
            print(f"  📥 连接 ChromaDB: {CHROMA_PATH}")
        client = chromadb.PersistentClient(path=CHROMA_PATH)

        # 获取或创建 collection（不删除旧的！）
        try:
            collection = client.get_collection(name=COLLECTION_NAME)
            if self.verbose:
                print(f"  ✅ 现有 collection 已加载（增量追加模式）")
        except Exception:
            collection = client.create_collection(
                name=COLLECTION_NAME,
                metadata={"hnsw:space": "cosine"},
            )
            if self.verbose:
                print(f"  ✅ 新 collection 已创建")

        # 3. 查询新论文的段落
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row

        # 构造 paper_id 列表（跟导入时的格式一致）
        paper_ids = []
        for pmc_id in task.new_paper_ids:
            paper_hash = hashlib.md5(pmc_id.encode()).hexdigest()[:8]
            paper_ids.append(f"paper_{pmc_id}_{paper_hash}_xml")

        if not paper_ids:
            conn.close()
            return

        # 查询这些论文的所有段落
        placeholders = ",".join("?" * len(paper_ids))
        cursor = conn.execute(f"""
            SELECT para_id, paper_id, section_level1, text
            FROM paragraphs
            WHERE paper_id IN ({placeholders})
        """, paper_ids)
        rows = cursor.fetchall()
        conn.close()

        if self.verbose:
            print(f"  📊 新论文段落数: {len(rows)}")

        if not rows:
            if self.verbose:
                print("  ℹ️  无段落，跳过索引")
            return

        # 4. 批量 embedding + 增量追加到 chroma
        batch_size = 256  # 小批量，避免内存溢出
        total_indexed_paras = 0

        for i in range(0, len(rows), batch_size):
            batch = rows[i:i + batch_size]

            ids = [row["para_id"] for row in batch]
            documents = [row["text"] for row in batch]
            metadatas = [
                {
                    "paper_id": row["paper_id"] or "",
                    "section_l1": row["section_level1"] or "",
                }
                for row in batch
            ]

            # 做 embedding
            embeddings = model.encode(documents).tolist()

            # 增量追加到 chroma（collection.add 会自动去重，相同 ID 会更新）
            collection.add(
                ids=ids,
                documents=documents,
                metadatas=metadatas,
                embeddings=embeddings,
            )

            total_indexed_paras += len(batch)
            if self.verbose:
                print(f"  🔢 已索引 {total_indexed_paras}/{len(rows)} 段落")

        # 统计索引了多少篇论文
        indexed_paper_ids = set(row["paper_id"] for row in rows)
        task.indexed = len(indexed_paper_ids)

        if self.verbose:
            print(f"  ✅ 增量索引完成: {task.indexed} 篇论文，{total_indexed_paras} 段落")
            print(f"  ✅ 向量库已自动更新，检索层无需改动，新论文立即可搜！")


# ============================================================
# 单例
# ============================================================

_online_downloader: Optional[OnlineDownloader] = None


def get_online_downloader() -> OnlineDownloader:
    """获取在线下载器单例。"""
    global _online_downloader
    if _online_downloader is None:
        _online_downloader = OnlineDownloader()
    return _online_downloader
