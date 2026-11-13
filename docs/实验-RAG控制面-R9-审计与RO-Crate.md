# 实验记录：R9 审计列表与 RO-Crate 导出

> 日期：2026-11-13  
> 状态：**audit API + RO-Crate ZIP 通过**  
> 页面：`/audit.html`

---

## 1. 审计列表

```text
GET /api/rag/audit/adjudications
GET /api/rag/audit/conflicts
```

实际：

```text
adjudications 1
conflicts     1
```

都带：

```text
multi_run_id
query
rag_id
decision / note
decided_by / flagged_by
created_at
```

## 2. RO-Crate

```text
GET /api/rag/multi/<id>/export/ro-crate.zip
```

实际包：

```text
README.md
ro-crate-metadata.json
data/evidence.json
data/adjudications.json
data/conflicts.json
data/duplicates.json
```

测试包大小：

```text
3117 bytes
```

metadata：

```text
@context https://w3id.org/ro/crate/1.1/context
Dataset + File entries
```

## 3. UI

```text
/audit.html
```

显示：

```text
人工裁决表
冲突标记表
链接回 evidence 页面
```

evidence 页面增加：

```text
导出审计 JSON
导出 RO-Crate ZIP
```

## 4. 验证

```text
tests.test_rag_audit        3 passed
tests.test_rag_adjudication 5 passed
validate_arch 242/242 OK
```

## 5. 边界

```text
只有当前用户可见的本地审计
没有跨用户 reviewer 权限
没有签名/DOI
```

## 6. 下一步

```text
多用户 reviewer 权限
裁决审计导出 CSV
```
