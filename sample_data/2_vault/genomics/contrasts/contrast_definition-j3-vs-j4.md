---
id: "contrast_definition:j3-vs-j4"
type: "contrast_definition"
name: "J3 vs J4"
---

# J3 vs J4

## Properties

| Field | Value |
|---|---|
| category | contrast |
| contrast_order | 4 |
| label | J3 vs J4 |
| order_index | 4 |
| source_column | dge_j3_j4 |
| source_summary_column | avg_j3 |
| source_summary_label | J3 |
| target_summary_column | avg_j4 |
| target_summary_label | J4 |

## Relationships

### CONTRAST_SOURCE

- [[expression/expression_measure-j3|J3]] (contrast_column=dge_j3_j4, summary_column=avg_j3, summary_label=J3)

### CONTRAST_TARGET

- [[expression/expression_measure-j4|J4]] (contrast_column=dge_j3_j4, summary_column=avg_j4, summary_label=J4)

### HAS_EXPRESSION_CONTRAST

- [[transcripts/hg_chrom1_tn10mrna_1|Hg_chrom1_TN10mRNA_1]] (log2_fold_change=-0.3497, source_column=dge_j3_j4)
- [[transcripts/hg_chrom1_tn10mrna_10|Hg_chrom1_TN10mRNA_10]] (log2_fold_change=4.9485, source_column=dge_j3_j4)
- [[transcripts/hg_chrom1_tn10mrna_100|Hg_chrom1_TN10mRNA_100]] (log2_fold_change=-1.0399, source_column=dge_j3_j4)
- [[transcripts/hg_chrom1_tn10mrna_1001|Hg_chrom1_TN10mRNA_1001]] (log2_fold_change=1.4484, source_column=dge_j3_j4)
- [[transcripts/hg_chrom1_tn10mrna_1003|Hg_chrom1_TN10mRNA_1003]] (log2_fold_change=0.2368, source_column=dge_j3_j4)

### TAGGED

- [[tags/differential-expression|Differential Expression]] (source_column=dge_j3_j4)
