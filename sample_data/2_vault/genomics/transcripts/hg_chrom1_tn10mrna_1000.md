---
id: "hg_chrom1_tn10mrna_1000"
type: "transcript"
name: "Hg_chrom1_TN10mRNA_1000"
---

# Hg_chrom1_TN10mRNA_1000

## Properties

| Field | Value |
|---|---|
| avg_counts | 30.4212 |
| avg_egg | 5.9128 |
| avg_female | 28.1817 |
| avg_glands | 45.1858 |
| avg_j2g | 0 |
| avg_j3 | 12.9133 |
| avg_j3g | 79.0752 |
| avg_j4 | 8.2757 |
| avg_male | 26.3548 |
| avg_pj2 | 22.4462 |
| avg_ppj2 | 39.9619 |
| cluster_name | 3-Not_described |
| cluster_score | 0.9862 |
| dge_egg_pj2 | 1.7901 |
| dge_egg_ppj2 | 2.5312 |
| dge_j2g_pj2b | 5.3453 |
| dge_j4_female | 1.7699 |
| dge_j4_male | 1.564 |
| dge_pj2_j3 | -0.8309 |
| dge_ppj2_pj2 | -0.7243 |
| expression_bin_13 | cyan |
| expression_bin_38 | grey |
| mrna_sequence | ATGAATGAGACCAATAGGCAAAATGTGTCTTCAAATGACCTATTAAATCCGTTTTACTCGTTTCTCTCCTCTTCCGGCTTTGTGCCTTTGCTGGTCATTCTGATCACTGTTCGTACtctgatcgcttccgttggcattgtgttgaatttgcttttggtttttgtcacaatatcaaatcgcaatttgcacggctccaccaatgttttgattgccattgactctctttCGCTTGCCATTTACCAATTCGGCTTTTTCCCTATGTTTTTCATCGTTTTGACTGGCCAAAATCTGATTCGCTTGGACCAGTGCTTTTGGCCAATGCTTCTCCCCGTTTTTTCTAAGAATGTTTCCTCCGCTTTGATGGTGGCCATCGGATTGGACCGACTTAAATTTGTCATTTCCCACGCATTTCTTCGCATCTCAAAAATATTTTACTGTTTTATGGCTTATTTTGTCTGCTCTTTTGGGGTTTCTATCCTTTCATTTAGCTATCGAATTATGCGACGAATTCCGCAAAATCTTGTGATGTGTGCCGCTTCGGAGGTCACTCAGCAAGAGGCGGCCTTTGTTTCCTTTTATTCAACTTTAATTCTGAACTGTGTGTCGCCTGCTGTGTATTGCGTTTTGGCAATTTGCTTATACGTCCGAAGGCCAAAAAACAACAACACTCAAAGTTTGTCTCTCAGTCAGCTGAGTCTGTTCCGCTCCATCTTCGTGCTGATGCTCCTCCAACTCCTCGGCTGGACTTCCAATTCCCTTTCGTTGTTTTTCTTCCAGAATTTGTTCGCCATCGCTTCGCTCTCCGATCTGACAAAATGGGCAATTAATTGTGTGTTCAGTTACATTTTGATCATCGCAACCGCAACCAATGGGCCCATTTTGTATTTTTGCAGTTTTGAATACAAAAAGCCATTCAAAAGCAATTCCGTGCATTTTGTCGAAGTATTGGCAACACCAACAGAAGCAAAAACTCGCGGGTGGTGGTGA |

## Relationships

### HAS_EXPRESSION_CONTRAST

- [[contrasts/contrast_definition-egg-vs-ppj2|Egg vs ppJ2]] (log2_fold_change=2.5312, source_column=dge_egg_ppj2)
- [[contrasts/contrast_definition-egg-vs-pj2|Egg vs pJ2]] (log2_fold_change=1.7901, source_column=dge_egg_pj2)
- [[contrasts/contrast_definition-ppj2-vs-pj2|ppJ2 vs pJ2]] (log2_fold_change=-0.7243, source_column=dge_ppj2_pj2)
- [[contrasts/contrast_definition-pj2-vs-j3|pJ2 vs J3]] (log2_fold_change=-0.8309, source_column=dge_pj2_j3)
- [[contrasts/contrast_definition-j4-vs-f|J4 vs F]] (log2_fold_change=1.7699, source_column=dge_j4_female)
- [[contrasts/contrast_definition-j4-vs-m|J4 vs M]] (log2_fold_change=1.564, source_column=dge_j4_male)
- [[contrasts/contrast_definition-g-j2-vs-pj2|G(J2) vs pJ2]] (log2_fold_change=5.3453, source_column=dge_j2g_pj2b)

### HAS_EXPRESSION_SUMMARY

- [[expression/expression_measure-egg|Egg]] (expression_value=5.9128, source_column=avg_egg)
- [[expression/expression_measure-ppj2|ppJ2]] (expression_value=39.9619, source_column=avg_ppj2)
- [[expression/expression_measure-pj2|pJ2]] (expression_value=22.4462, source_column=avg_pj2)
- [[expression/expression_measure-j3|J3]] (expression_value=12.9133, source_column=avg_j3)
- [[expression/expression_measure-j4|J4]] (expression_value=8.2757, source_column=avg_j4)
- [[expression/expression_measure-female|Female]] (expression_value=28.1817, source_column=avg_female)
- [[expression/expression_measure-male|Male]] (expression_value=26.3548, source_column=avg_male)

### HAS_TRANSCRIPT

- [[genes/hg_chrom1_tn10gene_956|Hg_chrom1_TN10gene_956]]

### TAGGED

- [[tags/tag-cyan|cyan]] (source_column=expression_bin_13)
- [[tags/tag-grey|grey]] (source_column=expression_bin_38)

### TRANSLATED_TO

- [[proteins/hg_chrom1_tn10mrna_1000-protein|Unknown_Hg_chrom1_TN10mRNA_1000]]
