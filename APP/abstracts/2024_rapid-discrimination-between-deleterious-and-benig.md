---
title: "Rapid discrimination between deleterious and benign missense mutations in the CAGI 6 experiment"
doi: "https://doi.org/10.1186/s40246-024-00655-z"
year: 2024
journal: "Human Genomics"
pmid: "39192324"
authors:
  - "[[eshel-faraggi]]"
  - "[[robert-jernigan]]"
  - "[[andrzej-kloczkowski]]"
tags: [genomics, machine-learning, humans, mutation-missense, software, computational-biology, proteins]
_indexed: 2026-06-01
---

# Rapid discrimination between deleterious and benign missense mutations in the CAGI 6 experiment

## Abstract

We describe the machine learning tool that we applied in the CAGI 6 experiment to predict whether single residue mutations in proteins are deleterious or benign. This tool was trained using only single sequences, i.e., without multiple sequence alignments or structural information. Instead, we used global characterizations of the protein sequence. Training and testing data for human gene mutations was obtained from ClinVar (ncbi.nlm.nih.gov/pub/ClinVar/), and for non-human gene mutations from Uniprot (www.uniprot.org). Testing was done on post-training data from ClinVar. This testing yielded high AUC and Matthews correlation coefficient (MCC) for well trained examples but low generalizability. For genes with either sparse or unbalanced training data, the prediction accuracy is poor. The resulting prediction server is available online at http://www.mamiris.com/Shoni.cagi6.

## Authors

- [[eshel-faraggi]]
- [[robert-jernigan]]
- [[andrzej-kloczkowski]]

**DOI:** https://doi.org/10.1186/s40246-024-00655-z
**PMID:** [39192324](https://pubmed.ncbi.nlm.nih.gov/39192324/)
**Journal:** Human Genomics
**Year:** 2024
