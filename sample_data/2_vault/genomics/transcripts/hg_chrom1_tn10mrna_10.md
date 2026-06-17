---
id: "hg_chrom1_tn10mrna_10"
type: "transcript"
name: "Hg_chrom1_TN10mRNA_10"
---

# Hg_chrom1_TN10mRNA_10

## Properties

| Field | Value |
|---|---|
| avg_counts | 115.1821 |
| avg_egg | 6.1026 |
| avg_female | 20.7878 |
| avg_glands | 261.9516 |
| avg_j2g | 0 |
| avg_j3 | 1.8674 |
| avg_j3g | 458.4152 |
| avg_j4 | 56.1002 |
| avg_male | 32.8574 |
| avg_pj2 | 0.7494 |
| avg_ppj2 | 2.8853 |
| cluster_name | 1-J4_Female |
| cluster_score | 0.9822 |
| dge_egg_pj2 | -3.1626 |
| dge_egg_ppj2 | -1.3014 |
| dge_j3_j4 | 4.9485 |
| dge_j3g_j2g | -7.1967 |
| dge_j3g_j3b | -5.4509 |
| dge_j4_female | -1.4222 |
| expression_bin_13 | turquoise |
| expression_bin_38 | black |
| mrna_sequence | ATGCTAAGAAATTTTCAGTCAGGAAATTATTGCCAAGAATCAACAGTGTTGTACCGGACAACTGCTCGGCCAAATTTAATAAGAACTGGAAAATTTGTCGCTGTACAGTACAATGAGAGCAAATTGGCACATCGATTGTTGGACGGTAAACGCGGCATCGAAATCGGCGCCTCCATGCACAATCCGTTCGGCTTGGACACATGGAACATTGACTACACGGACGACCCAAAAGCATTGTTTCAGAAAACCCAAGTTGAAGTTTCAGGAAAAGCAGCCAAAGTGCATATTATCGCTCCCGGGGACAAACTGCCGTTCACGAATAATTCAGTCGATTTTGTGATCAATTCACATGTGTTGGAACACTTTTATGATCCGATCAAGGCCATTGAAGAATGGCTAAGAATTGTGAAGCCCGGTGGCTTCGTTTACATGGATATCCCACACAAAGAACGGACTTTCGACCGGAACCGAAACAGGACAACATTGGCCGAACTGCTTGAACGGCACCAGCACCCCAATGCGGGCAATGACACTGCACATGAGCACCACTCGGTGTGGGTCACGGAAGATGTGCTGGAGCTGTGCCGACATTTTAACTGGACAGTGGCGGATTGGCGAGAAGCGGACGACAAGCTTGGCATCGGTTTCACCATTGTGCTCAAAAGAAGACATGATTTGGGGCAAACACATTTTGGCAAATATGAATGA |

## Relationships

### HAS_EXPRESSION_CONTRAST

- [[contrasts/contrast_definition-egg-vs-ppj2|Egg vs ppJ2]] (log2_fold_change=-1.3014, source_column=dge_egg_ppj2)
- [[contrasts/contrast_definition-egg-vs-pj2|Egg vs pJ2]] (log2_fold_change=-3.1626, source_column=dge_egg_pj2)
- [[contrasts/contrast_definition-j3-vs-j4|J3 vs J4]] (log2_fold_change=4.9485, source_column=dge_j3_j4)
- [[contrasts/contrast_definition-j4-vs-f|J4 vs F]] (log2_fold_change=-1.4222, source_column=dge_j4_female)
- [[contrasts/contrast_definition-g-j3-vs-j2|G(J3 vs J2)]] (log2_fold_change=-7.1967, source_column=dge_j3g_j2g)
- [[contrasts/contrast_definition-g-j3-vs-j3|G(J3) vs J3]] (log2_fold_change=-5.4509, source_column=dge_j3g_j3b)

### HAS_EXPRESSION_SUMMARY

- [[expression/expression_measure-egg|Egg]] (expression_value=6.1026, source_column=avg_egg)
- [[expression/expression_measure-ppj2|ppJ2]] (expression_value=2.8853, source_column=avg_ppj2)
- [[expression/expression_measure-pj2|pJ2]] (expression_value=0.7494, source_column=avg_pj2)
- [[expression/expression_measure-j3|J3]] (expression_value=1.8674, source_column=avg_j3)
- [[expression/expression_measure-j4|J4]] (expression_value=56.1002, source_column=avg_j4)
- [[expression/expression_measure-female|Female]] (expression_value=20.7878, source_column=avg_female)
- [[expression/expression_measure-male|Male]] (expression_value=32.8574, source_column=avg_male)

### HAS_TRANSCRIPT

- [[genes/hg_chrom1_tn10gene_10|Hg_chrom1_TN10gene_10]]

### TAGGED

- [[tags/tag-turquoise|turquoise]] (source_column=expression_bin_13)
- [[tags/tag-black|black]] (source_column=expression_bin_38)

### TRANSLATED_TO

- [[proteins/hg_chrom1_tn10mrna_10-protein|Hg_chrom1_TN10gene_10 protein]]
