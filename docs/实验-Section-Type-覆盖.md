# 实验记录：Section Type 覆盖率

> 日期：2026-11-14  
> 状态：只读审计；12/13,203 篇已分类  
> 目的：先看覆盖，不盲目全量回填

---

## 1. 脚本

```text
scripts/audit_section_type_coverage.py
```

用法：

```powershell
python scripts/audit_section_type_coverage.py --json
```

## 2. 当前覆盖

```text
papers        12 / 13,203
paragraphs   623 / 410,505
pending      13,191 papers
```

## 3. 类型分布

```text
results       280
front_matter  115
methods       100
discussion     75
back_matter    39
references      7
caption         7
abstract        0
```

## 4. 解释

```text
12 篇里没有真正的 abstract 标签
abstract 正文被归到 front_matter
```

这是已知问题，不是统计错误。

## 5. 为什么不一次全回填

```text
section_type 仍是启发式
13k 篇里 PDF 结构差异大
先抽样回填 + 审计
再决定是否扩大
```

## 6. 下一步

```text
1. 回填 50 篇抽样
2. 人工抽查 5 篇
3. 扩大或修规则
```
