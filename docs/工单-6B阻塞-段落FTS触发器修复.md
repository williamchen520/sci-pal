# 工单：修复 `paragraphs` 写入被 FTS 触发器打断（阻塞 6-B 真解析入库）

> **派单对象**：CodeBuddy
> **优先级**：🔴 高 —— 当前**任何**新论文入库都会失败（同步 `/api/papers/parse` 与
> 6-B 的 `/api/papers/parse_async` 都挂），6-B 的「解析→入库」因此无法端到端成立。
> **性质**：**既有缺陷**（不是 6-B 引入的），被 6-B 的真解析验收趟出来。

---

## 零、背景事实（我已现查核实，**直接采信，不要重复查仓库**）

### 0.1 现象（两条路由都失败，证明与 6-B 无关）

```text
# 6-B 新增的异步路由
POST /api/papers/parse_async  {"filename":"<临时名>.pdf"}
→ task failed，error="解析成功但写入数据库失败"

# 6-A 之前就有的同步路由（同一段写库代码）
POST /api/papers/parse        {"filename":"<临时名>.pdf"}
→ HTTP 500 {"error":"解析成功但写入数据库失败"}   TIME=16.58s
```

`logs/sciPal_api.log` 里 docling 解析本身是成功的：

```text
✅ Paragraphs: 29   ✅ Figures: 2   ✅ Citations: 0
💾 Inserting paper paper__xxx into database...
❌ Error inserting paper: table paragraphs_fts has no column named section_level1
```

即：**解析 100% 成功，卡在 `DatabaseWriter.insert_paper()` 写 `paragraphs` 表的那一刻**。

### 0.2 根因：`research.db` 里 3 个遗留触发器与 FTS 表列名不匹配

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

→ 只要往 `paragraphs` 插一行，`paragraphs_ai` 就报错，整个事务回滚。

### 0.3 这三条触发器**不是仓库脚本建的**

```text
grep -rn "CREATE TRIGGER" --include=*.py .   # 排除 venv
→ 只有 build_db/build_abstracts_db.py 里的 papers_fts_insert/update/delete（那是 abstracts.db）
```

`build_db/build_fts.py:22` 会 `DROP TABLE IF EXISTS paragraphs_fts`，然后
`:28` 用 `section_l1 / section_l2` 重建。**重建 FTS 表时没有一并重建触发器**，
触发器停留在「旧列名时代」→ 从此写入必炸。

### 0.4 关键度量（决定修法，不要用 rowid）

```text
paragraphs        : 52629 行，para_id 去重后仍 52629（**para_id 唯一**）
paragraphs_fts    : 50950 行（build_fts.py 只索引 length(text) > 10 的段落，故更少），para_id 亦唯一
rowid 对齐率      : 11246 / 50950   ← **只有 22% 对齐**
```

→ **绝不能按 rowid 删/改 FTS 行**（会删错别人）。`para_id` 两边都唯一，
用它做删除键才是安全的。

库里触发器仅这 3 个（`SELECT name FROM sqlite_master WHERE type='trigger'` 全表就它仨），
不用担心里面还有别的东西在跑。

### 0.5 现有代码位置

| 位置 | 作用 |
|---|---|
| `build_db/db_writer.py:38-95` | `insert_paper()` → 成功 `True`、异常 `rollback()` + `False`（**已有正确回滚**，不必改） |
| `api_server.py:2332 run_db_migrations()` | 启动时幂等迁移，只补 `papers.volume/issue/pages` 与建 `supplementary_files` |
| `api_server.py:2478-2481` | `run_db_migrations()` → `reconcile_stale_review_tasks()`，顺序已正确 |
| `api_server.py:1751` | 6-B 的 `parse_local_paper_async()`（本次**不用改**，它已经如实把失败落成 `failed`） |

### 0.6 附带观测（**不在本工单范围，别当成你的 bug**）

验收方连跑 4 次真解析后（每次都是同一套 `ParserOrchestrator()` 新建路径），Flask worker 进程：

```text
重启后（未解析任何文件）      ：WS ≈ 1.4 GB
4 次真解析之后                ：WS 7,024 MB / Private 11,133 MB   ← 不回落
```

→ 说明「每建一次 `ParserOrchestrator` 就多留一份模型/缓冲」这个方向值得怀疑，
但**本工单不要动它**（要动就是 `_parse_lock` 之外再引入 orchestrator 复用，属另一件事）。
你只需要在报告里**不要**把「内存 11 GB」当成自己改动引入的回归即可。
真解析只跑 **1 次**（F-2 要求），跑完看内存涨了多少、如实记一行就行。

---

## 一、任务

### F-1（必须）在 `run_db_migrations()` 里加幂等触发器修复

位置：`api_server.py` 的 `run_db_migrations()` 内，**放在现有 papers 字段迁移之后**。

判据式检测，不要无脑重建：

