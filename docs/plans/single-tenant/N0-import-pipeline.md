# N0 计划表：单租户导入管线

> 阶段：N0  
> 状态：进行中（N0.1–N0.4，N0.8）  
> 依赖：S0 TenantContext  
> 目标：单租户手工导入 XML/HTML/PDF/code，自动识别、分流、建库、建索引到 draft/indexed。

---

## 1. 目标

```text
ImportSession
  -> staging
  -> Detect
  -> Route
  -> Parse
  -> Build
  -> Index
  -> draft/indexed
```

N0 不做审查发布，不做 watch，不做插件市场。

---

## 2. 决策

| 编号 | 决策 | 结论 |
|---|---|---|
| N0-1 | 租户范围 | 单租户 + main |
| N0-2 | 触发方式 | 手工 API / DSH / 前端 |
| N0-3 | 先落 staging | 不直接写 canonical |
| N0-4 | 格式检测 | magic + MIME + 内容 + parser probe |
| N0-5 | 分流 | paper lane / code lane |
| N0-6 | 状态 | draft/indexed，不自动 published |
| N0-7 | 幂等 | content_hash + library + parser_version |
| N0-8 | 低置信度 | quarantine，不猜 |
| N0-9 | 执行 | 服务调用，不 subprocess 调脚本 |

---

## 3. 任务表

| 子任务 | 内容 | 产物 | 验收 |
|---|---|---|---|
| N0.1 | import 表 | `deploy/sql/046_import_sessions.sql` | sessions/items |
| N0.2 | ImportSession 服务 | `services/imports/session.py` | 创建/查询/重试 |
| N0.3 | Detector | `services/imports/detector.py` | 格式识别 |
| N0.4 | Router | `services/imports/router.py` | paper/code 分流 |
| N0.5 | Orchestrator | `services/imports/orchestrator.py` | 状态流转 |
| N0.6 | Paper adapters | `services/imports/paper_lane.py` | XML/HTML/PDF |
| N0.7 | Code adapter | `services/imports/code_lane.py` | repo/zip/R/Python |
| N0.8 | Import API | `routes/imports.py` | POST/GET/retry |
| N0.9 | Tests | `tests/test_import_pipeline.py` | 分流/幂等/失败 |
| N0.10 | 文档 | 本文件 + JSON | 一致 |

---

## 4. 数据模型

```text
import_sessions
  import_id
  tenant_id
  library_id
  origin          manual | dsh | api
  status
  total_items
  processed_items
  failed_items
  created_by
  created_at

import_items
  import_id
  item_id
  kind            paper | code | supplementary
  source_kind     jats | html | pdf | repo | zip | unknown
  source_uri
  content_hash
  status
  error
  created_at
```

---

## 5. Detector

| 类型 | 规则 |
|---|---|
| PDF | `%PDF-` magic / application/pdf |
| JATS XML | root `article` + `front/body/back` |
| HTML | doctype/html + citation meta |
| Python | `.py` + AST parse |
| R | `.R` + `<-` / `library()` |
| Rmd | `.Rmd/.qmd` + YAML header |
| repo | git URL / `.git` |
| zip | PK magic |

低置信度：

```text
source_kind=unknown
status=quarantined
```

---

## 6. Router

```text
jats/html/pdf -> paper lane -> xml/html/pdf library
repo/zip/python/r/rmd -> code lane -> code library
unknown -> quarantine
```

同一批可以混合。

---

## 7. 状态机

```text
received
  -> detected
  -> routed
  -> parsed
  -> built
  -> indexed
  -> draft

failed
quarantined
```

N0 不进入：

```text
reviewed
published
```

---

## 8. API

```text
POST /api/imports
GET  /api/imports/<import_id>
GET  /api/imports/<import_id>/items
POST /api/imports/<import_id>/retry
```

请求示例：

```json
{
  "tenant_id": "default",
  "library_id": "lib_default",
  "origin": "manual",
  "items": [
    {"uri": "..."},
    {"uri": "..."}
  ]
}
```

---

## 9. 建库与索引

Paper lane：

```text
JATS  -> jats parser -> xml native
HTML  -> html parser -> html native
PDF   -> docling    -> pdf native
```

Code lane：

```text
repo/zip -> code_rag.ingest -> file/unit/edge -> snapshot
```

索引：

```text
embedding
FTS
code index
```

使用 `TenantContext` 的 storage/index prefix。

---

## 10. 幂等与失败

```text
content_hash + library_id + parser_version
```

同一 item 不重复建库。

失败：

```text
单 item 失败不阻塞整批
可 retry
错误写 import_items.error
```

---

## 11. 不在 N0 范围

```text
审查与发布（N1）
watch 自动发现（N2）
插件注册表（N3）
多租户自助 provisioning
E3–E8
```

---

## 12. 当前进度

```text
N0.1  tables          done
N0.2  session         done
N0.3  detector        done
N0.4  router          done
N0.8  API             done
N0.9  tests           13 passed（部分）
N0.5  orchestrator    pending
N0.6  paper adapters  pending
N0.7  code adapter    pending
```

## 13. 验收

```text
1. XML/HTML/PDF 进入 paper lane
2. repo/zip/Python/R 进入 code lane
3. unknown 进入 quarantine
4. 混合批次正确分流
5. 重复导入不重复建库
6. 单 item 失败不阻塞整批
7. 导入后可查询状态
8. 不自动 published
9. 单测通过
```

---

## 14. 风险

```text
格式误判
大文件/大仓库
PDF 解析失败
代码仓库不可达
license 不明
重复导入
存储/模型成本
```

对策：

```text
低置信度隔离
大小限制
失败可重试
license 记录
hash 幂等
单租户配额暂不启用
```
