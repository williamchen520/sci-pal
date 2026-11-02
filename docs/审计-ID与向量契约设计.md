# ID / 向量契约审计设计

> 日期：2026-11-03  
> 状态：**设计，不写实现**  
> 目标：判断编号混入是否已造成向量回表失败、覆盖缺口或层级断裂

---

## 1. 审计问题

```text
Q1 向量 ID 能否解析到唯一数据库行？
Q2 数据库行是否都有向量？
Q3 同一实体在 SQLite / PG 是否使用同一 ID？
Q4 章节 / 段 / 句的编号格式是否只有一套？
Q5 向量的 metadata 是否带齐层级 ID？
Q6 句子证据链是否因 sentence_id 不一致而断？
```

---

## 2. 契约定义

### C1 身份契约

```text
section_uid / para_uid / sentence_uid
必须在 SQLite 与 PG 中一致
```

当前实现用：

```text
section_id / para_id / sentence_id
```

审计时按现状检查，不预设 UID 已存在。

### C2 向量回表契约

```text
Chroma id -> 数据库唯一一行
```

要求：

```text
命中率 = 100%
重复解析 = 0
孤儿向量 = 0
```

### C3 metadata 契约

每个向量至少包含：

```text
paper_id
section_id（若属于章节）
para_id（若属于段落）
source_type
schema_version
```

`sentence_id` 用于句级向量；当前句级向量不存在。

### C4 层级契约

```text
sentence.para_id -> paragraphs.para_id
paragraph.section_id -> sections.section_id
```

不允许：

```text
句子挂在不存在段落
段落挂在不存在章节
```

### C5 覆盖契约

```text
数据库实体数 vs 向量数
```

按集合分别统计，不用总量掩盖局部缺口。

---

## 3. 审计对象

### 3.1 数据库

```text
SQLite: G:\sciPal_deploy\data\research.db
PG:     scipal_bench
```

表：

```text
papers
sections
paragraphs
sentences
sentence_links
figures
tables
```

### 3.2 向量库

```text
G:\sciPal_deploy\data\chroma
```

集合：

```text
paragraphs
paragraphs_contextual
papers
section_summaries
figures
tables
chunks（若存在）
```

### 3.3 只读

```text
审计脚本必须只读
不写 SQLite / PG / Chroma
```

---

## 4. 指标

### 4.1 向量解析

```text
vector_total
vector_unique_ids
vector_resolved
vector_orphan
vector_duplicate_ids
vector_resolution_rate = resolved / unique_ids
```

### 4.2 数据库覆盖

```text
db_total
db_with_vector
db_coverage = with_vector / total
```

按集合分别算：

```text
papers
sections
paragraphs
paragraphs_contextual
figures
tables
```

### 4.3 ID 一致性

```text
sqlite_ids
pg_ids
same_ids
sqlite_only
pg_only
id_consistency = same / union
```

对象：

```text
sections.section_id
paragraphs.para_id
sentences.sentence_id
```

### 4.4 编号格式分布

正则分类：

```text
^para_paper_.+_\d{4}$
^paper_.+_para_\d{5}$
^sec_paper_.+_\d{4}$
^.+_sent_\d{3}$
其他
```

输出：

```text
每种格式数量
按 XML / PDF / preprint 分组
```

### 4.5 metadata 完整性

必填字段：

```text
paper_id
section_id（段落级可选）
para_id（句子级可选）
source_type
schema_version
```

计算：

```text
metadata_complete_rate
```

### 4.6 层级一致性

```text
orphan_sections
orphan_paragraphs
orphan_sentences
section_mismatch
```

### 4.7 句子证据链

```text
gold_sentence_total
same_id
text_match_only
missing
```

使用现有 17 条 gold sentence 做精确检查，不做模糊匹配。

---

## 5. 通过 / 失败建议

### 硬失败

```text
vector_resolution_rate < 99.9%
vector_duplicate_ids > 0
paragraph/section ID consistency < 100%
sentence text match < 100%
metadata_complete_rate < 99.9%
```

### 覆盖目标

```text
paragraphs coverage        >= 95%
paragraphs_contextual      >= 95%
sections summaries         >= 95%
papers                     >= 90%
figures / tables           先报告，不阻断
```

### 只报告

```text
编号格式分布
chunk 边界一致性
Gini / 长尾
```

---

## 6. 输出

### JSON

```json
{
  "generated_at": "",
  "sqlite": "",
  "pg": "",
  "chroma": "",
  "collections": {
    "paragraphs": {
      "vector_total": 0,
      "vector_resolved": 0,
      "vector_orphan": 0,
      "vector_duplicate_ids": 0,
      "db_total": 0,
      "db_with_vector": 0
    }
  },
  "ids": {
    "sections": {"same": 0, "sqlite_only": 0, "pg_only": 0},
    "paragraphs": {"same": 0, "sqlite_only": 0, "pg_only": 0},
    "sentences": {"same": 0, "sqlite_only": 0, "pg_only": 0}
  },
  "id_formats": {},
  "metadata": {},
  "hierarchy": {},
  "sentence_evidence": {},
  "verdict": "pass|fail|warn"
}
```

### CSV

逐项明细：

```text
collection, vector_id, status, db_table, db_id, reason
```

---

## 7. 决策树

### 情况 A：解析率高，覆盖低

```text
向量 ID 没问题
-> 只补缺失实体向量
```

### 情况 B：解析率低，覆盖高

```text
向量陈旧或 ID 规则变化
-> 优先重建向量
```

### 情况 C：ID 一致性低

```text
SQLite/PG 编号分叉
-> 先做 UID / 映射，不重建向量
```

### 情况 D：句子文本匹配 100%，ID 不一致

```text
句子 ID 是显示/绑定问题
-> 不影响段向量召回
-> 修 sentence 映射
```

### 情况 E：层级孤儿高

```text
编号或写入顺序问题
-> 先修数据，再谈向量
```

---

## 8. 实施计划（后续）

```text
1. 新增只读脚本
   scripts/audit_id_vector_contract.py

2. 参数
   --sqlite
   --pg-dsn
   --chroma
   --out
   --sample

3. 运行顺序
   SQLite IDs
   -> PG IDs
   -> Chroma IDs
   -> 交叉解析
   -> 格式分类
   -> 层级检查
   -> 句子证据检查

4. 输出
   eval/results/id_vector_contract_audit.json
   eval/results/id_vector_contract_audit.csv
```

---

## 9. 风险

```text
1. Chroma 客户端可能锁库，先做副本或只读快照
2. 150k+ ID 全量比较需要分页
3. SQLite/PG 文本规范化差异
4. 旧集合可能来自不同 schema 版本
5. 不要把“文本一致”误判成“ID 一致”
```

---

## 10. 结论

```text
先审计，不先重建
先确认是“ID 陈旧”还是“覆盖不足”
再决定 UID 迁移和向量重建顺序
```
