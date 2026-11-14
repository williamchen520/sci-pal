# 单租户交付执行计划总表

> 日期：2026-11-14  
> 版本：v1  
> 状态：执行中  
> 当前阶段：N0  
> 项目状态：tenant-ready 单租户架构  
> Phase 2：frozen

---

## 1. 目标

```text
一个 tenant
  + main
  + tenant -> main 联邦
  + 不做 tenant -> tenant
```

产品优先完成：

```text
导入
解析
审查
建库
建索引
发布
```

---

## 2. 原则

```text
1. 单租户优先，不扩多租户控制面
2. 所有新入口使用 TenantContext
3. 来源分库，不强制对齐
4. 解释不写 canonical
5. 自动导入默认不自动发布
6. 每阶段先写 .md + .json 计划
7. 每阶段一个 PR
8. E3–E8 保持 frozen
```

---

## 3. 总表

| 阶段 | 目标 | 依赖 | 状态 | 计划表 | 主要验收 |
|---|---|---|---|---|---|
| N0 | 单租户导入管线 | S0 | planned | `N0-import-pipeline.md/.json` | XML/PDF/HTML/code 分流 |
| N1 | 审查与发布门禁 | N0 | planned | `N1-review-publish.md/.json` | 质量门禁 + 人工批准 |
| N2 | 文献监控自动入库 | N1 | planned | `N2-watch-auto-ingest.md/.json` | watch -> ImportSession |
| N3 | 薄插件层 | N0 | planned | `N3-parser-adapters.md/.json` | Parser/Review/Sink 接口 |

Phase 2 冻结：

```text
E3 tenant connector
E4 gateway scope
E5 peer deny tests
E6 support access
E7 ImportSession 全租户
E8 quota/delete/migration
```

---

## 4. 阶段说明

### N0 单租户导入管线

```text
ImportSession
  -> staging
  -> Detect
  -> Route
  -> Parse
  -> Build
  -> Index
```

支持：

```text
JATS XML
HTML
PDF
Python
R / Rmd
git repo / zip
```

产物：

```text
import_sessions
import_items
detector
router
orchestrator
import API
```

N0 不发布，只到 draft/indexed。

### N1 审查与发布

```text
自动质量门禁
人工批准
code 绑定
发布状态
```

N1 才允许：

```text
draft -> reviewed -> published
```

### N2 文献监控

```text
watch candidate
  -> 同一个 ImportSession
  -> auto_stage=true
  -> auto_publish=false
```

### N3 薄插件层

```text
ParserAdapter
ReviewGate
Sink
```

先做薄接口，不做第三方插件市场。

---

## 5. 依赖关系

```text
S0 TenantContext
  -> N0 ImportSession
      -> N1 Review/Publish
          -> N2 Watch
      -> N3 Adapters
```

E0/E1 保留：

```text
capability + scope
federation catalog + star constraint
```

E2 保留但不作为产品面：

```text
tenant stack 注册/管理员 DDL
```

---

## 6. 执行门禁

```text
S0  done
N0  需要先写/执行计划表
N1  依赖 N0 合并
N2  依赖 N1 合并
N3  依赖 N0 合并
E3–E8  frozen
```

---

## 7. 当前下一步

```text
N0 单租户导入管线
  -> 先写 N0 .md/.json
  -> ImportSession + detector + router
  -> 手工导入 API
  -> XML/PDF/HTML/code 分流
  -> draft/indexed
```
