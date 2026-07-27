---
title: "FSEA: Incorporating domain-specific prior knowledge for few-shot weed detection"
doi: "https://doi.org/10.1016/j.plaphe.2025.100086"
year: 2025
journal: "Plant Phenomics"
pmid: "41416189"
authors:
  - "[[jingyao-gai]]"
  - "[[lu-bao]]"
  - "[[shijie-liu]]"
  - "[[mingzhang-pan]]"
  - "[[boqian-chen]]"
  - "[[lie-tang]]"
  - "[[haiyan-cen]]"
tags: [agriculture, remote-sensing, wood-and-agarwood]
_indexed: 2026-06-01
---

# FSEA: Incorporating domain-specific prior knowledge for few-shot weed detection

## Abstract

Deep learning-based crop and weed detection is essential for modern precision weed control. But its effectiveness is limited when facing newly presented weed species due to the impracticality of collecting large, balanced training datasets in field conditions. To address these challenges, this study presents a few-shot learning framework that achieves rapid and effective adaptation to new weed species by leveraging domain-specific characteristics of plant detection. We proposed few-shot enhanced attention (FSEA) network, built upon Faster R-CNN, which implements three prior knowledge in weed detection through: (1) designing a channel attention-based feature fusion module with an excess-green feature extractor to leverage color characteristics of plants and background, (2) designing a feature enhancement module to accommodate diverse plant morphologies, and (3) applying an optimized loss function designed specifically for plant occlusion scenarios. Using commonly observed crop and weed species (common beet, sugarcane, barnyard grass, field pennycress and Chinese money plant) as base classes, FSEA achieved an all-class mAP of 0.416 and a novel-class mAP of 0.346 when adapting to less frequent weed species (common purslane, Asian copperleaf, goosefoot, clover, and goosegrass), after training for 40 epochs using only 30 samples per species. This performance significantly outperforms state-of-the-art few-shot detectors (TFA, FSCE, Meta R-CNN, Meta-DETR, DCFS, DiGEO) and traditional detector YOLOv7, indicating the effectiveness of incorporating domain-specific prior knowledge into few-shot weed detection. This study provides a fundamental methodology for rapid adaptation of weed detection systems to new environments and species, making automated weed management more practical and accessible for various agricultural applications. The source code and dataset are publicly available (https://github.com/skyofyao/FSEA) to facilitate further research in this domain.

## Authors

- [[jingyao-gai]]
- [[lu-bao]]
- [[shijie-liu]]
- [[mingzhang-pan]]
- [[boqian-chen]]
- [[lie-tang]]
- [[haiyan-cen]]

**DOI:** https://doi.org/10.1016/j.plaphe.2025.100086
**PMID:** [41416189](https://pubmed.ncbi.nlm.nih.gov/41416189/)
**Journal:** Plant Phenomics
**Year:** 2025
