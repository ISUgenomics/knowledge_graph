---
id: "hg_chrom2_tn10mrna_3439"
type: "transcript"
name: "Hg_chrom2_TN10mRNA_3439"
---

# Hg_chrom2_TN10mRNA_3439

## Properties

| Field | Value |
|---|---|
| avg_counts | 5895.6282 |
| avg_egg | 71.8461 |
| avg_female | 296.221 |
| avg_glands | 12887.1837 |
| avg_j2g | 7612.3067 |
| avg_j3 | 2308.5427 |
| avg_j3g | 16843.3414 |
| avg_j4 | 246.7852 |
| avg_male | 865.7028 |
| avg_pj2 | 4589.1305 |
| avg_ppj2 | 263.9098 |
| cluster_name | 21-pJ2_J3 |
| cluster_score | 0.9999 |
| dge_egg_pj2 | 5.8613 |
| dge_egg_ppj2 | 1.6485 |
| dge_female_male | -1.4019 |
| dge_j3_j4 | -3.211 |
| dge_j4_female | 0.275 |
| dge_j4_male | 1.7011 |
| dge_pj2_j3 | -1.0226 |
| dge_ppj2_pj2 | 4.2289 |
| expression_bin_13 | magenta |
| expression_bin_38 | pink |
| mrna_sequence | ATGATGAAACGCGAGCTGAGCAAAAACGGCCAACTCAGCCCACAGTTATTCCTTTGGAGCCATCCATCCGATCATTCGCTTCATCTGCCAATCCGCAAAATGTCCCTTTTCCGTCCTCAATCGCTGCTTCTTCTGGCCGCTCTTTGCCTGTCCTTTGCGCTGCTCTTTGTCACTTCGTCGGAAGAGGGAGGGCGAGTGAAGCGCGGCGGATGGCCTTGGGATTGGGCCGGCAAACAACTGTGCAAAACATCGGCAAATTGCAAGTGCAAGGATGGCAAAAATTGGGCCAAATGTGTAAAGTCGGAAGGCTACGCGGCCAGCAATTGTTGCGACAAAAATTACGTGTGGGCATGTTGCGGGAAGAAGCCCAAACATTGA |

## Relationships

### HAS_EXPRESSION_CONTRAST

- [[contrasts/contrast_definition-egg-vs-ppj2|Egg vs ppJ2]] (log2_fold_change=1.6485, source_column=dge_egg_ppj2)
- [[contrasts/contrast_definition-egg-vs-pj2|Egg vs pJ2]] (log2_fold_change=5.8613, source_column=dge_egg_pj2)
- [[contrasts/contrast_definition-ppj2-vs-pj2|ppJ2 vs pJ2]] (log2_fold_change=4.2289, source_column=dge_ppj2_pj2)
- [[contrasts/contrast_definition-pj2-vs-j3|pJ2 vs J3]] (log2_fold_change=-1.0226, source_column=dge_pj2_j3)
- [[contrasts/contrast_definition-j3-vs-j4|J3 vs J4]] (log2_fold_change=-3.211, source_column=dge_j3_j4)
- [[contrasts/contrast_definition-j4-vs-f|J4 vs F]] (log2_fold_change=0.275, source_column=dge_j4_female)
- [[contrasts/contrast_definition-j4-vs-m|J4 vs M]] (log2_fold_change=1.7011, source_column=dge_j4_male)
- [[contrasts/contrast_definition-f-vs-m|F vs M]] (log2_fold_change=-1.4019, source_column=dge_female_male)

### HAS_EXPRESSION_SUMMARY

- [[expression/expression_measure-egg|Egg]] (expression_value=71.8461, source_column=avg_egg)
- [[expression/expression_measure-ppj2|ppJ2]] (expression_value=263.9098, source_column=avg_ppj2)
- [[expression/expression_measure-pj2|pJ2]] (expression_value=4589.1305, source_column=avg_pj2)
- [[expression/expression_measure-j3|J3]] (expression_value=2308.5427, source_column=avg_j3)
- [[expression/expression_measure-j4|J4]] (expression_value=246.7852, source_column=avg_j4)
- [[expression/expression_measure-female|Female]] (expression_value=296.221, source_column=avg_female)
- [[expression/expression_measure-male|Male]] (expression_value=865.7028, source_column=avg_male)

### HAS_TRANSCRIPT

- [[genes/hg_chrom2_tn10gene_3274|Hg_chrom2_TN10gene_3274]]

### TAGGED

- [[tags/tag-magenta|magenta]] (source_column=expression_bin_13)
- [[tags/tag-pink|pink]] (source_column=expression_bin_38)

### TRANSLATED_TO

- [[proteins/hg_chrom2_tn10mrna_3439-protein|10C01]]
