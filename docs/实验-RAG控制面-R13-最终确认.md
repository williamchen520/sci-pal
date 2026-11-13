# 实验记录：R13 最终确认 Gate 与封存哈希

> 日期：2026-11-13  
> 状态：**finalization gate + content seal hash 通过**  
> 目标：至少两名 reviewer 才能封存；封存是内容哈希，不是密码学签名

---

## 1. Gate

```text
reviewer_count >= 2
assigned reviewers 全部 completed
未 finalize
```

否则：

```text
400 at least two reviewers are required
400 assigned reviewers are not complete
400 already finalized
```

## 2. 最终确认

```text
POST /api/rag/multi/<id>/finalize
{
  "decision": "accepted | rejected | needs_more_evidence",
  "note": "..."
}
```

权限：

```text
human session
workspace finalize_review（owner/pi）
```

## 3. 封存

表：

```text
rag_multi_finalizations
  finalization_id
  multi_run_id
  decision
  note
  finalized_by
  content_hash
```

哈希覆盖：

```text
multi run
groups / evidence
adjudications
conflicts
agreement
```

哈希是完整性校验，不是签名。

## 4. 数据

`rag_multi_queries`：

```text
status open/finalized
finalized_by
finalized_at
```

## 5. UI

evidence 页面：

```text
reviewers >= 2 时显示“最终确认并封存”
完成后显示：
FINALIZED accepted · user · seal ...
```

## 6. 测试

```text
single reviewer cannot finalize
human required
finalizer permission required
```

```text
tests.test_rag_finalization 3 passed
validate_arch 247/247 OK
```

## 7. 边界

```text
不是密码学签名
没有外部时间戳
没有公钥基础设施
```

## 8. 下一步

```text
真实时间戳
签名
封存后只读
```
