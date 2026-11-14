# 实验记录：Paper Plugin Smoke

> 日期：2026-11-14  
> 状态：两篇论文端到端 smoke 全绿  
> 目标：把手工验证固化成可重复脚本

---

## 1. 脚本

```text
scripts/smoke_paper_plugin.py
```

用法：

```powershell
$env:SCIPAL_SECRET_KEY = ...
$env:SCIPAL_PG_DSN = ...
$env:SCIPAL_SMOKE_BASE = "http://127.0.0.1:5001"
python scripts/smoke_paper_plugin.py --paper-id <id>
```

鉴权：

```text
Flask signed session
不需要明文密码
```

## 2. 检查项

```text
health
outline
first paragraph
analysis compact
evidence
code links
code libraries
modules
data flow
section results
section methods
replication plan
```

## 3. HCC LAM

```text
paper_nature_hcc_lipid_macrophage_b3cb651d2d57
12/12 200
failures []
```

## 4. HCC Genomic

```text
paper_hcc_genomic_4492073cf016
12/12 200
failures []
```

## 5. 断言

```text
analysis.compact
analysis.outline == []
analysis.outline_summary.section_count > 0
section results/methods 只在 outline 存在时检查
replication target = 第一个 module
```

## 6. 作用

```text
以后改 reader / analysis / section / flow
直接跑 smoke
不用手工点 12 个接口
```

## 7. 边界

```text
依赖 Flask 已启动
依赖 embedding 模型已预热
不是 CI 单元测试
冷启动第一次可能超时
```
