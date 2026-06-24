---
id: "hg_chrom1_tn10mrna_1003"
type: "transcript"
name: "Hg_chrom1_TN10mRNA_1003"
---

# Hg_chrom1_TN10mRNA_1003

## Properties

| Field | Value |
|---|---|
| avg_counts | 1159.4909 |
| avg_egg | 631.9074 |
| avg_female | 2350.6527 |
| avg_glands | 411.5477 |
| avg_j2g | 166.6706 |
| avg_j3 | 2622.3173 |
| avg_j3g | 595.2054 |
| avg_j4 | 3059.7389 |
| avg_male | 920.7134 |
| avg_pj2 | 844.8651 |
| avg_ppj2 | 1176.644 |
| cluster_name | 29-Not_Clustered |
| cluster_score | 0.7481 |
| dge_egg_pj2 | 0.2818 |
| dge_egg_ppj2 | 0.6657 |
| dge_female_male | 1.4933 |
| dge_j3_j4 | 0.2368 |
| dge_j3g_j3b | 2.9626 |
| dge_j4_female | -0.3715 |
| dge_j4_male | -1.8363 |
| dge_pj2_j3 | 1.6025 |
| dge_ppj2_pj2 | -0.368 |
| expression_bin_13 | orange |
| expression_bin_38 | purple |
| mrna_sequence | ATGTTCTCCTCGCTTTTTCTCCTTCCCTTTTCCCTTTTTGCCCTTTTTCTGCTGCTTATCCCCGCTTTTTCTGACCCCCTTTTTCCAATTGTCCCAACTAAATTCGGCCGAGTCAAAGGCTTTGTCCATTCCCTTTCTCCGCCTCCCTCCGCTTTTCGTTTTCGTTCCGTCGATGTTTTCTTTGGCATTCCCTTCGCCACGCCTCCAATTGGCGAATTTCGGTTTGAGAAGCCAATTCCCCCAAAGCGTTGGCACGGCGTCCGAAATGCCATCCGTCCCGTGGCCCCGTGCGTGCCGCACGCGCGCAAACTGTGCAACAAATGCAGCGAGGACTGCCTTTATCTGAATATTTTCACGCCCCACCAACACTCCCTTAGAAAAAGAAATCGTCGTCTGTCCGCTTCTTCCGTTCATCGCCGTCGTCGTCATTCGCCGCTTTTCCCCGTCCTTTTTCTGATCCATGGCGGTGCTTTCGAAGTCGGATCAGCGGCCGACTTCGACAATTACACTGATTTGGGCATGCGATATGTGTCCGCTGGTATTGTGGTGGTTTCCATTCAGTACAGACTCGGCATAATCGGATTTTCATCGACGGGCGATAAGCAAATGGCAGGAAACTTCGGCCTTTGGGACCAATTCGCCGCGTTGGAATTCGTTTCGGAAAACATTGCGCAATTTGGAGGAAACCCTGCGGACATTACCCTTTTTGGCGAAAGTGCCGGCGCCGCGAGCGTTTCTTTCCTCGGACTTTCCCCGCACAGCCAAGGTCTTTTCCAAAAGTGCGTCCAATTAAGCGGCTCGCCTTTGTCCGCGTGGGCACTAAATGGACGCGTAATTAACGAAACTGCCCAATTAGCAGCAGCGATTAATTGCGCTGAGAATGGACGGGAAGGAATCAAAGAATGCCTTAAGGGGAAAACGGTGGACGAATTGTTCGAAGGGGTCGAAAAAGTGGGCAAAACGCGCCAGGAATACGACTTCACCAAATGGGGCCCCCTTTTGGACGGCGACTTTCTGCCGGCGGACATTCCGCAACTGATCGAAAGAGCACCGCCGAAGCCCACAGTGATGGGAATTGCCGATTTAGAGACACTTTTATGGACATTGGCCATCGGTCACAACGACAGCATTTCACTTTATGCAATTCCATGGGACGAAATGGCCAATTTTGACAGACGACGCTTTGAAATCAAATGGCGACGGAATTGCAACGAGAAATTGTGCAATTTTACACAAGAGACAAAGCGGTGGAGAGAATTGAAAATGAGGGCGAATATTATGAGGAAAATCACTTTGCTTTTGTCTGACCTCCAATTCGCCGTGCCGGTCATTTGGGAGGCGGCGCAAAAGGCGCAGAAGGGGTGGCCGATTTACTTCTTCAAAAACAGTTACTTCAACGAAGTGGTCTTCCCAAAAGTGGTCAAAGTCAGACAAAATTTCCACGCCAACGATTTTATTTATTTTTTCGACCGAAAAGTGTATCGTTTTGAATTCAATGCCAATGACAAATTAATCAGCAATTTTCTGATGGACACTGTGATTAATTTTGTGAAAACAGCTAATCCGTCATCCGACCACAGTACCGTCCAATGGCTTCCAATGGCTCCGAAGGATCCATCAGAAAGTTTTATGCATTTGTTGATCGAAATGCCAATGCCGAAAATGAACCCGAAAATGGAGGAGGAAATTGGCAGGGCCCAATTTTGGACGCAAATGCGAACAAAACACCCGAAGATTGACTTAATCAGGGGCCAATTTTGA |

