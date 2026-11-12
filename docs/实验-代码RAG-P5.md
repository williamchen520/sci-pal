# 实验记录：code-rag P5 UI「我的代码库」

> 日期：2026-11-12  
> 状态：**页面/代理/API 已实现；未在运行中的 SciPal 上做浏览器验收**  
> 入口：`/libraries.html`

---

## 1. 结构

```text
浏览器
  /libraries.html
  /src/libraries.js
        │
        ▼
SciPal 主应用
  /api/libraries                   平台注册/ACL
  /api/code/libraries/<id>/*       同源代理
        │
        ▼
code-rag HTTP 服务 :5010
  /libraries/<id>/status
  /libraries/<id>/search
  /libraries/<id>/trace
        │
        ▼
scipal_code.code_rag
```

主 Flask 不 import embedding 模型；code-rag 独立进程。

## 2. 页面功能

```text
列出代码库
新建代码库（name / repo_url / ref）
查看状态（snapshots / units / health）
搜索
展示 symbol/path/line/snippet
点击 Trace 查看 1–2 跳
```

## 3. API

平台：

```text
GET  /api/libraries?kind=code
POST /api/libraries
```

代理：

```text
GET  /api/code/libraries/<id>/status
POST /api/code/libraries/<id>/search
GET  /api/code/libraries/<id>/trace
```

代理会校验：

```text
library 属于当前 workspace
kind=code
用户有 read_workspace
```

## 4. 启动

```bash
SCIPAL_CODE_READ_DSN=... python -m code_rag.api --port 5010
```

主应用：

```text
SCIPAL_CODE_API_URL=http://127.0.0.1:5010
```

## 5. 验证

```text
tests.test_code_libraries_routes 4 passed
tests.test_code_rag_api         4 passed
validate_arch 211/211 OK
```

code-rag API smoke：

```text
GET /health -> ok=true
GET /libraries/lib_2c.../status -> units=1819
POST search -> normalize_total
```

## 6. 已知限制

```text
UI 不触发 clone/index
新建库后需 CLI/worker 索引
code API 需要单独启动
首次 search 冷启动约 20s
没有浏览器自动化验收
```

## 7. 下一步

```text
P6：30 问题评测（DSH 基线 vs code_search/code_trace）
```
