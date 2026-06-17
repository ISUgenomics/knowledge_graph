---
id: "hg_chrom1_tn10mrna_1001"
type: "transcript"
name: "Hg_chrom1_TN10mRNA_1001"
---

# Hg_chrom1_TN10mRNA_1001

## Properties

| Field | Value |
|---|---|
| avg_counts | 19.0088 |
| avg_egg | 4.557 |
| avg_female | 3.4408 |
| avg_glands | 13.0735 |
| avg_j2g | 0 |
| avg_j3 | 29.04 |
| avg_j3g | 22.8786 |
| avg_j4 | 78.2628 |
| avg_male | 21.7263 |
| avg_pj2 | 9.5258 |
| avg_ppj2 | 14.2069 |
| cluster_name | 26-J3_J4 |
| cluster_score | 0.9843 |
| dge_egg_ppj2 | 1.4016 |
| dge_female_male | -2.5119 |
| dge_j3_j4 | 1.4484 |
| dge_j4_female | -4.498 |
| dge_j4_male | -1.964 |
| dge_pj2_j3 | 1.5744 |
| expression_bin_13 | purple |
| expression_bin_38 | grey |
| mrna_sequence | ATGCGCTATTTTCACTTCCATCAATTTTTCATTGTTTTTTCGCTGAATTTTCTGAAAATAAAATCAAAGGAAAATGAAGAGCCGATTGGCCCACCGATTCGAAGCCGTCCCTCCGAAGTGATCGTTCATCTCCGTGCCAATTCCTACAACATCAGCGCATTTGTGCCAAACCACCCGGGCGGAGAATCCGTTCTTCGGCTGGTCAATGGTCAAGACATTGAGCAATACATTGAGGGACGAAAGTGCGTTTTGGGCATTTGCCATCGGCATCGATACGCTTATCAGGTGCTCAGACAATTCGAAATGCCTTCGGATGTTATCGTTGGGGTGAAGGGCAAATTTTACAACATCAGCGCATTTGTACCGGACCATCCGGGCGGGTCTTTTGTGCTCAGAGCGATCAACGGTCAGCAGAACGTGGAGCAGTACCTGGAGGGGCGAAAGTGCGTTTTTGGCATTTGCCACCGGCACGCCAACGCTTACGAAGTGCTCAGCCAATTGGAAATGTCCGGCTTAAACACCGCGCCGCCTCCTTCTACCGTAGTCCCTCCAACCGCCGTCCCTCCTACTGTCTTCCCCCATACCGTAATCGCCTCGTCTTTGTCCTCTTTCCCTTCCTTCGGCCATTTCCAAAATTCTTCTCTTTTAATTGTTCCGCATTTTCCCGGGACAAAAGTTaaagcacagcaaaggcaattagcacaagcattagccaagcaaagcgacaaaacaaaTGAAAACGAAAAAGAGGAGACAAATGAAGGGAAGCGAAACAATCGGACGGAATTGGCATTTGCCAATGATTTGCCAACGCAAAACGAAACAAAAGTGGACAAAGTATTAAAGGAAAAACAAATTGGAAAAGAAATGAAAGGAAAAGCGAAAGGAAAAGGAAAAGCGCCGAAAAGAAAAAACATTGAAACGACGACGGAGGAAAAGCAAAGGGACGGAAAAGGAAAAAGAAATGGGGGAAAAGAGAGGACAGAAGCCAAAGAAAAAGCGACGAACAGCAAAAAAGGAAATGAAAAGGGACGAAAAGCGAACGAAAAGCGAAAGGGGAGGAGGAAAAGCGGAGGAAAAGGGCAAAAAGTGAAACCAACGGACAATCAGCCGGAAAACGGACAAATGCTGAGGGGGGCGGATGCGCGGAAACGGAGGGTGCCGCTCTGTCTGTTCGTCAGACGGGCGGAAGAATCACCACACAATTACGAATGTGCTTGA |

## Relationships

### HAS_EXPRESSION_CONTRAST

- [[contrasts/contrast_definition-egg-vs-ppj2|Egg vs ppJ2]] (log2_fold_change=1.4016, source_column=dge_egg_ppj2)
- [[contrasts/contrast_definition-pj2-vs-j3|pJ2 vs J3]] (log2_fold_change=1.5744, source_column=dge_pj2_j3)
- [[contrasts/contrast_definition-j3-vs-j4|J3 vs J4]] (log2_fold_change=1.4484, source_column=dge_j3_j4)
- [[contrasts/contrast_definition-j4-vs-f|J4 vs F]] (log2_fold_change=-4.498, source_column=dge_j4_female)
- [[contrasts/contrast_definition-j4-vs-m|J4 vs M]] (log2_fold_change=-1.964, source_column=dge_j4_male)
- [[contrasts/contrast_definition-f-vs-m|F vs M]] (log2_fold_change=-2.5119, source_column=dge_female_male)

### HAS_EXPRESSION_SUMMARY

- [[expression/expression_measure-egg|Egg]] (expression_value=4.557, source_column=avg_egg)
- [[expression/expression_measure-ppj2|ppJ2]] (expression_value=14.2069, source_column=avg_ppj2)
- [[expression/expression_measure-pj2|pJ2]] (expression_value=9.5258, source_column=avg_pj2)
- [[expression/expression_measure-j3|J3]] (expression_value=29.04, source_column=avg_j3)
- [[expression/expression_measure-j4|J4]] (expression_value=78.2628, source_column=avg_j4)
- [[expression/expression_measure-female|Female]] (expression_value=3.4408, source_column=avg_female)
- [[expression/expression_measure-male|Male]] (expression_value=21.7263, source_column=avg_male)

### HAS_TRANSCRIPT

- [[genes/hg_chrom1_tn10gene_957|Hg_chrom1_TN10gene_957]]

### TAGGED

- [[tags/tag-purple|purple]] (source_column=expression_bin_13)
- [[tags/tag-grey|grey]] (source_column=expression_bin_38)

### TRANSLATED_TO

- [[proteins/hg_chrom1_tn10mrna_1001-protein|Hg_chrom1_TN10gene_957 protein]]
