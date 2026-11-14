# U1 计划表：Import Queue + Worker

> 阶段：U1  
> 状态：已完成  
> 依赖：U0  
> 目标：上传后 queued，worker 异步 claim + process，HTTP 不阻塞。

---

## 1. 决策

| 编号 | 决策 | 结论 |
|---|---|---|
| U1-1 | 队列 | `import_sessions.status=queued` |
| U1-2 | claim | `FOR UPDATE SKIP LOCKED` |
| U1-3 | worker | 单进程顺序处理 |
| U1-4 | PDF | 仍由 Docling 串行 |
| U1-5 | 失败 | session/item failed，可重试 |
| U1-6 | API | enqueue 可选 |
| U1-7 | 不做 | Celery/Redis/多 worker |

---

## 2. 流程

```text
upload -> queued
worker claim -> running
process_import
  -> completed
  -> partial
  -> failed
```

---

## 3. 产物

```text
services/imports/queue.py
scripts/import_worker.py
POST /api/imports/<id>/enqueue
tests/test_import_queue.py
```

---

## 4. 验收

```text
1. queued session 被 claim
2. running 不重复 claim
3. worker once 处理 HTML
4. 失败 session 可 requeue
5. HTTP 不阻塞
```

---

## 5. 不在 U1

```text
Celery / Redis
多 worker 并发 PDF
优先级队列
分布式锁
```
