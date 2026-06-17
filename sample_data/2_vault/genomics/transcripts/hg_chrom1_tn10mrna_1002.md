---
id: "hg_chrom1_tn10mrna_1002"
type: "transcript"
name: "Hg_chrom1_TN10mRNA_1002"
---

# Hg_chrom1_TN10mRNA_1002

## Properties

| Field | Value |
|---|---|
| avg_counts | 1.7653 |
| avg_egg | 0.928 |
| avg_female | 0 |
| avg_glands | 0.2203 |
| avg_j2g | 0.514 |
| avg_j3 | 4.7419 |
| avg_j3g | 0 |
| avg_j4 | 5.3677 |
| avg_male | 0.134 |
| avg_pj2 | 3.453 |
| avg_ppj2 | 4.943 |
| dge_egg_ppj2 | 2.1838 |
| dge_j4_female | -6.5721 |
| dge_j4_male | -5.2839 |
| expression_bin_38 | brown |
| mrna_sequence | ATGTTTTTTCTTTTCGGCGCTTTTCCTTTTCCTTTCGCTTTTCCTTTCATTTCTTTTCCAATTTGTTTTTCCTTTAATACTTTGTCCACTTTTGTTTCGTTTTGCGTTGGCAAATCATTGGCAAATGCCAATTCCGTCCGATTGTTTCGCTTCCCTTCATTTGTCTCCTCTTTTTCGTTTTCAtttgttttgtcgctttgcttggctaatgcttgtgctaattgcctttgctgtgctttAACTTTTGTCCCGGGAAAATGCGGAACAATTAAAAGAGAAGAATTTTGGAAATGGCCGAAGGAAGGGAAAGAGGACAAAGACGAGGCGATTACGGTACTGCTCCACGTTCTGCTGACCGTTGATCGCTCTGAGCACAAAAGACCCGCCCGGATGGTCCGGTACAAATGCGCTGATGTTGTAAAATTTGCCCTTCACCCCAACGATAACATCCGAAGGCATTTCGAATTGTCTGAGCACCTCAAAAGCAAGTTCCGGTGGGTCAGTCTCGAAAAAAGCAAAGATTCGCTAACAATAATCGGCTTTGGCATTTGTTCAACAAATTTGAGTCGTATCGATGCCGATGGCAAATGCCCAAAACGCACTTTCGTCCCTCAATGTATTGCTCAATGTCTTGACCATTGA |

## Relationships

### HAS_EXPRESSION_CONTRAST

- [[contrasts/contrast_definition-egg-vs-ppj2|Egg vs ppJ2]] (log2_fold_change=2.1838, source_column=dge_egg_ppj2)
- [[contrasts/contrast_definition-j4-vs-f|J4 vs F]] (log2_fold_change=-6.5721, source_column=dge_j4_female)
- [[contrasts/contrast_definition-j4-vs-m|J4 vs M]] (log2_fold_change=-5.2839, source_column=dge_j4_male)

### HAS_EXPRESSION_SUMMARY

- [[expression/expression_measure-egg|Egg]] (expression_value=0.928, source_column=avg_egg)
- [[expression/expression_measure-ppj2|ppJ2]] (expression_value=4.943, source_column=avg_ppj2)
- [[expression/expression_measure-pj2|pJ2]] (expression_value=3.453, source_column=avg_pj2)
- [[expression/expression_measure-j3|J3]] (expression_value=4.7419, source_column=avg_j3)
- [[expression/expression_measure-j4|J4]] (expression_value=5.3677, source_column=avg_j4)
- [[expression/expression_measure-female|Female]] (expression_value=0, source_column=avg_female)
- [[expression/expression_measure-male|Male]] (expression_value=0.134, source_column=avg_male)

### HAS_TRANSCRIPT

- [[genes/hg_chrom1_tn10gene_958|Hg_chrom1_TN10gene_958]]

### TAGGED

- [[tags/tag-brown|brown]] (source_column=expression_bin_38)

### TRANSLATED_TO

- [[proteins/hg_chrom1_tn10mrna_1002-protein|Hg_chrom1_TN10gene_958 protein]]
