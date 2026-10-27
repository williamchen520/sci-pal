# DSH 定时文献监测（示例）

> 依赖：`scipal-search` MCP 已连接到 DSH；SciPal `/api/watch` 可访问。

## 1. 先确认 profile

在 DSH 中调用：

```
watch_profiles()
```

返回示例：

```json
{"profiles": [{"id": 1, "name": "HCC 免疫治疗", "interval_days": 3, ...}]}
```

记住 `id`（下面用 `profile_id=1` 示例）。

## 2. 创建 DSH 定时任务

DSH 的 `schedule_create` 支持固定间隔（秒）。每 3 天一次：

```
schedule_create(
  title="文献监测运行",
  prompt="调用 watch_run(profile_id=1) 并展示返回的 Top 3 与简报链接；若 heartbeat=true 只提示“本月无新增”。",
  every_seconds=259200
)
```

也可以按 cron（每天 09:00 检查，是否运行由 profile 的 `next_run_at` 决定）：

```
schedule_create(
  title="文献监测检查",
  prompt="调用 watch_latest(profile_id=1)；若已超过 next_run_at，再调用 watch_run(profile_id=1)。",
  cron={"expression": "0 9 * * *", "time_zone": "Asia/Shanghai"}
)
```

## 3. 每次运行的返回

`watch_run` 返回：

```json
{
  "run_id": 12,
  "found": 30,
  "selected": 2,
  "imported_full": 2,
  "imported_abstract": 0,
  "skipped": 6,
  "heartbeat": false,
  "digest": "【文献监测】HCC 免疫治疗 · ..."
}
```

- `heartbeat=false`：正常简报；
- `heartbeat=true`：连续 30 天无新增，只推一条“本月无新增”；
- `digest` 可直接作为消息展示，Top 3 在 DSH 侧截取。

## 4. 手动查看与已读

```
watch_latest(profile_id=1)                 # 最近一期，不触发运行
GET /api/watch/profiles/1/latest           # 同上（HTTP）
POST /api/watch/items/<item_id>/read       # 手动标记已读
POST /api/watch/runs/<run_id>/read-all     # 全部已读
```

## 5. 注意

- 同一 profile 同一天重复调用会命中 `watch_seen`，不会重复入库；
- Europe PMC 503 时 JATS 全文会回退为摘要；
- 非 JATS 的 OA PDF 需要设置 `SCIPAL_UNPAYWALL_EMAIL` 才会尝试 Unpaywall 兜底；
- DSH 定时任务只在 DSH 运行时触发；SciPal 的 `/api/watch` 需常驻。
