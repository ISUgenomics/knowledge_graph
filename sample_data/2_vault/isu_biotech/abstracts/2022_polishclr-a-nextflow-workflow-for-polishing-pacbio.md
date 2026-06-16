---
title: "“polishCLR: a Nextflow workflow for polishing PacBio CLR genome assemblies”"
doi: "https://doi.org/10.1101/2022.02.10.480011"
year: 2022
journal: "bioRxiv (Cold Spring Harbor Laboratory)"
authors:
  - "[[jennifer-chang]]"
  - "[[amanda-stahlke]]"
  - "[[sivanandan-chudalayandi]]"
  - "[[benjamin-rosen]]"
  - "[[anna-childers]]"
  - "[[andrew-severin]]"
tags: [genomics]
_indexed: 2026-06-15
---

# “polishCLR: a Nextflow workflow for polishing PacBio CLR genome assemblies”

## Abstract

Abstract Long-read sequencing has revolutionized genome assembly, yielding highly contiguous, chromosome-level contigs. However, assemblies from some third generation long read technologies, such as Pacific Biosciences (PacBio) Continuous Long Reads (CLR), have a high error rate. Such errors can be corrected with short reads through a process called polishing. Although best practices for polishing non-model de novo genome assemblies were recently described by the Vertebrate Genome Project (VGP) Assembly community, there is a need for a publicly available, reproducible workflow that can be easily implemented and run on a conventional high performance computing environment. Here, we describe polishCLR ( https://github.com/isugifNF/polishCLR ), a reproducible Nextflow workflow that implements best practices for polishing assemblies made from CLR data. PolishCLR can be initiated from several input options that extend best practices to suboptimal cases. It also provides re-entry points throughout several key processes including identifying duplicate haplotypes in purge_dups, allowing a break for scaffolding if data are available, and throughout multiple rounds of polishing and evaluation with Arrow and FreeBayes. PolishCLR is containerized and publicly available for the greater assembly community as a tool to complete assemblies from existing, error-prone long-read data.

## Authors

- [[jennifer-chang]]
- [[amanda-stahlke]]
- [[sivanandan-chudalayandi]]
- [[benjamin-rosen]]
- [[anna-childers]]
- [[andrew-severin]]

**DOI:** https://doi.org/10.1101/2022.02.10.480011
**Journal:** bioRxiv (Cold Spring Harbor Laboratory)
**Year:** 2022
