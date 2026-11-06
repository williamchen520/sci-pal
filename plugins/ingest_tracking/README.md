# Ingest Tracking Plugin

客户端批量导入的质量标记插件。后端批量导入不使用它。

## 启用

```text
SCIPAL_INGEST_TRACKING=1
```

未启用：

```text
不建表
不注册路由
无开销
```

## 表

```text
ingest_tracking_batches
ingest_tracking_items
ingest_tracking_findings
papers.quality_status
papers.quality_flags
papers.quality_checked_at
```

## API

```text
POST /api/ingest-tracking/batches
POST /api/ingest-tracking/batches/<id>/items
POST /api/ingest-tracking/batches/<id>/finish
GET  /api/ingest-tracking/batches/<id>
GET  /api/ingest-tracking/papers/<paper_id>
POST /api/ingest-tracking/papers/<paper_id>/review
```

## 状态

```text
clean
warning
needs_review
duplicate
rejected
reviewed
```

## 原则

```text
只标记，不裁决
不删除输入
不阻塞整批
后端导入不调用
```
