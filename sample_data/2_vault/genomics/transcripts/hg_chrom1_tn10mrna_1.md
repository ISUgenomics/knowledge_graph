---
id: "hg_chrom1_tn10mrna_1"
type: "transcript"
name: "Hg_chrom1_TN10mRNA_1"
---

# Hg_chrom1_TN10mRNA_1

## Properties

| Field | Value |
|---|---|
| avg_counts | 64.7258 |
| avg_egg | 74.8178 |
| avg_female | 99.0782 |
| avg_glands | 7.8981 |
| avg_j2g | 4.3828 |
| avg_j3 | 99.9076 |
| avg_j3g | 10.5345 |
| avg_j4 | 77.6182 |
| avg_male | 145.0865 |
| avg_pj2 | 96.3413 |
| avg_ppj2 | 125.4272 |
| cluster_name | 9-Migratory |
| cluster_score | 0.9973 |
| dge_egg_ppj2 | 0.516 |
| dge_female_male | -0.4065 |
| dge_j2g_pj2b | 4.8104 |
| dge_j3_j4 | -0.3497 |
| dge_j4_male | 0.7969 |
| dge_ppj2_pj2 | -0.2712 |
| expression_bin_13 | brown |
| expression_bin_38 | brown |
| mrna_sequence | ATGGAATTTGGTGTCTACATGGAGTTGGGACGTGGAGCTAACTATTTGGACCATATAGGCATGCCTCCGTTGTCAGGCCGATTCGAAGGCGCAAGAATGTGTGGTCATTTGGGGCGAGTGCAACCACTGTTTCCACCTTTTTGTATGTCTCTGTGGGTGAAGCAGAACAACCGGTGCCCGCTGTGCCAATCCGATTGGGCTGTCCAACGAAAGAATTCGTTTTTTCCTTTGTGCGCTGTTCATTTTGGCGTAGAGCTGCTGAACGCGTCGCGTAACAGGACATCCCTGGCCGGCTCGCCTGACAGAATCTGTCGGTGTGTACAACAAAGGAAAATTCGTAGGCACCGCAAACCTAAAAATTACAAGATTACAACAGCGATTTGA |

## Relationships

### HAS_EXPRESSION_CONTRAST

- [[contrasts/contrast_definition-egg-vs-ppj2|Egg vs ppJ2]] (log2_fold_change=0.516, source_column=dge_egg_ppj2)
- [[contrasts/contrast_definition-ppj2-vs-pj2|ppJ2 vs pJ2]] (log2_fold_change=-0.2712, source_column=dge_ppj2_pj2)
- [[contrasts/contrast_definition-j3-vs-j4|J3 vs J4]] (log2_fold_change=-0.3497, source_column=dge_j3_j4)
- [[contrasts/contrast_definition-j4-vs-m|J4 vs M]] (log2_fold_change=0.7969, source_column=dge_j4_male)
- [[contrasts/contrast_definition-f-vs-m|F vs M]] (log2_fold_change=-0.4065, source_column=dge_female_male)
- [[contrasts/contrast_definition-g-j2-vs-pj2|G(J2) vs pJ2]] (log2_fold_change=4.8104, source_column=dge_j2g_pj2b)

### HAS_EXPRESSION_SUMMARY

- [[expression/expression_measure-egg|Egg]] (expression_value=74.8178, source_column=avg_egg)
- [[expression/expression_measure-ppj2|ppJ2]] (expression_value=125.4272, source_column=avg_ppj2)
- [[expression/expression_measure-pj2|pJ2]] (expression_value=96.3413, source_column=avg_pj2)
- [[expression/expression_measure-j3|J3]] (expression_value=99.9076, source_column=avg_j3)
- [[expression/expression_measure-j4|J4]] (expression_value=77.6182, source_column=avg_j4)
- [[expression/expression_measure-female|Female]] (expression_value=99.0782, source_column=avg_female)
- [[expression/expression_measure-male|Male]] (expression_value=145.0865, source_column=avg_male)

### HAS_TRANSCRIPT

- [[genes/hg_chrom1_tn10gene_1|Hg_chrom1_TN10gene_1]]

### TAGGED

- [[tags/tag-brown|brown]] (source_column=expression_bin_13)

### TRANSLATED_TO

- [[proteins/hg_chrom1_tn10mrna_1-protein|Unknown_Hg_chrom1_TN10mRNA_1]]
