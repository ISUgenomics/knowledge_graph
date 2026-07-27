---
title: "CLEAR: Concise List Enrichment Analysis Reducing Redundancy"
doi: "https://doi.org/10.64898/2026.03.30.715378"
year: 2026
journal: "bioRxiv (Cold Spring Harbor Laboratory)"
authors:
  - "[[xinglin-jia]]"
  - "[[an-phan]]"
  - "[[karin-dorman]]"
  - "[[claus-kadelka]]"
tags: [bioinformatics, gene-expression, single-cell]
_indexed: 2026-06-01
---

# CLEAR: Concise List Enrichment Analysis Reducing Redundancy

## Abstract

Abstract Motivation High-throughput experiments generate genome-wide measurements for thousands of genes, which are often tested marginally. Biological processes are driven by coordinated groups of genes rather than individual genes, making gene set enrichment analysis an essential post hoc interpretation tool. Traditional approaches such as Over-Representation Analysis and Gene Set Enrichment Analysis test gene sets independently, which ignores the hierarchical and overlapping structure of gene set collections such as the Gene Ontology, and often leads to redundant enrichment results. Set-based approaches such as MGSA address this issue by modeling multiple gene sets simultaneously, but they rely on binary gene activation states derived from arbitrary thresholds on gene-level statistics. Results We introduce Concise List Enrichment Analysis Reducing Redundancy (CLEAR), a Bayesian gene set enrichment framework that jointly models gene sets while incorporating continuous gene-level statistics such as test statistics or p-values. CLEAR extends model-based gene set analysis by replacing threshold-based gene activation with a probabilistic model for continuous gene-level statistics. This approach preserves the redundancy-reduction advantages of set-based enrichment methods while avoiding the information loss introduced by binarization. Using both simulated datasets and human gene expression data, we show that CLEAR improves sensitivity compared with existing enrichment approaches while producing a more concise and interpretable set of enriched gene sets. Availability and implementation The source code, data, and a brief tutorial are freely available at https://github.com/jiatuya/CLEAR

## Authors

- [[xinglin-jia]]
- [[an-phan]]
- [[karin-dorman]]
- [[claus-kadelka]]

**DOI:** https://doi.org/10.64898/2026.03.30.715378
**Journal:** bioRxiv (Cold Spring Harbor Laboratory)
**Year:** 2026
