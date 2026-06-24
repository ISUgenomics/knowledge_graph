---
id: "hg_chrom1_tn10mrna_1005"
type: "transcript"
name: "Hg_chrom1_TN10mRNA_1005"
---

# Hg_chrom1_TN10mRNA_1005

## Properties

| Field | Value |
|---|---|
| avg_counts | 548.2759 |
| avg_egg | 1097.9437 |
| avg_female | 1163.0151 |
| avg_glands | 340.4298 |
| avg_j2g | 192.0845 |
| avg_j3 | 543.5562 |
| avg_j3g | 451.6887 |
| avg_j4 | 494.4395 |
| avg_male | 433.2653 |
| avg_pj2 | 462.1557 |
| avg_ppj2 | 613.5042 |
| cluster_name | 19-Eggs_Female |
| cluster_score | 0.9982 |
| dge_egg_pj2 | -1.3855 |
| dge_egg_ppj2 | -1.0697 |
| dge_female_male | 1.5671 |
| dge_j4_female | 1.2439 |
| dge_j4_male | -0.2969 |
| dge_pj2_j3 | 0.2018 |
| dge_ppj2_pj2 | -0.2995 |
| expression_bin_13 | darkgrey |
| expression_bin_38 | grey |
| mrna_sequence | ATGAGTGCTTTAATTGGGATGGAATTTTCCAATTTCTACGCCTATTATGACAATTTGGCTGCGCTAATCGACCAACAAACGTGGGAAGCAGCTGAACAGGCGTCCGTGTTGCTTTGTTGTCGTGACAAACATGCGGACCTTAAATTTCTTCAGTTATGTGTGAAAATAGGTGGAGATCGCTACGACGACCGTGCCGTGGTCCGATGGGCCGTGTTCGACGACATTGTGTTGTCCCATTTGAATGTGCTGCACGCGCTCAGTGCGTCCGATTGGCCGGCGGCGTTTGGCCATCAAACGAATGCCCTGCAGCTGTTCAATAGGGAAATTTTGCAGCGCGAAAAGGACGCCAATTGGTTCATGCCCATCCTTTACGTGCTGTGCAGCGACTTGCGACTCATTGCGCGAATTGCTGACAAGCGCGGCTGTGTGCTGTGGGGCGGCCACCACCAGCGGAAGTCGGCCGACGCGCAAACGGCGACCTTTTACGAAGAGTCGGCCGCCTCAATTATGGAGAGTTACCGCATTTGTGTGGCGGAGCGGTCGGACGCGACCACAAAGAAAGTGGCCATCCTCAGTCTGACCAACCAATTGTTCCGCATTTATTTTGGGATCAACCGTTTGCATCTGCTGAAACCGCTTATCCGCAGCATTGACCACGTGGGCGAACTGTACGACCGTTTTTCGCTGGCCGACAAAATCACTTACAAATACTTTTTGGGCCGAAAAGCGATGTTTGACATGGACCTTTCCCGTGCCGAGGAAGCACTGACATTCGCTTTTGAGCACTGTCCGGCTCATTTCATGCACAACAAACGGCTCATTCTGATGTATTTGGTGCCCGTCAAAATGTTCCTTGGCCATATGCCCACCCAACAATTGCTCGTCCGCTACAACCTTGGCCAATTTGCCGACGTTGCCGCCAGCGTTAAGGATGGCAATTTGCGCGACCTGAACTTGGCACTGCAAAAACACCAACACTTTTTCATCAAATGCGGCATCTTTTTGATGTTGGAAAAGCTCAAAGTGATCACCTACAGAAACCTCTTCAAGCGAGTTGCTTCCATTCTGAACACCCATCTGATCAAATTGGACGCTTTCCTCGCCGTCCTTCGCTTTTTGGGCACGGACATTGACGCGGACGAATTGTCGTGCATTTTGGCCAATTTAATTGCGCAAAAGAAAATCAAAGGGTACATATCGCATCAGAGACAGACTTTGGTGATCTCAAAGCAAACGCCGTTCCCTTCCCTTTCCGCCGCTTAA |

## Relationships

### HAS_EXPRESSION_CONTRAST

- [[contrasts/contrast_definition-egg-vs-ppj2|Egg vs ppJ2]] (log2_fold_change=-1.0697, source_column=dge_egg_ppj2)
- [[contrasts/contrast_definition-egg-vs-pj2|Egg vs pJ2]] (log2_fold_change=-1.3855, source_column=dge_egg_pj2)
- [[contrasts/contrast_definition-ppj2-vs-pj2|ppJ2 vs pJ2]] (log2_fold_change=-0.2995, source_column=dge_ppj2_pj2)
- [[contrasts/contrast_definition-pj2-vs-j3|pJ2 vs J3]] (log2_fold_change=0.2018, source_column=dge_pj2_j3)
- [[contrasts/contrast_definition-j4-vs-f|J4 vs F]] (log2_fold_change=1.2439, source_column=dge_j4_female)
- [[contrasts/contrast_definition-j4-vs-m|J4 vs M]] (log2_fold_change=-0.2969, source_column=dge_j4_male)
- [[contrasts/contrast_definition-f-vs-m|F vs M]] (log2_fold_change=1.5671, source_column=dge_female_male)

### HAS_EXPRESSION_SUMMARY

- [[expression/expression_measure-egg|Egg]] (expression_value=1097.9437, source_column=avg_egg)
- [[expression/expression_measure-ppj2|ppJ2]] (expression_value=613.5042, source_column=avg_ppj2)
- [[expression/expression_measure-pj2|pJ2]] (expression_value=462.1557, source_column=avg_pj2)
- [[expression/expression_measure-j3|J3]] (expression_value=543.5562, source_column=avg_j3)
- [[expression/expression_measure-j4|J4]] (expression_value=494.4395, source_column=avg_j4)
- [[expression/expression_measure-female|Female]] (expression_value=1163.0151, source_column=avg_female)
- [[expression/expression_measure-male|Male]] (expression_value=433.2653, source_column=avg_male)

### HAS_TRANSCRIPT

- [[genes/hg_chrom1_tn10gene_960|Hg_chrom1_TN10gene_960]]

### TAGGED

- [[tags/tag-darkgrey|darkgrey]] (source_column=expression_bin_13)
- [[tags/tag-grey|grey]] (source_column=expression_bin_38)

### TRANSLATED_TO

- [[proteins/hg_chrom1_tn10mrna_1005-protein|Unknown_Hg_chrom1_TN10mRNA_1005]]
