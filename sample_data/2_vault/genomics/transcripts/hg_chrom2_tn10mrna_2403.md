---
id: "hg_chrom2_tn10mrna_2403"
type: "transcript"
name: "Hg_chrom2_TN10mRNA_2403"
---

# Hg_chrom2_TN10mRNA_2403

## Properties

| Field | Value |
|---|---|
| avg_counts | 3237.7301 |
| avg_egg | 6.5556 |
| avg_female | 436.364 |
| avg_glands | 6886.1687 |
| avg_j2g | 843.7596 |
| avg_j3 | 2376.4147 |
| avg_j3g | 11417.9756 |
| avg_j4 | 242.7982 |
| avg_male | 131.8069 |
| avg_pj2 | 2418.6854 |
| avg_ppj2 | 25.4392 |
| cluster_name | 21-Not_Clustered |
| cluster_score | 0.9469 |
| dge_egg_pj2 | 8.3849 |
| dge_egg_ppj2 | 1.7212 |
| dge_female_male | 1.8725 |
| dge_j3_j4 | -3.2766 |
| dge_j3g_j2g | -3.8652 |
| dge_j4_female | 0.8547 |
| dge_j4_male | -0.9995 |
| dge_ppj2_pj2 | 6.6851 |
| expression_bin_13 | magenta |
| expression_bin_38 | pink |
| mrna_sequence | atggcttcatctttctgctcctcaatcatttccatcgtcgcaattgtctgtttgctgtgcaaatgctgcttttcagcaccccatccatgctgtcctggcagccaacatgttgtttcgatgatgaaagatcacaccggcacattctccgcttcgatgccaaagtcttcgctttgtctgagtgccgaaagagtcgccgctgcggtggaaaaccaactgaaaacaatttggtgccctggcaatggtagtcaaacactcatcaacgagatcaacgcagctcaatcatcatctgatgagtgtgctcgctctctcggcttcgtccgtgccatgttcgaaattgccgcttccgccgcttcccatgtcggtgccaacgccgaattggccaatttggctgtccagttccgagaacaagttggcacaattgacaccaactgtgctgcgctggacattcgtgttgggcaaatcagcttgggcactctcaagggagaccatccgcaagtgcatgactctgagagtgtgcttagtaaccctggcaccagcgggtctcacaagcGCATTTAA |

## Relationships

### HAS_EXPRESSION_CONTRAST

- [[contrasts/contrast_definition-egg-vs-ppj2|Egg vs ppJ2]] (log2_fold_change=1.7212, source_column=dge_egg_ppj2)
- [[contrasts/contrast_definition-egg-vs-pj2|Egg vs pJ2]] (log2_fold_change=8.3849, source_column=dge_egg_pj2)
- [[contrasts/contrast_definition-ppj2-vs-pj2|ppJ2 vs pJ2]] (log2_fold_change=6.6851, source_column=dge_ppj2_pj2)
- [[contrasts/contrast_definition-j3-vs-j4|J3 vs J4]] (log2_fold_change=-3.2766, source_column=dge_j3_j4)
- [[contrasts/contrast_definition-j4-vs-f|J4 vs F]] (log2_fold_change=0.8547, source_column=dge_j4_female)
- [[contrasts/contrast_definition-j4-vs-m|J4 vs M]] (log2_fold_change=-0.9995, source_column=dge_j4_male)
- [[contrasts/contrast_definition-f-vs-m|F vs M]] (log2_fold_change=1.8725, source_column=dge_female_male)
- [[contrasts/contrast_definition-g-j3-vs-j2|G(J3 vs J2)]] (log2_fold_change=-3.8652, source_column=dge_j3g_j2g)

### HAS_EXPRESSION_SUMMARY

- [[expression/expression_measure-egg|Egg]] (expression_value=6.5556, source_column=avg_egg)
- [[expression/expression_measure-ppj2|ppJ2]] (expression_value=25.4392, source_column=avg_ppj2)
- [[expression/expression_measure-pj2|pJ2]] (expression_value=2418.6854, source_column=avg_pj2)
- [[expression/expression_measure-j3|J3]] (expression_value=2376.4147, source_column=avg_j3)
- [[expression/expression_measure-j4|J4]] (expression_value=242.7982, source_column=avg_j4)
- [[expression/expression_measure-female|Female]] (expression_value=436.364, source_column=avg_female)
- [[expression/expression_measure-male|Male]] (expression_value=131.8069, source_column=avg_male)

### HAS_TRANSCRIPT

- [[genes/hg_chrom2_tn10gene_2302|Hg_chrom2_TN10gene_2302]]

### TAGGED

- [[tags/tag-magenta|magenta]] (source_column=expression_bin_13)
- [[tags/tag-pink|pink]] (source_column=expression_bin_38)

### TRANSLATED_TO

- [[proteins/hg_chrom2_tn10mrna_2403-protein|16B09]]
