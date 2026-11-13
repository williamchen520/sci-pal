# 实验记录：R15 带签名的研究包导出

> 日期：2026-11-13  
> 状态：**RO-Crate 包含 finalization + signature**  
> 目标：导出包能独立验证封存

---

## 1. 导出内容

`ro-crate.zip`：

```text
README.md
ro-crate-metadata.json
data/evidence.json
data/adjudications.json
data/conflicts.json
data/duplicates.json
data/finalization.json
```

`finalization.json` 包含：

```text
content_hash
signature
public_key
signature_algorithm
key_id
signed_at
timestamp_source
```

## 2. JSON 导出

`/export.json` 的 `get_multi` 现在也包含：

```text
finalization
```

不再只是 groups/adjudications/conflicts。

## 3. 验证

包内 finalization 可用：

```text
GET /api/rag/multi/<id>/verify-seal
```

验证：

```text
content_hash_match
signature_valid
key_id
signed_at
local_clock
```

## 4. 测试

```text
zip contains data/finalization.json
signed finalization signature preserved
```

```text
tests.test_rag_audit 4 passed
```

## 5. 边界

```text
签名时间仍是本地时钟
没有外部 TSA
包内不包含私钥
```

## 6. 下一步

```text
外部时间戳（可选）
导出 CSV
```
