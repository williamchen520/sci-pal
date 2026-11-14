# 实验记录：全库 Caption 审计

> 日期：2026-11-14  
> 状态：精确 caption 正则 0 命中；审计脚本可用  
> 目标：避免盲目全量重建 sentences

---

## 1. 脚本

```text
scripts/audit_sentence_captions.py
```

查询：

```sql
WHERE text ~* '(Fig[.]?|Figure|Table)[[:space:]]+[0-9]+[A-Za-z]?[[:space:]]*[|]'
```

`--rebuild` 按论文重建。

## 2. 误报

最初用：

```sql
text LIKE '%Fig.%|%'
 OR text LIKE '%Figure %|%'
 OR text LIKE '%Table %|%'
```

得到 41 篇 / 46 句，但其中大量是：

```text
|O/STERR|
|k→|=0
Figure 1b ... (not a caption)
```

不是图注。

## 3. 精确审计

```text
papers     0
sentences  0
```

说明当前 sentence 表没有残留 `Fig./Figure/Table N |` 图注句。

## 4. 已重建

在此之前，针对 41 篇候选执行了重建；其中真实污染已清掉，误报论文也重建了 sentences。

## 5. 规则

```text
caption 检测必须要求：
  Fig./Figure/Table + 数字 + 可选字母 + 可选空格 + |
不能只要求出现 | 
```

## 6. 下一步

```text
1. 把精确 caption 正则加入 CI/审计
2. 新论文入库后自动跑一次
3. Results section fallback 另做
```
