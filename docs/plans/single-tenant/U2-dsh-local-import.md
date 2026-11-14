# U2 计划表：DSH 本地路径导入

> 阶段：U2  
> 状态：已完成  
> 依赖：U1  
> 目标：DSH/MCP 传本地路径列表，服务端安全 staging 并创建 ImportSession。

---

## 1. 决策

| 编号 | 决策 | 结论 |
|---|---|---|
| U2-1 | 输入 | JSON `paths[]` |
| U2-2 | 扩展名 | html/htm/pdf/xml |
| U2-3 | 文件 | 必须存在，单文件 50MB |
| U2-4 | 落盘 | 复制到 staging |
| U2-5 | 会话 | queued，不自动 process |
| U2-6 | MCP | `paper_import_local` |
| U2-7 | 安全 | 仅本地/内部 token |

---

## 2. API

```text
POST /api/imports/local
{
  "library_id": "lib_default",
  "paths": ["D:/papers/a.html", "D:/papers/a.pdf"]
}
```

---

## 3. 验收结果

```text
POST /api/imports/local -> 201
imp_5e0cd4a61a3c47ef queued
3 tests passed
```

## 4. 验收

```text
1. 本地 HTML 路径 staging
2. 本地 PDF 路径 staging
3. 不存在路径拒绝
4. 非白名单扩展拒绝
5. ImportSession queued
6. MCP tool 返回 import_id
```

---

## 5. 不在 U2

```text
远程路径
DSH 上传二进制
自动 process
```
