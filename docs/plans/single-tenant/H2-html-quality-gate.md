# H2 计划表：HTML 质量门禁

> 阶段：H2  
> 状态：已完成  
> 依赖：H1  
> 目标：HTML 解析后先过质量门禁，低质量不入 canonical。

---

## 1. 门禁项

| 项 | 规则 | 级别 |
|---|---|---|
| title | 非空，不是文件名，>=10 字符 | critical |
| abstract | 非空，>=100 字符 | critical |
| sections | >=3 | critical |
| paragraphs | >=5 | critical |
| total chars | >=1000 | critical |
| doi | 缺失 | warning |
| duplicate titles | 重复 section title | warning |

---

## 2. 行为

```text
parsed HTML
  -> evaluate_html
  -> ok
       -> build
  -> not ok
       -> status=quarantined
       -> error=issues
       -> 不写 canonical
```

---

## 3. 产物

```text
services/imports/html_quality.py
tests/test_html_quality.py
```

---

## 4. 验收结果

```text
Nature: ok=true score=100
sections=15 paragraphs=175 chars=65873
6 tests passed
```

## 5. 验收

```text
1. 正常 Nature fixture 通过
2. 缺 title 拒绝
3. abstract 太短拒绝
4. sections 太少拒绝
5. paragraphs 太少拒绝
6. 低质量不进入 build
7. 返回 issues / metrics
```

---

## 6. 不在 H2

```text
PDF fallback（H3）
Cell/JS（H4）
自动抓取
人工审查 UI
```
