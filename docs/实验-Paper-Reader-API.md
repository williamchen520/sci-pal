# 实验记录：Paper Reader API

> 日期：2026-11-13  
> 状态：reader 服务 + 4 个只读路由；真实数据直连验证通过  
> 目标：给 `scipal-paper` 提供 outline / paragraph / sentence 入口

---

## 1. 新增服务

```text
services/papers/reader.py
```

能力：

```text
paper_outline(paper_id)
paper_paragraphs(paper_id, section, offset, limit)
paper_first_paragraph(paper_id, section)
paragraph_sentences(paper_id, para_id)
```

## 2. 新增路由

```text
GET /api/papers/<paper_id>/outline
GET /api/papers/<paper_id>/paragraphs
GET /api/papers/<paper_id>/paragraphs/first
GET /api/papers/<paper_id>/paragraphs/<para_id>/sentences
```

## 3. 真实数据验证

论文：

```text
paper_nature_hcc_lipid_macrophage_b3cb651d2d57
```

reader 直连：

```text
sections 44
Results 第一段 para_0022
该段句子 7
```

示例：

```text
paper_..._para_0022_sent_001
```

## 4. 架构校验

```text
json_routes=256
app_routes=256
OK
```

## 5. 测试

```text
outline 归一化
section filter 参数
empty first paragraph
```

```text
tests.test_paper_reader 3 passed
```

## 6. 边界

```text
HTTP 接口尚未在重启后的 app 上验证
app 启动仍卡在模型/DB 初始化
outline 目前直接暴露 section_level1=body
```

所以：

```text
服务层已用真实 DB 验证
HTTP 层只完成注册与架构校验
```

## 7. HTTP 在线验证

app 起来后：

```text
login                 200
outline               200
paragraphs/first      200
paragraphs            200
sentences (para_0022) 200, 7 句
```

启动脚本修复：

```text
SCIPAL_PG_MAIN_READ_DSN
SCIPAL_PG_OWNER_DSN
SCIPAL_PG_INGEST_DSN
SCIPAL_PG_ADMIN_DSN
SCIPAL_PG_TENANT_WRITE_DSN
```

都从 `host.docker.internal` 替换为 `127.0.0.1`，解决 `198.18.1.238:5433` 连接失败。

## 8. Outline 归一化

reader 服务已把：

```text
body > Heading
```

归一化为：

```text
Heading
```

服务层实测：

```text
sections 43（归一化后）
```

但当前 app 进程仍是旧代码，HTTP 还返回 44 个含 `body` 的节；重启后才生效。

## 9. 下一步

```text
1. 等 app 起来后验证 4 个 HTTP 路由
2. 修 outline 的 body/heading 归一化
3. paragraph vector -> sentence FTS 检索链
4. scipal-paper 工具接入
```
