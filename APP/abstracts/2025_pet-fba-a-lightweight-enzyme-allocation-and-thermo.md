---
title: "PET-FBA: A lightweight enzyme allocation and thermodynamics-constrained flux analysis approach to explore Escherichia coli metabolic adaptation to intracellular acidification"
doi: "https://doi.org/10.1016/j.ymben.2025.12.003"
year: 2025
journal: "Metabolic Engineering"
pmid: "41386341"
authors:
  - "[[chao-wu]]"
  - "[[jeffrey-law]]"
  - "[[onyeka-onyenemezu]]"
  - "[[jetendra-kumar-roy]]"
  - "[[peter-st-john]]"
  - "[[robert-jernigan]]"
  - "[[yannick-bomble]]"
  - "[[laura-jarboe]]"
tags: [microbial-metabolic-engineering, bacterial-genetics, gene-regulatory-network-analysis, escherichia-coli, escherichia-coli-proteins, hydrogen-ion-concentration, models-biological, thermodynamics, metabolic-flux-analysis, adaptation-physiological]
_indexed: 2026-06-01
---

# PET-FBA: A lightweight enzyme allocation and thermodynamics-constrained flux analysis approach to explore Escherichia coli metabolic adaptation to intracellular acidification

## Abstract

Escherichia coli employs diverse strategies to adapt to acidic environments that disrupt enzyme activity and the thermodynamic feasibility of essential reactions. To understand the impact of pH stress on cell metabolism, we present the PET-FBA (pH-, Enzyme protein allocation-, and Thermodynamics-constrained Flux Balance Analysis) framework. PET-FBA extends genome-scale modeling by integrating enzyme protein costs and reaction Gibbs free energy changes. Additionally, by incorporating pH-dependent enzyme kinetics in response to intracellular acidification, this framework enables the simulation of E. coli's metabolic adjustments across varying external pH levels. The model's accuracy is validated by comparing in silico growth simulations with experimental measurements under both anaerobic and aerobic conditions, as well as in silico gene knockouts of essential genes. By explicitly incorporating pH effects, our model accurately replicates the metabolic shift towards lactate production as the primary fermentation product at low pH in anaerobic conditions. This shift is only predicted when enzyme kinetics are dynamically adjusted as a function of pH. Further analysis revealed that this shift can be attributed to the reduced protein efficiency of the acetyl-CoA branch compared to lactate dehydrogenase under acidic stress, which then becomes crucial for maintaining NAD regeneration and cell growth at low pH. Furthermore, we identified strategies for enhancing cell growth under acidic anaerobic conditions by improving the enzyme activity of lactate dehydrogenase and pyruvate formate lyase, which increases NAD production efficiency and reduces enzyme protein allocation costs. Designed as a lightweight yet versatile framework, PET-FBA enables efficient genome-scale metabolic analysis. Using E. coli as a model system, our framework provides a systematic approach to understanding metabolic responses to environmental stress, pinpointing key metabolic bottlenecks, and identifying potential targets for strain optimization. This work also highlights the critical role of intracellular acidification in shaping enzyme performance and microbial adaptation. The PET-FBA framework is implemented as a Python package at https://github.com/Chaowu88/etfba, with detailed documentation provided at https://etfba.readthedocs.io.

## Authors

- [[chao-wu]]
- [[jeffrey-law]]
- [[onyeka-onyenemezu]]
- [[jetendra-kumar-roy]]
- [[peter-st-john]]
- [[robert-jernigan]]
- [[yannick-bomble]]
- [[laura-jarboe]]

**DOI:** https://doi.org/10.1016/j.ymben.2025.12.003
**PMID:** [41386341](https://pubmed.ncbi.nlm.nih.gov/41386341/)
**Journal:** Metabolic Engineering
**Year:** 2025
