---
title: "Novel R Shiny Tool for Survival Analysis With Time-Varying Covariate in Oncology Studies: Overcoming Biases and Enhancing Collaboration"
doi: "10.1200/CCI-25-00225"
year: 2026
journal: "JCO clinical cancer informatics"
pmid: "41616239"
authors:
  - "[[li-y]]"
  - "[[qiao-y]]"
  - "[[gao-f]]"
  - "[[gauthier-j]]"
  - "[[zhang-qe]]"
  - "[[voutsinas-j]]"
  - "[[leisenring-w]]"
  - "[[gooley-t]]"
  - "[[summers-c]]"
  - "[[hirayama-a]]"
  - "[[turtle-cj]]"
  - "[[gardner-r]]"
  - "[[zee-j]]"
  - "[[wu-qv]]"
tags: [humans, hematopoietic-stem-cell-transplantation, proportional-hazards-models, survival-analysis, immunotherapy-adoptive, bias, kaplan-meier-estimate, medical-oncology, precursor-cell-lymphoblastic, neoplasms]
_indexed: 2026-06-01
---

# Novel R Shiny Tool for Survival Analysis With Time-Varying Covariate in Oncology Studies: Overcoming Biases and Enhancing Collaboration

## Abstract

PURPOSE: Our study is motivated by evaluating the role of hematopoietic cell transplantation (HCT) after chimeric antigen receptor T-cell (CAR-T) therapy for ALL, a debated topic. Because patients may receive HCT at different times after CAR-T infusion or never, HCT post-CAR-T should be considered as a time-varying covariate (TVC). METHODS: Standard Cox models and Kaplan-Meier (KM) curves (naïve method) assume that TVC status is known and fixed at baseline, which can yield biased estimates. Landmark analysis is a popular alternative but depends on a chosen landmark time. Time-dependent (TD) Cox model is better suited for TVC although visualizing survival curves is complex. The newly proposed Smith-Zee method generates appropriate survival curves from TD Cox models. RESULTS: To address these challenges, we developed an open-source R Shiny tool integrating multiple models (naïve Cox, landmark Cox, and TD Cox) and curves (naïve KM, landmark KM, Smith-Zee, and Extended KM) to facilitate TVC analysis. Reanalysis of post-CAR-T HCT's effect on leukemia-free survival (LFS) showed consistent results between naïve and TD Cox models, whereas landmark analyses varied by landmark time. A separate data analysis of chronic graft-versus-host disease and survival showed that substantial differences emerged across statistical methods. Simulations revealed increased bias in naïve methods when TVC changed late and minimal bias when TVC changes occurred early relative to time to events. CONCLUSION: We recommend TD Cox models and Smith-Zee curves for robust TVC analysis. Our R Shiny tool supports standardized analyses without requiring data sharing, thereby promoting collaboration across different institutions and providing a practical tool to advance survival analysis in oncology research.

## Authors

- [[li-y]]
- [[qiao-y]]
- [[gao-f]]
- [[gauthier-j]]
- [[zhang-qe]]
- [[voutsinas-j]]
- [[leisenring-w]]
- [[gooley-t]]
- [[summers-c]]
- [[hirayama-a]]
- [[turtle-cj]]
- [[gardner-r]]
- [[zee-j]]
- [[wu-qv]]

**DOI:** 10.1200/CCI-25-00225
**PMID:** [41616239](https://pubmed.ncbi.nlm.nih.gov/41616239/)
**Journal:** JCO clinical cancer informatics
**Year:** 2026
