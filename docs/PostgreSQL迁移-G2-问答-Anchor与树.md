# G2 问答记录：Anchor、Sentence Window 与章节句树

> 日期：2026-11-04  
> 背景：q002/q016/q017/q018 的 gold paragraph 已在 evidence，但 highlight 未命中

---

## Q1：我们现在做的是 sentence window retrieval 吗？

是，但只是简化版。

当前：

```text
一个 evidence 的所有 paragraph
  -> 全局选 best sentence
  -> 取同 paragraph 的相邻句
```

标准 sentence window：

```text
先定位 anchor sentence
再取同一父节点的 window
```

我们缺的是：

```text
anchor 的正确层级
```

---

## Q2：best anchor 是怎么找的？

尝试过三种：

| 方法 | 原理 | 结果 |
|---|---|---|
| lexical | query/sentence 词面重合 | 偏向总结句 |
| cross-encoder | query+sentence 语义打分 | 只修 q002 |
| embedding | query/sentence 向量相似 | 四题全失败 |

共同问题：

```text
都在整个 evidence 的句子里做全局选择
没有利用章节段落结构
```

---

## Q3：为什么 q017/q018 还是失败？

q017/q018 的 evidence 有 6 个 paragraph。

当前：

```text
全局 best anchor 可能落在 paragraph_00001/00002
gold 在 paragraph_00000
window 跟不过去
```

所以：

```text
window 方向正确
但“全局 best per evidence”选错了 paragraph
```

---

## Q4：章节句树状结构可以用吗？

可以，而且应该用。

当前数据：

```text
paper
  -> section
    -> paragraph
      -> sentence
```

对应表：

```text
papers
sections
paragraphs
sentences
```

字段：

```text
sentences.sentence_id
sentences.para_id
sentences.paper_id
sentences.section_id
sentences.sequence
```

---

## Q5：sentence_id 是四级编号吗？

当前 ID 编码了：

```text
paper
paragraph
sentence
```

例如：

```text
paper_PMC13631563_4e18eb11_xml_para_00000_sent_002
```

但 **section 不在 ID 里**。

所以：

```text
sentence_id -> 精确定位
para_id     -> 父 paragraph
section_id  -> 查 sections 表
paper_id    -> 直接有
```

---

## Q6：能不能通过 sentence_id 判断有没有上下文？

可以，但不应该解析 ID。

正确方式：

```sql
-- 同段前后句
SELECT sentence_id, sequence, text
FROM sentences
WHERE para_id = ?
ORDER BY sequence;

-- section
SELECT section_id, title, parent_id
FROM sections
WHERE section_id = ?;
```

判断：

```text
sequence > 1
sequence < max(sequence)
section 是否有 parent
paragraph 是否有 siblings
```

不要：

```text
sentence_id.split("_")
```

原因：

```text
ID 格式不止一种
重新 ingest 后可能变化
section 不在 ID 里
```

---

## Q7：代码规则是不是在强制模型怎么处理数据？

不是。

代码约束：

```text
evidence 形状
anchor/window
顺序
citation id
quote 可验证
```

模型自由：

```text
理解
比较
推理
组织答案
```

正确说法：

```text
输入契约 + 输出校验
不是强制模型内部推理
```

---

## Q8：正确的 anchor 选法是什么？

不是：

```text
全局 best sentence
```

而是：

```text
paragraph-first
  -> 每个 paragraph 内选 best sentence
  -> 该 sentence ± window
  -> 按 paragraph rerank score 选 top paragraphs
  -> section path 作为 metadata
```

---

## Q9：为什么 paragraph-first 能修 q017/q018？

```text
gold 在 paragraph_00000
只要该 paragraph 参与 anchor 选择
window 就能覆盖 gold
```

当前全局选择会跳过这个 paragraph。

---

## Q10：最终 evidence 应该长什么样？

```json
{
  "paper_id": "...",
  "section_path": ["Introduction"],
  "para_id": "...",
  "anchor": {
    "sentence_id": "...",
    "text": "..."
  },
  "window": [
    {"sentence_id": "...", "text": "..."}
  ],
  "paragraph_score": 0.82,
  "evidence_id": "P1"
}
```

---

## Q11：G2 下一步是什么？

```text
G2.6b paragraph-first anchor window
```

验收：

```text
q002/q016/q017/q018 sentence 命中
20 题 L3 >= .85
```

当前：

```text
anchor 默认关闭
生产保持 Chroma
G4 阻塞
```


## Q12：paragraph-first 原型结果（2026-11-04）

```text
q002 命中  nhigh 32
q016 命中  nhigh 60
q017 未命中 nhigh 33
q018 命中  nhigh 38
```

结论：

```text
paragraph-first 修好 q018
q017 仍失败
高亮数完全不可接受
```

原因：

```text
每个 paragraph 都产生 window
limit_paragraphs=2 仍然放大到 30–60 条
```

处理：

```text
anchor 全系列默认关闭
生产保持 Chroma
```

下一步：

```text
不是继续加 window
而是先做 paragraph 级 evidence 选择
再只对 1 个 paragraph 做 anchor window
```
