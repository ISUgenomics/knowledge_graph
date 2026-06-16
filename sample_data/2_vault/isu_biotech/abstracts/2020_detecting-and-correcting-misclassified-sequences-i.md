---
title: "Detecting and correcting misclassified sequences in the large-scale public databases"
doi: "https://doi.org/10.1093/bioinformatics/btaa586"
year: 2020
journal: "Bioinformatics"
pmid: "32579213"
authors:
  - "[[hamid-bagheri]]"
  - "[[hridesh-rajan]]"
  - "[[andrew-severin]]"
tags: [biomedical, genomics]
_indexed: 2026-06-15
---

# Detecting and correcting misclassified sequences in the large-scale public databases

## Abstract

MOTIVATION: As the cost of sequencing decreases, the amount of data being deposited into public repositories is increasing rapidly. Public databases rely on the user to provide metadata for each submission that is prone to user error. Unfortunately, most public databases, such as non-redundant (NR), rely on user input and do not have methods for identifying errors in the provided metadata, leading to the potential for error propagation. Previous research on a small subset of the NR database analyzed misclassification based on sequence similarity. To the best of our knowledge, the amount of misclassification in the entire database has not been quantified. We propose a heuristic method to detect potentially misclassified taxonomic assignments in the NR database. We applied a curation technique and quality control to find the most probable taxonomic assignment. Our method incorporates provenance and frequency of each annotation from manually and computationally created databases and clustering information at 95% similarity. RESULTS: We found more than two million potentially taxonomically misclassified proteins in the NR database. Using simulated data, we show a high precision of 97% and a recall of 87% for detecting taxonomically misclassified proteins. The proposed approach and findings could also be applied to other databases. AVAILABILITY AND IMPLEMENTATION: Source code, dataset, documentation, Jupyter notebooks and Docker container are available at https://github.com/boalang/nr. SUPPLEMENTARY INFORMATION: Supplementary data are available at Bioinformatics online.

## Authors

- [[hamid-bagheri]]
- [[hridesh-rajan]]
- [[andrew-severin]]

**DOI:** https://doi.org/10.1093/bioinformatics/btaa586
**PMID:** [32579213](https://pubmed.ncbi.nlm.nih.gov/32579213/)
**Journal:** Bioinformatics
**Year:** 2020
