# 工单：修复 `paragraphs` 写入被 FTS 触发器打断（阻塞 6-B 真解析入库 + 去重脚本）

> **派单对象**：CodeBuddy ｜ **提出**：WorkBuddy ｜ 2026-10-25（v2：扩入复发路径）
> **优先级**：🔴 高 —— `paragraphs` 表**任何** INSERT / UPDATE / DELETE 都会失败。
> **性质**：**既有缺陷**（不是 6-B 引入的），被 6-B 的真解析验收趟出来。
>
> ✅ **T-1 已交付（2026-10-25）**：F-1 ~ F-5 全部完成。prod 实跑 1 次真解析
> （`status=parsed` / 29 段 / FTS 29 行 / `MATCH` 命中），清理后回到基线
> （papers 565 / documents 77）。**T-2（orchestrator 内存不回落）未动。**
>
> ⚠️ 一处判据修正：F-1 给的 `needs_fix = any("section_level1" in sql ...)` **不幂等** ——
> 修复后的 DDL 里必然含 `new.section_level1`（`paragraphs` 的数据源列），子串判断会
> 永远为 True、每次启动都重建打日志。实际改为比对「触发器 `INSERT INTO paragraphs_fts(列清单)`
> 的目标列」与 `PRAGMA table_info(paragraphs_fts)`，实现在
> `build_db/build_fts.py::paragraphs_triggers_need_fix()`。

---

## 零、背景事实（我已现查核实，**直接采信，不要重复查仓库**）

### 0.1 现象（三条路径全挂，证明与 6-B 无关）

```text
# ① 6-B 新增的异步路由
POST /api/papers/parse_async  {"filename":"<临时名>.pdf"}
→ task failed，error="解析成功但写入数据库失败"

# ② 6-A 之前就有的同步路由（前端「解析」按钮走这条，同一段写库代码）
POST /api/papers/parse        {"filename":"<临时名>.pdf"}
→ HTTP 500 {"error":"解析成功但写入数据库失败"}   TIME=16.58s

# ③ 去重脚本（build_db/dedup_papers.py:36 的 PAPER_ID_TABLES 含 "paragraphs"）
DELETE FROM paragraphs WHERE paper_id = ?  → 触发 paragraphs_ad → 同样报错 → 整批 rollback
```

`logs/sciPal_api.log` 里 docling 解析本身是成功的：

```text
✅ Paragraphs: 29   ✅ Figures: 2   ✅ Citations: 0
💾 Inserting paper paper__xxx into database...
❌ Error inserting paper: table paragraphs_fts has no column named section_level1
```

### 0.2 根因：3 个遗留触发器与 FTS 表列名不匹配

`paragraphs_fts` 的实际列（`PRAGMA table_info`）：

```text
['para_id', 'paper_id', 'section_l1', 'section_l2', 'text']
```

而库里 3 个触发器写的是 `section_level1 / section_level2 / section_level3`：

```sql
CREATE TRIGGER paragraphs_ai AFTER INSERT ON paragraphs BEGIN
    INSERT INTO paragraphs_fts (para_id, paper_id, section_level1, section_level2, section_level3, text)
    VALUES (new.para_id, new.paper_id, new.section_level1, new.section_level2, new.section_level3, new.text);
END
-- paragraphs_ad / paragraphs_au 同病（用 'delete' 命令 + old.section_level1/2/3）
```

### 0.3 **复发路径**（本次必须一起修，否则修好也会再坏）

`build_db/build_fts.py`：

```text
:22   conn.execute("DROP TABLE IF EXISTS paragraphs_fts")     ← 只删表，不删触发器
:28   CREATE VIRTUAL TABLE paragraphs_fts USING fts5(para_id, paper_id, section_l1, section_l2, text, ...)
:53   INSERT INTO paragraphs_fts (para_id, paper_id, section_l1, section_l2, text) ...
```

