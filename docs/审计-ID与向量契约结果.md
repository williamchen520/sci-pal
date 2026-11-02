# ID / 向量契约审计结果（2026-11-03）

> 脚本：`scripts/audit_id_vector_contract.py`  
> 模式：只读  
> 结果：修复前 **FAIL**；2026-11-03 修复后 **PASS**

## 1. 结论

```text
vector_resolution_rate = 0.9328
硬失败：vector resolution < 99.9%
```

主要原因：

```text
paragraphs 向量有 25,346 个 ID 解析不到当前 DB
```

## 2. 集合结果

| 集合 | 向量 | 解析 | 孤儿 | 解析率 | DB 覆盖 |
|---|---:|---:|---:|---:|---:|
| paragraphs | 147,910 | 122,564 | 25,346 | 82.86% | 73.22% |
| paragraphs_contextual | 164,654 | 164,654 | 0 | 100% | 98.37% |
| papers | 2,076 | 2,076 | 0 | 100% | 62.66% |
| section_summaries | 61,932 | 61,932 | 0 | 100% | 89.59% |
| figures | 219 | 219 | 0 | 100% | 1.63% |
| tables | 114 | 114 | 0 | 100% | 2.32% |

## 3. ID 一致性

| 表 | SQLite | PG | same | consistency |
|---|---:|---:|---:|---:|
| papers | 3,313 | 3,313 | 3,313 | 100% |
| sections | 69,128 | 69,128 | 69,128 | 100% |
| paragraphs | 167,388 | 167,388 | 167,388 | 100% |
| sentences | 862,677 | 862,677 | 862,677 | 100% |
| figures | 13,471 | 13,471 | 13,471 | 100% |
| tables | 4,922 | 4,922 | 4,922 | 100% |

**重要更正**：当前库句子 ID 已一致。

```text
gold sentence total 65
same_id            65
text_match_only     0
missing             0
```

之前“17/17 文本一致、0/17 ID 一致”是旧库状态；当前审计不成立。

## 4. Metadata / 层级

```text
paragraphs metadata complete            100%
paragraphs_contextual metadata complete 100%
papers metadata complete                100%
figures metadata complete               100%
tables metadata complete                100%

orphan_sections    0
orphan_paragraphs  0
orphan_sentences   0
```

## 5. 编号格式分布

```text
sections:
  paper_*_sec_*   58,372
  sec_paper_*     10,756

paragraphs:
  paper_*_para_* 158,681
  para_paper_*     8,613
  other               94

sentences:
  *_sent_*       862,677
```

说明：

```text
编号格式仍有两套
但 SQLite/PG 内部一致
```

## 6. 解释

### 6.1 不是“ID 全乱”

```text
papers/sections/paragraphs/sentences
在 SQLite 与 PG 之间 100% 一致
```

所以当前不是跨库编号分叉。

### 6.2 是“向量陈旧”

```text
paragraphs 集合 25,346 个 ID 不在当前 DB
```

这符合旧向量未清理/重建的情况。

### 6.3 覆盖不足

```text
papers     62.66%
figures     1.63%
tables      2.32%
sections   89.59%
paragraphs 73.22%
```

## 7. 决策

```text
不先做 UID 迁移
先重建 paragraphs 向量
再补 papers / sections / figures / tables
```

原因：

```text
当前 ID 一致性 100%
问题主要是旧向量未清理 + 覆盖不足
```

## 8. 下一步

```text
1. 清理 paragraphs 集合中的孤儿 ID
2. 用当前 para_id 重建 paragraphs
3. 补 contextual 缺失
4. 补 papers / section_summaries
5. figures/tables 单独回填
6. 重跑审计直到 verdict=pass 或只剩 coverage warn
```

## 9. 产物

```text
eval/results/id_vector_contract_audit.json
```


---

## 10. 修复后复核（2026-11-03）

执行：

```text
scripts/repair_paragraph_vectors.py
```

结果：

```text
orphans deleted       26,226
missing backfilled    44,786
paragraph vectors     166,470
orphan after          0
missing after         0
coverage after        99.45%
```

审计复核：

```text
verdict              WARN
vector resolution    100%
failures             []
```

剩余 warning：

```text
papers coverage           62.66%
figures coverage           1.63%
tables coverage            2.32%
section_summaries coverage 89.59%
```

paragraphs 剩余 918 条未向量化，因文本长度 < 10，被建索引脚本过滤。

结论：

```text
paragraph 向量契约已恢复
下一步是补 papers / sections / figures / tables 覆盖
```


---

## 11. papers / section_summaries 补全（2026-11-03）

执行：

```text
scripts/backfill_paper_summary_vectors.py
```

结果：

```text
papers vectors             3,313 / 3,313   100%
section_summaries vectors 69,128 / 69,128 100%
PG summaries              69,128
```

处理：

```text
papers 缺失向量      1,237
sections 缺失 summary 7,196
```

审计复核：

```text
verdict   WARN
warnings  figures coverage < 90%
          tables  coverage < 90%
```

剩余：

```text
figures 219 / 13,471   1.63%
tables  114 / 4,922    2.32%
```

结论：

```text
papers / section_summaries 契约已补齐
只剩 figures / tables 覆盖问题
```


---

## 12. figures / tables 补全（2026-11-03）

执行：

```text
scripts/backfill_figure_table_vectors.py
```

结果：

```text
figures vectors  13,098 / 13,471   97.23%
tables  vectors   4,919 / 4,922    99.94%
```

处理：

```text
figures missing  12,879
tables  missing   4,805
```

审计：

```text
verdict   PASS
failures  []
warnings  []
resolution 100%
```

剩余未向量化：

```text
figures 373 条无有效 caption
tables    3 条无 caption/markdown
```
