# U0 计划表：前端批量上传 staging

> 阶段：U0  
> 状态：已完成  
> 依赖：H0–H4  
> 目标：前端上传 HTML/PDF/XML，安全落 staging，创建 ImportSession；不阻塞处理。

---

## 1. 决策

| 编号 | 决策 | 结论 |
|---|---|---|
| U0-1 | 上传格式 | html/htm/pdf/xml |
| U0-2 | 单文件上限 | 50 MB |
| U0-3 | 单批上限 | 50 files |
| U0-4 | 文件名 | basename + 白名单 |
| U0-5 | 落盘 | `data/imports/staging/<uuid>/` |
| U0-6 | 创建会话 | ImportSession queued |
| U0-7 | 处理 | 不自动 process；由客户端/worker 触发 |
| U0-8 | 权限 | 登录/现有 auth |

---

## 2. 任务

| 子任务 | 内容 | 产物 | 验收 |
|---|---|---|---|
| U0.1 | staging helper | `services/imports/upload.py` | 安全落盘 |
| U0.2 | upload route | `routes/imports.py` | multipart |
| U0.3 | frontend page | `frontend/imports.html` | 选择多文件 |
| U0.4 | tests | `tests/test_import_upload.py` | 大小/扩展/路径 |
| U0.5 | docs | 本文件 + JSON | 一致 |

---

## 3. API

```text
POST /api/imports/upload
  multipart/form-data
  library_id
  origin=upload
  files[]
```

返回：

```json
{
  "import_id": "imp_...",
  "status": "queued",
  "items": [...]
}
```

---

## 4. 不在 U0

```text
异步 worker（U1）
DSH MCP tool（U2）
自动 process
断点续传
对象存储
```

---

## 5. 验收结果

```text
POST /api/imports/upload -> 201
staging file created
ImportSession queued
4 tests passed
```

## 6. 验收

```text
1. 多文件上传成功
2. 非白名单扩展拒绝
3. 超大文件拒绝
4. 文件名路径穿越拒绝
5. 创建 ImportSession
6. 不自动 build
```