```python
cursor.execute(
    "SELECT name, sql FROM sqlite_master WHERE type='trigger' "
    "AND name IN ('paragraphs_ai','paragraphs_ad','paragraphs_au')"
)
for name, sql in cursor.fetchall():
    if sql and "section_level1" in sql:
        needs_fix = True
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

硬要求：

1. **幂等**：第二次启动不应再 DROP/CREATE，也不应打印「修复」日志。
2. **只碰这 3 个触发器**，不许 `DROP TRIGGER` 别的。
3. **不动历史数据行**：不 UPDATE/DELETE `paragraphs` / `paragraphs_fts` 任何一行。
   （存量 FTS 行 `section_l1/l2` 是否为空不影响本次目标，别顺手回填。）
4. 失败必须**打印清楚并继续启动**（沿用现有 try/except 风格），不许因此让服务起不来。
5. 重建成功后打印一行：`🔧 触发器迁移：paragraphs_ai/ad/au 已按 section_l1|section_l2 重建`。

### F-2（必须）自证：写入 + FTS 检索 + 更新/删除 三向一致

修完必须自己验一遍（**用临时副本，验完删干净**）：

1. 复制一个**小** PDF 成临时名（如 `documents/_fix_probe.pdf`，取 `PMC13612245.pdf` 268 KB 那个）；
2. `POST /api/papers/parse_async {"filename":"_fix_probe.pdf"}` → 轮询到 `completed`，
   `result.status == "parsed"`、`paragraph_count > 0`；
3. 用 FTS 命中该论文的段落：
   `SELECT para_id FROM paragraphs_fts WHERE paragraphs_fts MATCH '<正文里出现的词>' AND paper_id = '<新 paper_id>'`
   → **至少 1 行**（证明 `paragraphs_ai` 真的写进 FTS 了）；
4. 更新一条该论文的段落（`UPDATE paragraphs SET section_level1='X' WHERE para_id=?`）后，
   FTS 里对应行仍能在 MATCH 里命中（或按新值命中），**不出现重复行**；
5. 删除该段落（`DELETE FROM paragraphs WHERE para_id=?`）后，FTS 里该 `para_id` **归零**；
6. **清理**：删 `papers` 里新增行 + 删临时 PDF，并贴出清理后的计数。

### F-3（可选，但建议）`--status` 式自检脚本或函数

在 `scripts/` 下加一个只读检查（或 `run_db_migrations` 里加 `--check` 分支），打印：

```text
paragraphs_ai/ad/au 是否存在、SQL 是否含 section_level1（旧列名 = 未修）
paragraphs_fts 列名
paragraphs / paragraphs_fts 行数、para_id 唯一性
判据：OK / BROKEN
```

目的是**下次再出现同类漂移能一眼看见**，不用靠真解析 20 秒去试。

> 如果你判断成本偏高，可以只做「`run_db_migrations` 里打印一行当前触发器状态」，
> 但要在报告里说明你选了哪种。

### F-4（顺手）两处措辞／观感

1. `reconcile_stale_review_tasks()` 的日志现在是
   `🧹 启动对账：收掉 1 个遗留 review 任务`，但白名单已含 `parse_paper` →
   改成「遗留**持久化**任务」。
2. 解析失败时 `progress` 停在 `写入数据库…`（实测：`status=failed | progress=写入数据库…`）→
   失败时把 progress 置为 `已失败`（或保留阶段 + 前缀 `失败于：`），避免前端看起来像还在跑。

---

## 二、红线

- **只改** `api_server.py`（`run_db_migrations` / 那行日志；F-4.2 若在 `parse_local_paper_async`
  内改则也允许）**+ 可选新增 `scripts/` 下的只读检查脚本 + 文档**。
- **不许改** `build_db/**`（尤其 `db_writer.py`、`build_fts.py`）、`services/**`、`mcp_server/**`。
- **不许** 动 `research.db` 的历史数据行、不许 rebuild FTS、不许改表结构（只重建触发器）。
- 不许 `git add -A`（仓库里有别人的 `_test_v3317b.py`），显式列路径。
- 提交前缀 `V33.17: 修复段落FTS触发器 —— `，**不要自己 push**。

---

## 三、验收（我会自己跑，不采信报告）

| # | 判据 | 期望 |
|---|---|---|
| 1 | 重启后首次日志 | 出现一行「触发器迁移：…已重建」 |
| 2 | 再重启一次 | **不再**打印该行（幂等） |
| 3 | 三个触发器 SQL | 不含 `section_level1`，删除走 `para_id` |
| 4 | 触发器总数 | 仍为 3（没多建、没误删） |
| 5 | 真解析端到端 | temp 副本 → `completed` / `parsed` / `paragraph_count>0` |
| 6 | FTS 命中 | `MATCH` 能查到新论文段落 ≥1 行 |
| 7 | 更新/删除一致 | 无重复行、删后归零 |
| 8 | 数据卫生 | `papers` 仍 565 行、`documents/` 仍 77 个 PDF、无临时文件 |
| 9 | 回归 | `selftest` 27/27、`precheck` 退出码 0、`/api/review/running_task` → `running=false` |

---

## 四、交付报告必须回答

1. 检测逻辑写在 `run_db_migrations()` 的哪一行之后？贴那段 diff。
2. 你用的删除键是什么？为什么不用 `rowid`（提示：见 §0.4 的 11246/50950）。
3. 真解析端到端：`task_id`、耗时、`result` 原文、FTS `MATCH` 的返回行数。
4. 更新/删除验证怎么做的？贴 SQL 与前后计数。
5. 清理结果：`papers` 行数、`documents/` 文件数、临时 PDF 是否删除。
6. 幂等怎么证明的（两次重启的日志对比）。
7. `git diff --stat` 全文；有没有碰 `build_db/**`、`services/**`、`mcp_server/**`。
