# 实验记录：Sentence Tree 入库

> 日期：2026-11-13  
> 状态：**HCC 论文 paragraph -> sentence 已入库；句级 FTS 可查**  
> 目标：补上章-节-句树的最后一级

---

## 1. 实现

```text
services/papers/sentences.py
scripts/build_sentence_tree.py
```

流程：

```text
paragraphs
  -> pySBD 切句
  -> char_start / char_end
  -> sentence_id = para_id + _sent_NNN
  -> sentences 表
```

## 2. 实际结果

论文：

```text
paper_nature_hcc_lipid_macrophage_b3cb651d2d57
```

结果：

```text
paragraphs 112
sentences  802
orphans    0
```

句子 ID：

```text
paper_..._para_0008_sent_005
paper_..._para_0038_sent_002
```

## 3. 句级 FTS

查询：

```text
lycopene chiglitazar
```

命中：

```text
para_0008_sent_005
  LAM lipid-associated condition, lycopene...
para_0038_sent_002
  lycopene (LYC) and PPAR agonist chiglitazar (CHI)...
para_0038_sent_004
  HFD + LYC / HFD + CHI...
```

说明：

```text
sentence_id 可定位
para_id 可回滚
section_id 随段落
```

## 4. 验证

```text
scientific abbreviation 切分
char offsets
stable sentence ids
```

```text
tests.test_sentence_tree 3 passed
```

## 5. 当前边界

```text
只跑了这一篇
HTML 还没有入库
R parser 仍未实现
sentence embeddings 未做
sentence API 还没有
```

## 6. 下一步

```text
1. sentence 查询 API
2. paragraph vector -> sentence FTS 检索链
3. 把 sentence 树接入 HTML/PDF ingest 主流程
4. R parser
```

现在这篇终于从：

```text
112 paragraphs
```

变成：

```text
112 paragraphs
802 sentences
```

“章-节-句”最后一级有数据了。
