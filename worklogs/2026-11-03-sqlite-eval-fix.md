# Worklog: eval 去 SQLite 长连接

> 日期：2026-11-03  
> PR：Pending Review

## 1. 需求

长 eval 后容器 SQLite 句柄失效，必须重启 app；需要验证并消除触发条件。

## 2. ARCHITECTURE.json 变化

```text
无
```

## 3. 修改文件

```text
eval/retrieval_eval.py
docs/运维-SQLite长跑故障.md
docs/Research_Logs_Index.md
worklogs/2026-11-03-sqlite-eval-fix.md
```

## 4. 业务逻辑变化

```text
新增 --pg-dsn：
  sentence -> section/paragraph 映射走 PostgreSQL
无 PG 时：
  每次查询打开/关闭 SQLite，不持有长连接
```

生产 Flask 代码未改。

## 5. validate_arch 结果

```text
json_routes=202
app_routes=202
OK
```

## 6. 测试命令与通过率

```text
python -m unittest discover -s tests -p "test_*.py"
814 tests OK

完整 96 题（PG 映射）
recall 0.6615 / refusal 1.00
跑完后容器 papers=3313 / health=200 / 未重启
```

## 7. 风险 / 外部 API

```text
无新增外部 API（复用现有 PG）
eval 脚本新增可选参数
生产 app 无变化
```

## 8. 未完成项

```text
PR Pending Review
如果后续长跑仍复现，再启动 B（named volume）
```