SQLite 的 `DROP TABLE` **不会**连带删掉建在别的表上的触发器 → 触发器原地保留、继续指向同名新表 →
列名从这一刻起对不上。**这就是 bug 的诞生点**，只修库不修脚本，下次谁跑一次 `build_fts.py` 立刻复现。

全仓库 `grep -rn "CREATE TRIGGER" --include=*.py .`（排除 venv）只有
`build_db/build_abstracts_db.py` 里的 `papers_fts_*`（那是 abstracts.db），
**没有任何代码负责重建 `paragraphs_ai/ad/au`** → 不会自愈。

### 0.4 关键度量（决定修法，不要用 rowid）

```text
paragraphs        : 52629 行，para_id 去重后仍 52629（**para_id 唯一**）
paragraphs_fts    : 50950 行（build_fts.py 只索引 length(text) > 10 的段落，故更少），para_id 亦唯一
rowid 对齐率      : 11246 / 50950   ← **只有 22% 对齐**
```

→ **绝不能按 rowid 删/改 FTS 行**（会删错别人）。`para_id` 两边都唯一，用它做删除键才安全。

### 0.5 代码位置

| 位置 | 作用 |
|---|---|
| `build_db/db_writer.py:38-95` | `insert_paper()` → 成功 `True`、异常 `rollback()` + `False`（**回滚已正确，不必改**） |
| `api_server.py:2332 run_db_migrations()` | 启动时幂等迁移，目前只补 `papers.volume/issue/pages` 与建 `supplementary_files` |
| `api_server.py:2478-2481` | `run_db_migrations()` → `reconcile_stale_review_tasks()`，顺序已正确 |
| `build_db/build_fts.py` | 重建 FTS 索引（91 行，`DB_PATH` 是模块常量，`build_fts()` 无参） |

### 0.6 附带观测（**不在本工单范围，别当成你的 bug**）

验收方连跑 4 次真解析后（每次都新建 `ParserOrchestrator()`），Flask worker：

```text
重启后（未解析任何文件）  ：WS ≈ 1.4 GB
4 次真解析之后            ：WS 7,024 MB / Private 11,133 MB   ← 不回落
```

→ 「每建一次 orchestrator 就多留一份」值得怀疑，但**本工单不要动**。
所以本工单的验证**只在 prod 上跑 1 次真解析**，其余验证用 DB 副本做（见 F-2）。

---

## 一、任务

### F-1（必须）`run_db_migrations()` 里加幂等触发器修复

判据式检测，不要无脑重建。

> ⚠️ **v2.1 更正（2026-10-25，交付方指出，验收方确认成立）**：本节初版给的
> `needs_fix = any("section_level1" in sql ...)` **是错的、不幂等** —— 修好之后的 DDL 里
> 必然出现 `new.section_level1`（那是 `paragraphs` 的数据源列），子串判断会永远为 `True`，
> 每次启动都 DROP/CREATE 并打日志，直接违反「幂等」硬要求。
>
> **正确判据**：把触发器里 `INSERT INTO paragraphs_fts (<列清单>)` 的**目标列**与
> `PRAGMA table_info(paragraphs_fts)` 求差集，非空才需要修。实现在
> `build_db/build_fts.py::paragraphs_triggers_need_fix()`，`api_server.py` 直接 import 调用
> （DDL 唯一真源也在 `build_fts.py` 的 `PARAGRAPHS_TRIGGER_DDL`，两处不复制）。

```python
# build_db/build_fts.py::paragraphs_triggers_need_fix(cursor) 的核心
fts_columns = {row[1] for row in cursor.execute("PRAGMA table_info(paragraphs_fts)")}
for _name, sql in cursor.execute(
    "SELECT name, sql FROM sqlite_master WHERE type='trigger' "
    "AND name IN ('paragraphs_ai','paragraphs_ad','paragraphs_au')"
):
    for column_list in re.findall(r"INSERT\s+INTO\s+paragraphs_fts\s*\(([^)]*)\)", sql or "", re.I):
        names = {p.strip().split()[-1].strip('"`[]') for p in column_list.split(",") if p.strip()}
        if names - {"paragraphs_fts", "rowid"} - fts_columns:
            return True          # 目标列里出现 FTS 表不存在的列 → 需要修
