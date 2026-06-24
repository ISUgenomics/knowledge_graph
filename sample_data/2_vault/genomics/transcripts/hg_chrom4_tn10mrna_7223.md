---
id: "hg_chrom4_tn10mrna_7223"
type: "transcript"
name: "Hg_chrom4_TN10mRNA_7223"
---

# Hg_chrom4_TN10mRNA_7223

## Properties

| Field | Value |
|---|---|
| avg_counts | 1163.9477 |
| avg_egg | 1.2211 |
| avg_female | 21.0771 |
| avg_glands | 2614.8347 |
| avg_j2g | 1601.6377 |
| avg_j3 | 233.3436 |
| avg_j3g | 3374.7324 |
| avg_j4 | 26.3638 |
| avg_male | 63.4159 |
| avg_pj2 | 891.6028 |
| avg_ppj2 | 139.8036 |
| cluster_name | 30-pJ2 |
| cluster_score | 1.000 |
| dge_egg_pj2 | 9.3714 |
| dge_egg_ppj2 | 6.6057 |
| dge_female_male | -1.4472 |
| dge_j3_j4 | -3.1319 |
| dge_j3g_j3b | -3.7169 |
| dge_j4_male | 1.1603 |
| dge_pj2_j3 | -1.9643 |
| dge_ppj2_pj2 | 2.7822 |
| expression_bin_13 | magenta |
| expression_bin_38 | pink |
| mrna_sequence | ATGCTGAGGATTGCTCTACTCATCTCCATTTTGGCACTGTTTGGTGATTGCATGGACAAGGGaaaaagaaaattaggaggaatcaGTATTAATGAGCCAAGTGAATATGGAACCAAAGAAAAAGAAGCCATCGCAACAAAAGAAAATGCACAAACATCAAAGGACCCGCCGACATCGGCGGGTGGTCAAAATGAAGCAATCCCTTCACCAAAAAAGCCAAGCCCCAAGGGGAAGTTGAAAAGCGATTTTGGCCTAAACTTAGCCAAGGCTTTTCCACGGCCGGTTCCGAAAGAGAAAAATGAAGAAAATGCACAGACCTCAAAGGTCCCGACATCGATGGAAGGGCAAAATGAACCAATCCCTTCACCAAAAAAGTCAAGCCCCAAGGGGAAGTCCAAAAGCGATTTCGCCCTAAACTTGGCCAAAGCTTTTCCACGACCGGTGCCGAAAGCAAAAATGGGAGAAGAAGCTCAGTCTTCAAAAGATCCGACAATGAATGGCCAAATTTGTGCAATTTGTTTGGATGCATCGCTTATCACTGACCTTGAATTGAGCAAATGCCATCATCGCTTTCACCGCGAATGCGTTGATGGGTGGTTTAAAAACAATGACACGTGCCCTTATTGTCGTGCTGTAGTTGCAAGCAGATATTTACCAAGACCTACGCGTACAGATCGAATTTTTGACGCCAGAATCGAAAACAAAAGACGCTTCATGGGAGAAGGAGAAGGAAAATACACAATTATTCGCCCTAACGGAAGTACGCTTATGGTTCACGATAATCATTTTGGAAACAATTTTACGGTCGAAAAAACTGAAGAGGGCTCCATTCAACTCAGTAAAAACGATCGCAAATAG |

## Relationships

### HAS_EXPRESSION_CONTRAST

- [[contrasts/contrast_definition-egg-vs-ppj2|Egg vs ppJ2]] (log2_fold_change=6.6057, source_column=dge_egg_ppj2)
- [[contrasts/contrast_definition-egg-vs-pj2|Egg vs pJ2]] (log2_fold_change=9.3714, source_column=dge_egg_pj2)
- [[contrasts/contrast_definition-ppj2-vs-pj2|ppJ2 vs pJ2]] (log2_fold_change=2.7822, source_column=dge_ppj2_pj2)
- [[contrasts/contrast_definition-pj2-vs-j3|pJ2 vs J3]] (log2_fold_change=-1.9643, source_column=dge_pj2_j3)
- [[contrasts/contrast_definition-j3-vs-j4|J3 vs J4]] (log2_fold_change=-3.1319, source_column=dge_j3_j4)
- [[contrasts/contrast_definition-j4-vs-m|J4 vs M]] (log2_fold_change=1.1603, source_column=dge_j4_male)
- [[contrasts/contrast_definition-f-vs-m|F vs M]] (log2_fold_change=-1.4472, source_column=dge_female_male)
- [[contrasts/contrast_definition-g-j3-vs-j3|G(J3) vs J3]] (log2_fold_change=-3.7169, source_column=dge_j3g_j3b)

### HAS_EXPRESSION_SUMMARY

- [[expression/expression_measure-egg|Egg]] (expression_value=1.2211, source_column=avg_egg)
- [[expression/expression_measure-ppj2|ppJ2]] (expression_value=139.8036, source_column=avg_ppj2)
- [[expression/expression_measure-pj2|pJ2]] (expression_value=891.6028, source_column=avg_pj2)
- [[expression/expression_measure-j3|J3]] (expression_value=233.3436, source_column=avg_j3)
- [[expression/expression_measure-j4|J4]] (expression_value=26.3638, source_column=avg_j4)
- [[expression/expression_measure-female|Female]] (expression_value=21.0771, source_column=avg_female)
- [[expression/expression_measure-male|Male]] (expression_value=63.4159, source_column=avg_male)

### HAS_TRANSCRIPT

- [[genes/hg_chrom4_tn10gene_6837|Hg_chrom4_TN10gene_6837]]

### TAGGED

- [[tags/tag-magenta|magenta]] (source_column=expression_bin_13)
- [[tags/tag-pink|pink]] (source_column=expression_bin_38)

### TRANSLATED_TO

- [[proteins/hg_chrom4_tn10mrna_7223-protein|10A06]]
