# 肿瘤免疫领域包 v0

## 范围

- 肝细胞癌（HCC）
- 非小细胞肺癌（NSCLC）
- 黑色素瘤
- 免疫检查点抑制剂（PD-1 / PD-L1 / CTLA-4）
- 疗效终点：ORR、PFS、OS
- 安全性：irAE
- 生物标志物：TMB、MSI-H/dMMR

## 文件

```text
pack.yaml              manifest
taxonomy.yaml          术语、限定条件、证据类型
section_types.yaml     章节类型与证据权重
evidence_schema.yaml   claim/evidence 字段
sources.yaml           文献源
prompts/               QA / review / brief
```

## 原则

1. ORR、PFS、OS 不混用；
2. 一线/二线、单药/联合必须记录；
3. 单臂研究不能写成对照结论；
4. irAE 与疗效分开；
5. 没有证据不写断言。

## 使用

```bash
python -m services.domain_packs.cli validate packs/biomed-oncoimmuno
```

## 许可

AGPL-3.0-only。
