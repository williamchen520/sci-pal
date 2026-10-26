"""
Build FTS5 full-text search index for paragraphs.
V21.0 - Full-text search layer
V33.17 - 重建 FTS 后**必须**一并重建 paragraphs_ai/ad/au 触发器（见 PARAGRAPHS_TRIGGER_DDL）
"""
import argparse
import re
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = PROJECT_ROOT / "data" / "research.db"

# ---------------------------------------------------------------------------
# V33.17: 段落 FTS 触发器 DDL —— **全仓库唯一真源**
#
# 为什么必须有这段：`paragraphs_fts` 被本脚本按 5 列重建
# （para_id / paper_id / section_l1 / section_l2 / text），但 SQLite 的
# `DROP TABLE` **不会**连带删掉建在 `paragraphs` 上的触发器 —— 三个旧触发器
# 原地保留、继续引用 section_level1/2/3 → `paragraphs` 的任何
# INSERT/UPDATE/DELETE 都报 `table paragraphs_fts has no column named
# section_level1`，入库与去重脚本全挂。
#
# ⚠️ **不要在任何别处另抄一份 DDL。**
#    `api_server.py::run_db_migrations()` 通过
#    `from build_db.build_fts import rebuild_paragraphs_triggers` 调用本文件的
#    函数（判据：触发器 SQL 里还含 `section_level1` 就重建）。改这里即两处同时生效。
#
# 两条约束（改坏就等于没修）：
#   1. 删除/更新只能按 `para_id` 定位 —— `paragraphs_fts.rowid` 与
#      `paragraphs.rowid` 对齐率仅 11246/50950（22%），按 rowid 删会删错别人的行。
#   2. 列名必须与 `paragraphs_fts` 实际列一致：只有 section_l1 / section_l2
#      两级（旧的 section_level3 在 FTS 表里根本不存在）。
# ---------------------------------------------------------------------------
PARAGRAPHS_TRIGGER_NAMES = ("paragraphs_ai", "paragraphs_ad", "paragraphs_au")

PARAGRAPHS_TRIGGER_DDL = (
    """
CREATE TRIGGER paragraphs_ai AFTER INSERT ON paragraphs BEGIN
  INSERT INTO paragraphs_fts (para_id, paper_id, section_l1, section_l2, text)
  VALUES (new.para_id, new.paper_id, new.section_level1, new.section_level2, new.text);
END
""",
    """
CREATE TRIGGER paragraphs_ad AFTER DELETE ON paragraphs BEGIN
  DELETE FROM paragraphs_fts WHERE para_id = old.para_id;
END
""",
    """
CREATE TRIGGER paragraphs_au AFTER UPDATE ON paragraphs BEGIN
  DELETE FROM paragraphs_fts WHERE para_id = old.para_id;
  INSERT INTO paragraphs_fts (para_id, paper_id, section_l1, section_l2, text)
  VALUES (new.para_id, new.paper_id, new.section_level1, new.section_level2, new.text);
END
""",
)


def rebuild_paragraphs_triggers(cursor) -> None:
    """DROP + CREATE 三个段落 FTS 触发器（幂等，调用方负责 commit）。

    Args:
        cursor: `sqlite3.Connection` 或 `sqlite3.Cursor` 均可（两者都有 `.execute`）

    ⚠️ 前提：`paragraphs_fts` 表已存在（触发器引用它的列名）。
    """
    for name in PARAGRAPHS_TRIGGER_NAMES:
        cursor.execute(f"DROP TRIGGER IF EXISTS {name}")
    for ddl in PARAGRAPHS_TRIGGER_DDL:
        cursor.execute(ddl)


PAPERS_TRIGGER_NAMES = ("papers_ai", "papers_ad", "papers_au")

PAPERS_TRIGGER_DDL = (
    """
CREATE TRIGGER papers_ai AFTER INSERT ON papers BEGIN
  INSERT INTO papers_fts (paper_id, title, authors, journal)
  VALUES (new.paper_id, new.title, new.authors, new.journal);
END
""",
    """
CREATE TRIGGER papers_ad AFTER DELETE ON papers BEGIN
  DELETE FROM papers_fts WHERE paper_id = old.paper_id;
END
""",
    """
CREATE TRIGGER papers_au AFTER UPDATE ON papers BEGIN
  DELETE FROM papers_fts WHERE paper_id = old.paper_id;
  INSERT INTO papers_fts (paper_id, title, authors, journal)
  VALUES (new.paper_id, new.title, new.authors, new.journal);
END
""",
)


def rebuild_papers_triggers(cursor) -> None:
    """论文级 FTS 触发器：入库/更新/删除论文时同步 papers_fts。"""
    for name in PAPERS_TRIGGER_NAMES:
        cursor.execute(f"DROP TRIGGER IF EXISTS {name}")
    for ddl in PAPERS_TRIGGER_DDL:
        cursor.execute(ddl)


# `INSERT INTO paragraphs_fts(...)` 的列清单里，这两个不是 FTS 表的真实列：
#   paragraphs_fts —— FTS5 的命令列（`'delete'` 用）
#   rowid          —— 隐式列
_FTS_PSEUDO_COLUMNS = {"paragraphs_fts", "rowid"}


