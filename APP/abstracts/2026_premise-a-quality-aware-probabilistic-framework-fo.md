---
title: "PREMISE: A Quality-Aware Probabilistic Framework for Pathogen Resolution and Source Assignment in Viral mNGS"
doi: "https://doi.org/10.64898/2026.03.15.711921"
year: 2026
journal: "bioRxiv (Cold Spring Harbor Laboratory)"
authors:
  - "[[sriram-vijendran]]"
  - "[[karin-dorman]]"
  - "[[tavis-anderson]]"
  - "[[oliver-eulenstein]]"
tags: [influenza-virus-research, respiratory-viral-infections, salmonella]
_indexed: 2026-06-01
---

# PREMISE: A Quality-Aware Probabilistic Framework for Pathogen Resolution and Source Assignment in Viral mNGS

## Abstract

Abstract The circulation of Influenza A viruses (IAVs) in wildlife and livestock presents a significant public health threat due to their zoonotic potential and rapid genomic diversification. Accurate classification of viral subtypes and characterization of within-host diversity are crucial for risk assessment and vaccine development. Although metagenomic sequencing facilitates early detection, prevalent memory-efficient k-mer-based pipelines often discard critical linkage information. This loss of information can result in missed or imprecise pathogen identification, potentially delaying clinical and public health responses. We introduce PREMISE (Pathogen Resolution via Expectation Maximization In Sequencing Experiments), a probabilistic, alignment-based framework implemented in RUST for high-resolution viral genome identification. By integrating advanced string data structures for efficient alignment with a quality-score-aware Expectation-Maximization algorithm, PREMISE accurately identifies source strains, estimates relative abundances, and performs precise read assignments. This framework provides superior source estimation with statistical confidence, enabling the identification of mixed infections, recombination, and IAV-reassortment directly from raw data. Validated against simulated and empirical datasets, PREMISE outperforms state-of-the-art k-mer methods. Ultimately, this framework represents a significant advancement in viral identification, providing a foundation for novel approaches that can automatically flag reassorted viruses or recombination events in the future, thereby improving the detection of emerging pathogens with zoonotic potential. Availability https://github.com/sriram98v/premise under a MIT license. Contact sriramv@iastate.edu

## Authors

- [[sriram-vijendran]]
- [[karin-dorman]]
- [[tavis-anderson]]
- [[oliver-eulenstein]]

**DOI:** https://doi.org/10.64898/2026.03.15.711921
**Journal:** bioRxiv (Cold Spring Harbor Laboratory)
**Year:** 2026
