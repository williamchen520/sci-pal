# 评测归因：auto 题低覆盖

> 数据：`qa_cloud_100.json` 中 69 个 auto 题，取 coverage 最低的 20 个。  
> 方法：检查检索 top10 是否命中 gold paper，并人工看 question / answer_points。

## 1. 结论

auto 题的低覆盖，主要不是检索或数据结构问题，而是 **auto 题与 answer_points 生成质量问题**。

20 个低分题中：

| 类型 | 数量 |
|---|---|
| C/D. 检索命中，但 answer_points 是噪声/问题畸形 | 13 |
| A. 检索未命中 gold paper | 7 |
| B. 检索命中且 gold 有效，但回答没覆盖 | 0（未发现明确案例） |

## 2. 明细

| id | coverage | 检索命中 | 主要问题 |
|---|---|---|---|
| q046 | 0.0 | ✅ | 问题截断；points = forests / constitute / vital |
| q079 | 0.0 | ❌ | 检索未命中；points = condition / hyperglycemia / caused |
| q083 | 0.0 | ✅ | points = nanomaterials / known / possess |
| q085 | 0.0 | ✅ | points 是作者名：mramba / niinist / erlund |
| q093 | 0.0 | ✅ | points = certain / extent / relative |
| q096 | 0.0 | ✅ | points = noncoding / lncrnas / critical |
| q031 | 0.33 | ❌ | “What role does absence play”；问题畸形 |
| q033 | 0.33 | ✅ | points = critical / examines / reversible |
| q038 | 0.33 | ✅ | points = functionally / implicated / regulating |
| q047 | 0.33 | ✅ | points = plant / growth / development |
| q052 | 0.33 | ✅ | points = recent / years / china |
| q060 | 0.33 | ✅ | points = mesenchymal / stromal / cells |
| q069 | 0.33 | ❌ | “What role does herein play”；问题畸形 |
| q071 | 0.33 | ❌ | “What evidence is provided about forage”；过于宽泛 |
| q074 | 0.33 | ❌ | “What role does surgical play”；问题畸形 |
| q078 | 0.33 | ✅ | points = findings / raise / conceptual |
| q080 | 0.33 | ✅ | points = according / international / diabetes |
| q081 | 0.33 | ❌ | “What role does according play”；问题畸形 |
| q086 | 0.33 | ✅ | points = purpose / explored / associations |
| q089 | 0.33 | ❌ | 问题宽泛；points = recent / years / metal |

## 3. 典型问题

### 3.1 问题畸形
```
What role does herein play according to the paper?
What role does according play according to the paper?
What role does surgical play according to the paper?
```

### 3.2 answer_points 是关键词噪声
```
q085: mramba, niinist, erlund      # 作者名
q093: certain, extent, relative    # 泛词
q046: forests, constitute, vital   # 主题词
```

### 3.3 问题截断
```
q046: How does constitutive AtRD29A expression reveal divergent
      BpCBF3 regulatory mechanisms in birch within forest ecosystems
```
没有问号，语义不完整。

## 4. 影响

- auto 题 69 个，coverage 0.686；
- 人工题（factual/methods/comparison/refusal）基本 1.00；
- 30 题样本里 auto 比例较低，所以 30 题 0.9667 明显偏乐观；
- auto 题不适合作为模型/检索/结构选择的主指标。

## 5. 建议

1. **冻结现有 auto 题**：不再用它们做 A/B 或模型选择；
2. **重生成 auto 题**：
   - 从 evidence 段落生成；
   - question 必须是完整疑问句；
   - answer_points 必须是可验证的短句/数值，不是关键词；
   - 用第二个模型抽检；
3. **分开报告**：
   - human subset；
   - auto subset；
   - 不混合成一个总分；
4. **再处理 7 个检索 miss**：
   - q071/q089 等问题本身宽泛；
   - 需先清理问题，再判断检索。

## 6. 对数据结构的判断

- 13/20 检索命中，说明段落/章节结构可用；
- 低分主要来自评测数据，不是结构；
- 当前不应基于 auto 低覆盖改数据结构。

## 7. 下一步

1. 重生成 auto 题（独立 PR）；
2. 用新 auto 集重跑 100 题；
3. 做 100 题引用/拒答专项分析。
