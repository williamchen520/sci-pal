# 零技术债 Phase 4a：protocol renderer 解耦

> 日期：2026-11-09  
> 状态：**pg_export 不再依赖 ProtocolService**

---

## 1. 改动

```text
services/protocols/render.py
  render_protocol_markdown(record, runs, protocol_id)
```

```text
services/protocols/pg_export.py
  删除 _Renderer(ProtocolService)
  直接调用 render_protocol_markdown
```

```text
services/protocols/service.py
  export_markdown 委托 render_protocol_markdown
```

---

## 2. 意义

`pg_export` 是生产导出路径；它不再为了渲染而构造一个 SQLite service。

这是 protocols family 迁移的第一步：renderer 先脱离存储。

---

## 3. 验证

```text
protocols / pg_import / pg_read
25 tests: 23 passed
2 个 pg_read 测试失败是既有 mock 目标过期（pg_read 不再直接暴露 pg_connection）
```

未新增失败。

---

## 4. 下一步

```text
1. 修 pg_read 测试 mock 目标
2. routes/protocols 固定 PG
3. ProtocolService SQLite 移入 tests/support
```
