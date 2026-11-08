# P4g 开发库种子结果

> 日期：2026-11-08  
> 状态：**scipal_dev 已可本地跑通**

---

## 1. 种子

```text
users            1（user_dev）
workspaces       1（ws_default）
memberships      1（owner）
papers           2
paragraphs       8
sentences        8
embeddings       8（零向量）
library docs     2
```

论文：

```text
paper_dev_hcc_001
paper_dev_crc_002
```

---

## 2. 脚本

```text
scripts/seed_scipal_dev.py
  --apply
```

幂等：

```text
删除固定 ID 的 dev 数据
重新插入
```

不触碰生产。

---

## 3. 向量说明

```text
embedding = 768 维零向量
```

用途：

```text
跑通 schema / API / join
不是检索质量数据
```

---

## 4. 验证

```text
papers       2
paragraphs   8
sentences    8
embeddings   8
docs         2
```

---

## 5. 当前开发环境

```text
database   scipal_dev
owner      scipal_dev_owner
DSN        SCIPAL_PG_DEV_OWNER_DSN
```

生产仍是：

```text
tenant_writer / main_reader / ingest / admin
break-glass scipal
```

---

## 6. 下一步

```text
1. 用 scipal_dev 跑测试子集
2. 评估 public 对 admin 只读
3. 决定迁移脚本临时凭据
```
