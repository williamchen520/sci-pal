# Claim 试点在线入库 v1

> 日期：2026-10-31  
> 目标：修复在线 ingest 链路并导入 LEAP-012 / EMERALD-1 相关论文

---

## 1. 修复的链路

原问题：

```text
No module named 'import_xml_v2'
```

根因：

- `services/search/ingest.py` 仍引用已删除的旧解析器；
- `build_db.import_jats.parse_file` 返回的是嵌套结构；
- `authors` 是 list，直接绑定 SQLite 失败；
- 原写入层只写 papers/paragraphs，不写 sentences。

修复：

1. `_default_parse` 改用 `build_db.import_jats.parse_file`；
2. 把 `metadata` 拍平；
3. `authors` 拼接为字符串；
4. `_write_batch` 写入 sentences；
5. 写入 journal / year / doi。

---

## 2. 入库结果

### D 盘

```text
任务: ing_7a6f448cadd6
status: partial
imported: 2
failed: 1
```

成功：

- `PMC12771288` → `paper_PMC12771288_fca97ed9_xml`
- `PMC8940827` → `paper_PMC8940827_45a0a117_xml`

失败：

- `PMC13036683`：download failed after 3 attempts

### G 盘

```text
任务: ing_5f041a4968d1
status: completed
imported: 2
failed: 0
```

G 盘已在容器内重新入库，claims corpus 回填为 32。

---

## 3. 关键新证据

来自 `PMC12771288`（LEAP-012 / EMERALD-1 解读）：

> Current data for overall survival are immature but do not suggest a statistically significant survival benefit for combination therapy vs. TACE alone arms.

另一句：

> Conversely, PFS was not significantly improved in the durvalumab plus TACE arm compared to the TACE alone arm (HR 0.94, 95% CI 0.75–1.19).

---

## 4. 对 claim_hcc_triple_os 的影响

原 claim：

> TACE 联合抗 VEGF/TKI 与 PD-1/PD-L1 抑制剂的方案，较 TACE 单药或其他对照方案提高总生存。

新证据的含义：

- 部分三联方案 **PFS 有获益**；
- 但 **OS 仍未成熟**；
- 当前数据 **不支持统计学显著的 OS 获益**；
- 这与 claim 的“提高总生存”存在张力。

因此：

```text
claim_hcc_triple_os 不应继续保持无条件 accepted
建议改为 contested 或 revised
```

但这是人类裁决，不由脚本自动改状态。

---

## 5. Corpus 变化

```text
30 → 32
```

新增：

```text
paper_PMC12771288_fca97ed9_xml
paper_PMC8940827_45a0a117_xml
```

---

## 6. 下一步

1. 人工审阅上述 OS 反证；
2. 决定 `claim_hcc_triple_os` 改为 `contested` 还是 `revised`；
3. 再决定是否继续导入 IMbrave050 等其他在线论文。

注意：

> OS 数据 immature ≠ 已经证明无效。  
> 但它足以推翻“提高总生存”的无条件表述。

---

## 7. 人工裁决

2026-10-31，人工确认：

```text
claim_hcc_triple_os -> contested
```

同时保留：

```text
refutes: paper_PMC12771288_fca97ed9_xml_para_00000_sent_001
```

裁决理由：

> LEAP-012 / EMERALD-1 解读显示 OS 数据未成熟，且不支持联合治疗相对 TACE 单药的统计学显著 OS 获益；该证据直接挑战“提高总生存”的无条件表述。

状态变化：

```text
accepted -> contested
```

注意：

- 不是“证明无效”；
- 是“不能再无条件写提高 OS”；
- 后续写作必须同时写 PFS 获益与 OS 未成熟。
