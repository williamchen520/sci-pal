# 零技术债 Phase 4l：systematic route 纯 PG

> 日期：2026-11-09  
> 状态：**route 不再引用 SQLite systematic**

---

## 1. 改动

```text
routes/systematic_review.py
  AST 折叠 _pg_projects()
  删除不可达 else
  adjudicate / members / evidence 全走 pg_systematic
  新增 evidence_rules.extract_evidence
  /import 明确 410（无 PG 导入）
```

```text
services/review/evidence_rules.py
  纯 evidence 抽取规则
```

---

## 2. 验证

```text
systematic service tests   8 passed
validate_arch              210/210
```

---

## 3. 剩余

`services/review/systematic.py` 仍被报告模块使用：

```text
brief / report / docx_report / pdf_report / export
```

这些模块和测试是 service 的最后依赖。

---

## 4. 下一步

```text
报告模块 data 参数化
```

然后把 service 移入 tests。
