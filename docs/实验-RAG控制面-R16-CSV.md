# 实验记录：R16 CSV 导出

> 日期：2026-11-13  
> 状态：**审计/证据 CSV 导出通过**  
> 目标：给表格工具/人工审查提供稳定导出

---

## 1. 审计 CSV

```text
GET /api/rag/audit/adjudications.csv
GET /api/rag/audit/conflicts.csv
```

列：

```text
created_at
multi_run_id
query
rag_id
decision / note
decided_by / flagged_by
```

## 2. 证据 CSV

```text
GET /api/rag/multi/<id>/export/evidence.csv
```

列：

```text
rag_id
evidence_id
source_path
start_line
end_line
score
content_hash
metadata
duplicate_of
```

## 3. 安全

CSV 字段防注入：

```text
以 = + - @ 开头 -> 前置 '
```

UTF-8 BOM，便于 Excel。

## 4. 实测

```text
adjudications lines 2
conflicts lines 2
evidence lines 4
```

## 5. UI

audit 页面：

```text
下载 CSV
```

evidence 页面：

```text
导出证据 CSV
```

## 6. 测试

```text
tests.test_rag_audit 6 passed
validate_arch 251/251 OK
```

## 7. 边界

```text
CSV 不带签名
完整签名包仍用 RO-Crate ZIP
外部 TSA 未做
```
