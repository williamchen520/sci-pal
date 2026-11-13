# 实验记录：R17 可独立验证的封存包

> 日期：2026-11-13  
> 状态：**canonical + Ed25519 + 独立验证 CLI 通过**  
> 目标：第三方不启动 SciPal 也能验证包

---

## 1. 包内新增

```text
data/canonical.json
```

它是生成 `content_hash` 的 canonical payload：

```text
multi_run
groups/evidence
adjudications
conflicts
agreement
```

哈希：

```text
sha256(data/canonical.json) == finalization.content_hash
```

## 2. 独立验证

```bash
python scripts/verify_rag_seal.py package.ro-crate.zip
```

输出：

```text
content_hash_match
signature_valid
key_id
signed_at
timestamp_source
valid
```

不启动 API，不访问数据库。

## 3. 验证逻辑

```text
1. sha256(canonical.json)
2. 与 finalization.content_hash 比较
3. Ed25519 verify(content_hash, signature, public_key)
```

篡改 canonical 任一字节都会失败。

## 4. 测试

```text
valid package  -> 0
tampered package -> 1
```

```text
tests.test_verify_rag_seal 2 passed
tests.test_rag_audit       6 passed
```

## 5. 边界

```text
时间仍是本地时钟
没有外部 TSA
公钥随包提供，信任根仍是用户
```

## 6. 下一步

```text
外部时间戳（可选）
公钥发布/指纹目录
```
