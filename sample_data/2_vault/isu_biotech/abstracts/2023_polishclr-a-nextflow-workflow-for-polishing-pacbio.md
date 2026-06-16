---
title: "polishCLR: A Nextflow Workflow for Polishing PacBio CLR Genome Assemblies"
doi: "https://doi.org/10.1093/gbe/evad020"
year: 2023
journal: "Genome Biology and Evolution"
pmid: "36792366"
authors:
  - "[[chang-j]]"
  - "[[stahlke-ar]]"
  - "[[rosen-bd]]"
  - "[[childers-ak]]"
  - "[[jennifer-chang]]"
  - "[[amanda-stahlke]]"
  - "[[sivanandan-chudalayandi]]"
  - "[[benjamin-rosen]]"
  - "[[anna-childers]]"
  - "[[siva-chudalayandi]]"
  - "[[andrew-severin]]"
tags: [genomics, molecular-biology]
_indexed: 2026-06-15
---

# polishCLR: A Nextflow Workflow for Polishing PacBio CLR Genome Assemblies

## Abstract

Long-read sequencing has revolutionized genome assembly, yielding highly contiguous, chromosome-level contigs. However, assemblies from some third generation long read technologies, such as Pacific Biosciences (PacBio) continuous long reads (CLR), have a high error rate. Such errors can be corrected with short reads through a process called polishing. Although best practices for polishing non-model de novo genome assemblies were recently described by the Vertebrate Genome Project (VGP) Assembly community, there is a need for a publicly available, reproducible workflow that can be easily implemented and run on a conventional high performance computing environment. Here, we describe polishCLR (https://github.com/isugifNF/polishCLR), a reproducible Nextflow workflow that implements best practices for polishing assemblies made from CLR data. PolishCLR can be initiated from several input options that extend best practices to suboptimal cases. It also provides re-entry points throughout several key processes, including identifying duplicate haplotypes in purge_dups, allowing a break for scaffolding if data are available, and throughout multiple rounds of polishing and evaluation with Arrow and FreeBayes. PolishCLR is containerized and publicly available for the greater assembly community as a tool to complete assemblies from existing, error-prone long-read data.

## Authors

- [[chang-j]]
- [[stahlke-ar]]
- [[rosen-bd]]
- [[childers-ak]]
- [[jennifer-chang]]
- [[amanda-stahlke]]
- [[sivanandan-chudalayandi]]
- [[benjamin-rosen]]
- [[anna-childers]]
- [[siva-chudalayandi]]
- [[andrew-severin]]

**DOI:** https://doi.org/10.1093/gbe/evad020
**PMID:** [36792366](https://pubmed.ncbi.nlm.nih.gov/36792366/)
**Journal:** Genome Biology and Evolution
**Year:** 2023