def paragraphs_triggers_need_fix(cursor) -> bool:
    """三个段落 FTS 触发器是否与 `paragraphs_fts` 实际列不匹配（需要重建）。

    ⚠️ **不能**用 `"section_level1" in sql` 判断 —— 修复后的 DDL 里必须出现
    `new.section_level1` / `new.section_level2`，那是 `paragraphs` 表的真实列
    （数据源），只是目标列不叫这个。用子串判断会导致「永远 needs_fix」：
    每次启动都 DROP/CREATE 一遍并打日志，破坏幂等。

    正确判据：把触发器里 `INSERT INTO paragraphs_fts (<列清单>)` 的目标列
    与 `PRAGMA table_info(paragraphs_fts)` 比对，只要出现 FTS 表里不存在的列
    （如 section_level1 / section_level2 / section_level3）就判定需要修。
    """
    rows = cursor.execute(
        "SELECT name, sql FROM sqlite_master WHERE type='trigger' "
        "AND name IN ('paragraphs_ai','paragraphs_ad','paragraphs_au')"
    ).fetchall()
    if not rows:
        return False  # 一个都没有 → 没有可修的目标（新建库不在此处处理）

    fts_columns = {
        row[1] for row in cursor.execute("PRAGMA table_info(paragraphs_fts)").fetchall()
    }
    if not fts_columns:
        return False  # FTS 表不存在 → 由 build_fts.py 负责整表重建

    for _name, sql in rows:
        if not sql:
            continue
        for column_list in re.findall(
            r"INSERT\s+INTO\s+paragraphs_fts\s*\(([^)]*)\)", sql, flags=re.IGNORECASE
        ):
            names = {
                part.strip().split()[-1].strip('"`[]') for part in column_list.split(",") if part.strip()
            }
            if names - _FTS_PSEUDO_COLUMNS - fts_columns:
                return True
    return False


def build_fts(db_path: str | Path | None = None):
    """Create FTS5 virtual table and populate it.

    Args:
        db_path: 目标库路径。默认 `data/research.db`；
                 验证时请显式指向副本（如 `data/_fts_probe.db`），**不要**拿生产库试。
    """
    target = Path(db_path) if db_path else DB_PATH

    print("=" * 60)
    print("🔍 Building Full-Text Search Index (FTS5)")
    print(f"   DB: {target}")
    print("=" * 60)

    conn = sqlite3.connect(str(target))
    conn.row_factory = sqlite3.Row

    # Drop existing FTS table if any
    conn.execute("DROP TABLE IF EXISTS paragraphs_fts")
    conn.commit()

    # Create FTS5 virtual table
    print("\n📋 Creating FTS5 virtual table...")
    conn.execute("""
        CREATE VIRTUAL TABLE paragraphs_fts USING fts5(
            para_id UNINDEXED,
            paper_id UNINDEXED,
            section_l1,
            section_l2,
            text,
            tokenize = 'unicode61 remove_diacritics 2'
        )
    """)
    conn.commit()

    # Populate from paragraphs
    print("📥 Populating FTS index...")
    rows = conn.execute("""
        SELECT para_id, paper_id, section_level1, section_level2, text
        FROM paragraphs
        WHERE text IS NOT NULL AND length(text) > 10
    """).fetchall()

    print(f"   Indexing {len(rows)} paragraphs...")

    batch_size = 1000
    for i in range(0, len(rows), batch_size):
        batch = rows[i:i+batch_size]
        conn.executemany("""
            INSERT INTO paragraphs_fts (para_id, paper_id, section_l1, section_l2, text)
            VALUES (?, ?, ?, ?, ?)
        """, [(
            r["para_id"],
            r["paper_id"],
            r["section_level1"] or "",
            r["section_level2"] or "",
            r["text"]
        ) for r in batch])
        conn.commit()
        print(f"   [{min(i+batch_size, len(rows))}/{len(rows)}] indexed...")

    # V33.17: 重建段落 FTS 触发器（堵住「跑一次 build_fts 就复发」的路径）。
    # 必须放在 paragraphs_fts 建好并填充完之后 —— 触发器引用它的列名。
    # 不重建的话：上面的 DROP TABLE 不删触发器，旧触发器仍写 section_level1/2/3，
    # 之后任何 paragraphs 的写入都会失败。
    rebuild_paragraphs_triggers(conn)
    conn.commit()
    print("🔧 触发器：paragraphs_ai/ad/au 已按 section_l1|section_l2 重建")

    # Also index paper titles
    conn.execute("DROP TABLE IF EXISTS papers_fts")
    conn.execute("""
        CREATE VIRTUAL TABLE papers_fts USING fts5(
            paper_id UNINDEXED,
            title,
            authors,
            journal,
            tokenize = 'unicode61 remove_diacritics 2'
        )
    """)
    conn.commit()

    papers = conn.execute("SELECT paper_id, title, authors, journal FROM papers").fetchall()
    conn.executemany("""
        INSERT INTO papers_fts (paper_id, title, authors, journal)
        VALUES (?, ?, ?, ?)
    """, [(p["paper_id"], p["title"] or "", p["authors"] or "", p["journal"] or "") for p in papers])
    rebuild_papers_triggers(conn)
    conn.commit()
    print(f"   Indexed {len(papers)} papers")
    print("🔧 触发器：papers_ai/ad/au 已重建（入库即进 papers_fts）")

    conn.close()
    print("\n✅ FTS5 index built successfully!")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="重建 paragraphs / papers 的 FTS5 索引")
    parser.add_argument(
        "--db",
        default=None,
        help="目标库路径；默认 data/research.db。验证请指向副本（如 data/_fts_probe.db）",
    )
    build_fts(parser.parse_args().db)
