# DOI 重复组软去重

> 日期：2026-11-08

## 原则

```text
保留两版解析
标 papers.duplicate_of
检索路径排除 duplicate_of IS NOT NULL
不删除任何行
```

## 结果

```text
重复组  8
标记行  8
```

## 映射

| canonical（保留） | duplicate（排除） |
|---|---|
| `paper_PMC13583973_cfbd6b13` | `paper_PMC13583973_cfbd6b13_mineru` |
| `paper_PMC13612646_02e95398_mineru` | `paper_PMC13612646_775a3407_xml` |
| `paper_PMC13612782_cf1a1bc1_mineru` | `paper_PMC13612782_cf1a1bc1` |
| `paper_PMC13613318_e85358f1_mineru` | `paper_PMC13613318_e85358f1` |
| `paper_PMC13613722_dffed48e` | `paper_PMC13613722_dffed48e_mineru` |
| `paper_PMC13613924_d5e96a33` | `paper_PMC13613924_d5e96a33_mineru` |
| `paper_PMC13614128_c08078c4_mineru` | `paper_PMC13614128_c08078c4` |
| `paper_PMC13614617_b028aa74_mineru` | `paper_PMC13614617_b028aa74` |

选择规则：

```text
同一 DOI 中 paragraphs 数最多者
```

## 检索过滤

```text
pg_vector.py       JOIN papers pp ... duplicate_of IS NULL
pg_fts.py          paragraph + summary 查询均过滤
hybrid_search.py   filter_paper_ids 过滤
```

## 未处理

```text
12 组不同 PMCID 的同名文章
in this issue / 空标题
```

这些需要人工确认，未按标题删除。

## 回滚

```sql
UPDATE papers SET duplicate_of = NULL;
```

## 脚本

```text
scripts/soft_dedup_doi.py
```
