# 实验记录：R18 封存公钥目录

> 日期：2026-11-13  
> 状态：**公钥目录可用；verify-seal 增加 key_known**  
> 目标：验证不只看包内自证

---

## 1. 公钥目录

```text
rag_signing_keys
  key_id
  public_key
  algorithm
  first_seen_at
  last_seen_at
```

key_id：

```text
sha256(public_key) 前 16 位
```

## 2. 注册

finalize 生成签名时：

```text
sign(content_hash)
  -> register(key_id, public_key)
```

同 key 再次出现只更新 `last_seen_at`。

## 3. 验证

```text
GET /api/rag/multi/<id>/verify-seal
```

新增：

```text
key_known
```

含义：

```text
签名 key 是否出现在本机公钥目录
```

即使 `signature_valid=true`，`key_known=false` 也应引起注意。

## 4. 目录 API

```text
GET /api/rag/seal-keys
```

只返回公钥，不返回私钥。

## 5. 实测

```text
keys 1
known True
key_id af1bf248331ae6fa
```

## 6. 测试

```text
tests.test_rag_signing_keys 1 passed
tests.test_rag_seal_signature 3 passed
validate_arch 252/252 OK
```

## 7. 边界

```text
公钥目录在本机
不是外部 CA
没有 key 吊销
没有外部时间戳
```
