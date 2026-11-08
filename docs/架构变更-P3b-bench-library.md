# 架构变更授权：P3b library_bench

> 日期：2026-11-08  
> 状态：**待人类批准修改**  
> 规则：`.dsh_rules` 规则 0A  
> 前置：P3b 25 篇 CC BY PMC OA 已下载到 `F:\scipal_data\bench_pmc_oa`

---

## 1. 问题

现在没有独立 benchmark library。

证据：

```text
F:\scipal_data\bench_pmc_oa   25 个 XML
catalog.libraries             只有 library_main
library_bench schema          不存在
```

如果直接拿主库论文当 bench：

```text
评测语料与生产语料重叠
work/document 身份无法独立验证
bench-only 无法隔离
```

---

## 2. 变更

改哪一层：

```text
schema
```

新增：

```text
catalog.libraries 增加 library_bench
library_bench.documents
library_bench.source_nodes
library_bench.sections
library_bench.paragraphs
library_bench.sentences
```

字段：

```text
documents
  document_id
  work_id
  library_id
  source_type
  source_path
  sha256
  parser
  parser_version
  imported_at

source_nodes
  node_id
  document_id
  parent_node_id
  node_type
  source_path
  source_order
  native_json

sections
  section_id
  document_id
  parent_id
  level
  seq
  title
  path
  depth
  source_node_id

paragraphs
  para_id
  document_id
  section_id
  seq
  text
  source_node_id

sentences
  sentence_id
  document_id
  para_id
  section_id
  seq
  text
  char_start
  char_end
  source_node_id
  search_vector
```

索引：

```text
documents(work_id)
documents(sha256)
source_nodes(document_id)
source_nodes(parent_node_id)
sections(document_id)
paragraphs(document_id)
paragraphs(section_id)
sentences(document_id)
sentences(para_id)
sentences(search_vector) GIN
```

---

## 3. 理由

```text
bench 必须是独立 library
否则 300 题与 bench smoke 都会被主库污染
```

P3b 只做：

```text
25 篇 XML
FTS
金标映射
```

不做：

```text
向量
HNSW
联邦
API
```

---

## 4. 影响

规模：

```text
documents      25
sections       约 150
paragraphs     约 700
sentences      约 3,000
```

不修改：

```text
public 表
library_main
现有 API
现有检索
```

风险：

```text
XML 解析失败 -> 该篇跳过并记录
node_id 冲突 -> 加载前清空 bench schema
```

---

## 5. 迁移

步骤：

```text
1. 建 library_bench schema
2. 注册 catalog.libraries
3. 解析 25 个 XML
4. 写 documents/source_nodes/sections/paragraphs/sentences
5. 生成 10 题金标
6. 校验
```

回滚：

```sql
DROP SCHEMA library_bench CASCADE;
DELETE FROM catalog.libraries WHERE library_id='library_bench';
DELETE FROM catalog.works WHERE work_id NOT IN (SELECT work_id FROM library_main.documents)
  AND work_id NOT IN (SELECT work_id FROM library_bench.documents);
```

P3b 不影响主库。

---

## 6. 验证

```text
documents = 25
sections > 0
paragraphs > 0
sentences > 0
sentences.search_vector 非空
10 题金标 100% 可映射
```

---

## 7. 需要批准

```text
1. 是否允许新增 library_bench schema 与 5 张表
2. 是否允许写入 25 篇解析结果
3. 是否允许在 catalog.libraries 注册 library_bench
```

批准后我会先建空表，再解析 25 篇；失败逐篇记录，不写主库。
