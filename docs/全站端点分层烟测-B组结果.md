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

## 明确未实现

```text
review-projects/<id>/export.json  -> 410 FEATURE_OFFLINE_PG_ONLY
```

不是 500，是明确的能力缺口。

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
export.json 待后续实现
```

C 组仍待执行。
