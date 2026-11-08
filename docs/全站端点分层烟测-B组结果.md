# 全站端点分层烟测：B 组结果

> 日期：2026-11-08  
> 环境：生产容器、无 research.db、PG-only

## 结果

```text
tested  14
5xx     0
```

## 通过

```text
review-projects brief
review-projects conflicts
review-projects events
review-projects evidence
review-projects evidence.csv
review-projects kappa
review-projects members
review-projects prisma
review-projects risk-of-bias
review-projects webhooks
reviews/<id>
protocols/<id>/runs
papers/<id>/supplementary
```

## 全部通过

```text
review-projects/<id>/export.json  -> 200
```

已改为 PG 导出，不再返回 410。

## 修复

```text
conflicts / events / members 接 pg_systematic
kappa 新增 kappa_pg
risk-of-bias 读 PG
prisma.svg 数据源 PG
export.json 明确 410
```

## 结论

```text
B 组通过
无 5xx
export.json 已实现
```

C 组仍待执行。
