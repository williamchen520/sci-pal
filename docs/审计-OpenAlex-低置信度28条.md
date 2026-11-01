# OpenAlex 低置信度校验清单

> Filter: confidence=low, match=any  
> Rows: 28


> **用途**：这 28 条是 AI 预标注中 `confidence=low` 的行，优先人工复核。  
> **注意**：`ai_prelabel_*` 只是启发式结果，不是人工 ground truth。  
> **CSV**：`eval/validation/openalex_100_low_confidence.csv`  
> **复核后**：填写 `human_domain`、`human_topic_match`、`human_notes`，再运行 `scripts/score_openalex_validation.py`。

## 复核建议

```text
1. 先看 match=no
2. 再看 partial
3. 最后看 yes 但 confidence=low
4. 每条保留 OpenAlex / DOI / MeSH 证据
```

| sample | topic | title | match | OpenAlex | DOI |
|---|---|---|---|---|---|
| OA006 | Parkinson's Disease Mechanisms and Treatments | A conditional two‐step approach for detecting Lewy Body pathology: smell functio | no | https://openalex.org/W7117307150 | https://doi.org/10.1002/alz70856_102894 |
| OA010 | Advanced MRI Techniques and Applications | Sex differences in cerebrovascular function across an aerobic exercise intervent | partial | https://openalex.org/W7154830262 | https://doi.org/10.14814/phy2.70880 |
| OA013 | Gut microbiota and health | Across Kingdoms: The Bacteriome, Mycobiome, and Virome in Autoimmune Diseases: M | partial | https://openalex.org/W7165677616 | https://doi.org/10.3390/nu18122032 |
| OA026 | Neuroinflammation and Neurodegeneration Mechanisms | Editorial: Astrocytes and immunity: unveiling their role in pain and neurodegene | no | https://openalex.org/W7202161180 | https://doi.org/10.3389/fnagi.2026.1944416 |
| OA028 | Sepsis Diagnosis and Treatment | Inflammatory gut–liver crosstalk: mechanisms and therapeutic targets | partial | https://openalex.org/W7197007040 | https://doi.org/10.1038/s12276-026-01810-3 |
| OA029 | Nanocluster Synthesis and Applications | Role of nanoclusters in the design and development of novel strategies for diagn | no | https://openalex.org/W7204967358 | https://doi.org/10.1039/d6na00472e |
| OA036 | Neuroinflammation and Neurodegeneration Mechanisms | The Role of the Mammalian Target of Rapamycin in Microglial Phenotypic Polarizat | partial | https://openalex.org/W7213017946 | https://doi.org/10.3390/cells15181654 |
| OA039 | Acute Lymphoblastic Leukemia research | Leucine, autoimmune diseases, and circulating mediators shape the causal landsca | partial | https://openalex.org/W7212264339 | https://doi.org/10.3389/fimmu.2026.1934057 |
| OA043 | Cardiac tumors and thrombi | Primary Malignant Pericardial Mesothelioma Manifesting as Constrictive Pericardi | no | https://openalex.org/W7155010888 | https://doi.org/10.18502/jthc.v21i1.21286 |
| OA044 | Advanced Fluorescence Microscopy Techniques | ATP-Red enables single-cell bioenergetic phenotyping by flow cytometry | partial | https://openalex.org/W7171821908 | https://doi.org/10.1016/j.crmeth.2026.101537 |
| OA045 | BRCA gene mutations in cancer | Pathogenic germline variants in BRCA1/2 are associated with a decreased number o | partial | https://openalex.org/W7214322485 | https://doi.org/10.1186/s13058-026-02387-5 |
| OA046 | Chromosomal and Genetic Variations | Two Eremogone (Caryophyllaceae) genomes provide insights into alpine adaptation | no | https://openalex.org/W7161951428 | https://doi.org/10.1016/j.pld.2026.05.008 |
| OA047 | Osteoarthritis Treatment and Mechanisms | Advances in Injectable miRNA-Loaded Nanocomposite Hydrogel Systems for Cartilage | partial | https://openalex.org/W7213947200 | https://doi.org/10.2147/IJN.S639907 |
| OA053 | Ubiquitin and proteasome pathways | Posttranslational Modifications of p62/SQSTM1 in Health and Disease | no | https://openalex.org/W7214957421 | https://doi.org/10.1002/mco2.70949 |
| OA058 | Neutrophil, Myeloperoxidase and Oxidative Mechanisms | Neutrophil extracellular traps as a potential therapeutic target in inflammatory | partial | https://openalex.org/W7213472333 | https://doi.org/10.3389/fimmu.2026.1935261 |
| OA059 | Environmental Toxicology and Ecotoxicology | Copper bionanocomposite mitigates arsenic toxicity in Oreochromis niloticus | no | https://openalex.org/W7214975854 | https://doi.org/10.1186/s11671-026-04944-5 |
| OA061 | Reproductive Biology and Fertility | Recent Advances and Emerging Applications in Embryo Vitrification for Livestock | partial | https://openalex.org/W7215049330 | https://doi.org/10.1111/rda.70269 |
| OA064 |  | Abstracts | no | https://openalex.org/W7215059094 | https://doi.org/10.1002/jpr3.70233 |
| OA067 | Parkinson's Disease Mechanisms and Treatments | Visualizing α‐synuclein pathology in live brain: A new platform for Parkinson's  | partial | https://openalex.org/W7215069486 | https://doi.org/10.1002/ctm2.70850 |
| OA069 | Machine Learning in Healthcare | STREAM: A data-driven framework for physiological state monitoring in ICU patien | no | https://openalex.org/W7215106669 | https://doi.org/10.1371/journal.pdig.0001753 |
| OA075 | Viral Infections and Vectors | Climate change, rodent ecology, and the rising risk of hantavirus outbreaks: an  | partial | https://openalex.org/W7213547053 | https://doi.org/10.3389/fmicb.2026.1943856 |
| OA078 | Genomics and Rare Diseases | Uncovering the Genetic Landscape of Pediatric Hearing Loss Along the Texas–Mexic | partial | https://openalex.org/W7204264577 | https://doi.org/10.1111/cge.70224 |
| OA080 | Platelet Disorders and Treatments | Unveiling the role of circulating monocyte-macrophage polarization state and PD- | partial | https://openalex.org/W7215099299 | https://doi.org/10.1007/s44313-026-00163-0 |
| OA081 | Cardiovascular Health and Disease Prevention | Automated assessment of breast arterial calcification: a new frontier in cardiov | partial | https://openalex.org/W7213561410 | https://doi.org/10.3389/fcvm.2026.1860391 |
| OA082 | Monoclonal and Polyclonal Antibodies Research | ABL209 (NEOK002): Designing an EGFR × MUC1 Bispecific TOP1i ADC with Promising A | no | https://openalex.org/W7154958558 | https://doi.org/10.1158/1535-7163.MCT-26-0088 |
| OA085 | Autoimmune and Inflammatory Disorders | Use of a Synthetic Polylactic Acid Matrix for Pyoderma Gangrenosum: A Case Serie | partial | https://openalex.org/W7215742541 | https://doi.org/10.1111/iwj.71055 |
| OA099 | Cellular Mechanics and Interactions | Corrigendum to “Matrix nanoalignment programs macrophage vesicular immunity thro | no | https://openalex.org/W7222273385 | https://doi.org/10.1016/j.bioactmat.2026.10.018 |
| OA100 | Animal Nutrition and Physiology | Dietary esculetin improves growth performance and spleen function via the NF-κB/ | no | https://openalex.org/W7213944461 | https://doi.org/10.1016/j.psj.2026.107811 |
