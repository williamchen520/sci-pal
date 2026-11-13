# 实验记录：R14 封存签名与只读

> 日期：2026-11-13  
> 状态：**Ed25519 签名 + 本地时间 + 封存后只读通过**  
> 不是外部 TSA，不冒充可信时间戳

---

## 1. 签名

算法：

```text
Ed25519
```

签名对象：

```text
content_hash
```

存储：

```text
signature
public_key
signature_algorithm
key_id
signed_at
```

密钥：

```text
G:/runs/rag_signing_key.pem
SCIPAL_RAG_SIGNING_KEY
```

`key_id` 是公钥 sha256 前 16 位。

## 2. 时间

```text
timestamp_source = local_clock
```

明确不是 RFC 3161 / 外部 TSA。

## 3. 验证

```text
GET /api/rag/multi/<id>/verify-seal
```

返回：

```text
content_hash_match
signature_valid
key_id
signed_at
timestamp_source
```

## 4. 只读

finalized 后：

```text
add_adjudication -> 409
add_conflict     -> 409
assign           -> 409
```

封存后不能再改证据判断。

## 5. UI

evidence 页面显示：

```text
seal prefix
key_id
验证封存
```

## 6. 测试

```text
sign/verify roundtrip
tampered hash fails
key_id stable
```

```text
tests.test_rag_seal_signature 3 passed
tests.test_rag_finalization   3 passed
validate_arch 248/248 OK
```

## 7. 边界

```text
本地时钟，不是可信时间戳
私钥在本机文件
没有证书链/CA
```

## 8. 下一步

```text
外部时间戳（可选）
封存后导出带签名
```