return False
```

需要修就 `DROP TRIGGER IF EXISTS` + 重建三条，**列名与 FTS 表一致，删除/更新走 `para_id`**：

```sql
CREATE TRIGGER paragraphs_ai AFTER INSERT ON paragraphs BEGIN
  INSERT INTO paragraphs_fts (para_id, paper_id, section_l1, section_l2, text)
  VALUES (new.para_id, new.paper_id, new.section_level1, new.section_level2, new.text);
END;

CREATE TRIGGER paragraphs_ad AFTER DELETE ON paragraphs BEGIN
  DELETE FROM paragraphs_fts WHERE para_id = old.para_id;
END;

CREATE TRIGGER paragraphs_au AFTER UPDATE ON paragraphs BEGIN
  DELETE FROM paragraphs_fts WHERE para_id = old.para_id;
  INSERT INTO paragraphs_fts (para_id, paper_id, section_l1, section_l2, text)
  VALUES (new.para_id, new.paper_id, new.section_level1, new.section_level2, new.text);
END;
```

硬要求：幂等（第二次启动不再 DROP/CREATE、不再打日志）；只碰这 3 个触发器；
不动历史数据行、不 rebuild 存量 FTS；失败要打印清楚但**不许阻塞启动**；
成功后打一行 `🔧 触发器迁移：paragraphs_ai/ad/au 已按 section_l1|section_l2 重建`。

### F-2（必须）`build_fts.py` 重建 FTS 后一并重建触发器（堵复发）

在 `build_db/build_fts.py` 里，`paragraphs_fts` 建好并填充完（`conn.commit()` 之后）：
`DROP TRIGGER IF EXISTS` 三条 → 用与 F-1 **完全相同**的 DDL 重建。

同时给脚本加一个可选的库路径入口（二选一，便于在副本上验证、也避免误重建生产库）：

```python
def build_fts(db_path: str | Path | None = None): ...           # 默认仍用模块 DB_PATH
# 或 if __name__ == "__main__": argparse 收 --db
```

> 触发器 DDL 建议抽成一个模块级常量/函数，`build_fts.py` 与 `run_db_migrations`
> 各自 import 或复制**同一份文本**，并在两处注释里互相指认（避免以后又只改一边）。

### F-3（必须）三向自证 —— **在 DB 副本上做，不碰生产库**

```powershell
cp data/research.db data/_fts_probe.db     # 副本，验完删掉
```

在副本上（纯 sqlite3 脚本，**不启动 Flask、不跑 docling**）：

1. `INSERT INTO paragraphs (para_id, paper_id, section_level1, section_level2, text, sequence) VALUES (...)`
   → **必须成功**（这就是当前必失败的那一步）；
2. `INSERT INTO paragraphs_fts` 里能否用 `MATCH` 查到这条（`paragraphs_ai` 生效）；
3. `UPDATE paragraphs SET section_level1='X' WHERE para_id=?` → FTS 里该 para_id **不出现重复行**，且能按新值命中；
4. `DELETE FROM paragraphs WHERE para_id=?` → FTS 里该 para_id **归零**；
5. `DELETE FROM paragraphs WHERE paper_id='<某个已有论文>'` 会连带把它的 FTS 行删干净 ——
   **不要真跑这条**（会删历史数据），改成：只对第 1 步插入的那条做 3/4 两步验证即可；
6. 附上 `SELECT count(*) FROM paragraphs_fts` 前后对比（除自测行外应无变化）。

### F-4（必须）prod 端到端 —— **只跑 1 次真解析**

1. 复制**最小**的 PDF 成临时名（`documents/PMC13612245.pdf` 268 KB → `documents/_fix_probe.pdf`）；
2. `POST /api/papers/parse_async {"filename":"_fix_probe.pdf"}` → 轮询到 `completed`，
   `result.status == "parsed"`、`paragraph_count > 0`；
3. 用 `MATCH` 命中该论文段落 ≥1 行（证明 `paragraphs_ai` 在生产库也生效）；
4. **清理**：删 `papers`/`paragraphs`/`figures`/`citations`/`tables` 里该 paper 的行 +
   该论文的 FTS 行 + 临时 PDF，并贴出清理后的计数（`papers` 应回到 565、`documents/` 回到 77）。

### F-5（顺手，各一行）

1. `reconcile_stale_review_tasks()` 的日志 `🧹 启动对账：收掉 N 个遗留 review 任务` →
   白名单已含 `parse_paper`，改成「遗留**持久化**任务」。
2. 解析失败时 `progress` 停在 `写入数据库…`（实测 `status=failed | progress=写入数据库…`）→
   失败分支把 `progress_text` 置为 `已失败`（或 `失败于：<阶段>`）。

---

## 二、红线

- **允许改**：`api_server.py`（仅 `run_db_migrations` + 那行日志 + 解析失败时的 progress）、
  `build_db/build_fts.py`（仅 F-2 范围）、`scripts/` 下新增只读检查、文档。
- **不许改**：`build_db/db_writer.py`、`build_db/dedup_papers.py`、`services/**`、`mcp_server/**`。
- **不许**：动 `research.db` 的历史数据行（`paragraphs` / `paragraphs_fts` / `papers` 一行都不许改）、
  不许在生产库上 rebuild FTS、不许改表结构（只重建触发器）。
- 副本文件（`data/_fts_probe.db`）验完必须删掉。
- 不许 `git add -A`（仓库里有别人的 `_test_v3317b.py`），显式列路径。
- 提交前缀 `V33.17: 修复段落FTS触发器 —— `，**不要自己 push**。

---

## 三、验收（我会自己跑，不采信报告）

| # | 判据 | 期望 |
|---|---|---|
| 1 | 重启后首次日志 | 出现「触发器迁移：…已重建」 |
| 2 | 再重启一次 | **不再**打印该行（幂等） |
| 3 | 三个触发器 SQL | 不含 `section_level1`；删除走 `para_id` |
| 4 | 触发器总数 | 仍为 3（没多建、没误删） |
| 5 | **副本三向自证** | insert 成功 + MATCH 命中 + update 无重复 + delete 归零 |
| 6 | **`build_fts.py` 复发测试** | 在**副本**上跑一次 `build_fts(--db 副本)` → 触发器仍在且 SQL 正确 → 副本再 insert 仍成功 |
| 7 | prod 真解析 | temp 副本 → `completed` / `parsed` / `paragraph_count>0` / MATCH ≥1 |
| 8 | 数据卫生 | `papers` 565、`documents/` 77、无临时文件、无 `data/_fts_probe.db` |
| 9 | 回归 | `selftest` 27/27、`precheck` 退出码 0、`running_task` → `running=false` |

判据 6 是本工单与 v1 的关键差别：**只证明「库修好了」不够，必须证明「再跑一次 build_fts 也不会坏」**。

---

## 四、交付报告必须回答

1. F-1 的检测逻辑贴在哪一段之后？贴 diff。
2. 删除键为什么用 `para_id` 不用 `rowid`（提示 §0.4：11246/50950）。
3. 触发器 DDL 是「抽公共常量」还是「两处复制」？如果复制，怎么保证两处一致（贴两处代码）。
4. 副本三向自证：四条 SQL 与前后计数。
5. **复发测试**：在副本上跑 `build_fts` 的完整命令、耗时、跑完后触发器 SQL 与一次 insert 的结果。
6. prod 真解析：`task_id`、耗时、`result` 原文、MATCH 行数、清理后 `papers`/`documents` 计数。
7. 幂等证明（两次重启日志对比）。
8. `git diff --stat` 全文；有没有碰 `db_writer.py` / `dedup_papers.py` / `services/**` / `mcp_server/**`。
