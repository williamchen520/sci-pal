# 实验记录：Embedding 输入审计与修复

> 日期：2026-11-13  
> 状态：ID 污染 0；HCC 论文脏 embedding 已清理  
> 目的：建 PG 库前确认章节句编号没有进入向量

---

## 1. 审计项

```text
paragraphs.text 是否含 para_/sent_/section_id/paper_ ID
sentences.text  是否含同类 ID
embedding 输入是否包含低质量段落
section_path 是否被错误拼进向量
```

## 2. 全库 ID 审计

```sql
SELECT count(*) FROM paragraphs
WHERE text ~ '(para_|sent_|section_id|paper_)[A-Za-z0-9]';

SELECT count(*) FROM sentences
WHERE text ~ '(para_|sent_|section_id|paper_)[A-Za-z0-9]';
```

结果：

```text
paragraphs_id_like 0
sentences_id_like  0
```

说明：

```text
没有发现 paper/para/sent/section ID 被写进正文
```

## 3. 发现的问题

HCC 这篇手工补 embedding 时绕过了 `index_skip_reason`：

```text
112 paragraphs
全部 112 条都写了向量
```

其中 6 条属于：

```text
no_letters
url_only
reference_section
boilerplate
```

这不是“编号进向量”，但属于 **脏输入进向量**。

## 4. 修复

脚本：

```text
scripts/audit_embedding_inputs.py
```

执行：

```text
--paper-id paper_nature_hcc_lipid_macrophage_b3cb651d2d57 --fix
```

结果：

```text
removed_embeddings 6
removed_sentences 181
```

修复后：

```text
embeddings 106
sentences   621
orphans       0
```

## 5. 句级 FTS 复验

```text
lycopene chiglitazar
-> para_0008_sent_005
-> para_0038_sent_002
```

仍可命中。

## 6. 根因

```text
build_embeddings_pg.py 本身有 index_skip_reason
手工一次性 embedding 脚本没有复用该过滤
```

所以问题不在向量模型，而在**旁路写入**。

## 7. 规则

以后所有 embedding 写入必须：

```text
paragraphs.text
  -> index_skip_reason
  -> 通过才 encode
```

禁止：

```text
手工 SELECT 全部段落直接 encode
把 section_path / para_id 拼进 text
把 sentence_id 拼进 text
```

## 8. 审计脚本

```text
scripts/audit_embedding_inputs.py
  --paper-id
  --fix
```

默认只报告，不删除。

## 9. 结论

```text
ID 污染：0
脏输入：HCC 6 条，已清理
当前：106 向量 / 621 句
```

建 PG 库前应把该审计作为 preflight，而不是事后补救。