## Relationships

### HAS_EXPRESSION_CONTRAST

- [[contrasts/contrast_definition-egg-vs-ppj2|Egg vs ppJ2]] (log2_fold_change=0.6657, source_column=dge_egg_ppj2)
- [[contrasts/contrast_definition-egg-vs-pj2|Egg vs pJ2]] (log2_fold_change=0.2818, source_column=dge_egg_pj2)
- [[contrasts/contrast_definition-ppj2-vs-pj2|ppJ2 vs pJ2]] (log2_fold_change=-0.368, source_column=dge_ppj2_pj2)
- [[contrasts/contrast_definition-pj2-vs-j3|pJ2 vs J3]] (log2_fold_change=1.6025, source_column=dge_pj2_j3)
- [[contrasts/contrast_definition-j3-vs-j4|J3 vs J4]] (log2_fold_change=0.2368, source_column=dge_j3_j4)
- [[contrasts/contrast_definition-j4-vs-f|J4 vs F]] (log2_fold_change=-0.3715, source_column=dge_j4_female)
- [[contrasts/contrast_definition-j4-vs-m|J4 vs M]] (log2_fold_change=-1.8363, source_column=dge_j4_male)
- [[contrasts/contrast_definition-f-vs-m|F vs M]] (log2_fold_change=1.4933, source_column=dge_female_male)
- [[contrasts/contrast_definition-g-j3-vs-j3|G(J3) vs J3]] (log2_fold_change=2.9626, source_column=dge_j3g_j3b)

### HAS_EXPRESSION_SUMMARY

- [[expression/expression_measure-egg|Egg]] (expression_value=631.9074, source_column=avg_egg)
- [[expression/expression_measure-ppj2|ppJ2]] (expression_value=1176.644, source_column=avg_ppj2)
- [[expression/expression_measure-pj2|pJ2]] (expression_value=844.8651, source_column=avg_pj2)
- [[expression/expression_measure-j3|J3]] (expression_value=2622.3173, source_column=avg_j3)
- [[expression/expression_measure-j4|J4]] (expression_value=3059.7389, source_column=avg_j4)
- [[expression/expression_measure-female|Female]] (expression_value=2350.6527, source_column=avg_female)
- [[expression/expression_measure-male|Male]] (expression_value=920.7134, source_column=avg_male)

### HAS_TRANSCRIPT

- [[genes/hg_chrom1_tn10gene_959|Hg_chrom1_TN10gene_959]]

### TAGGED

- [[tags/tag-orange|orange]] (source_column=expression_bin_13)
- [[tags/tag-purple|purple]] (source_column=expression_bin_38)

### TRANSLATED_TO

- [[proteins/hg_chrom1_tn10mrna_1003-protein|Unknown_Hg_chrom1_TN10mRNA_1003]]
