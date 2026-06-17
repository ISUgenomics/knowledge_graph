---
id: "contrast_definition:j4-vs-f"
type: "contrast_definition"
name: "J4 vs F"
---

# J4 vs F

## Properties

| Field | Value |
|---|---|
| category | contrast |
| contrast_order | 5 |
| label | J4 vs F |
| order_index | 5 |
| source_column | dge_j4_female |
| source_summary_column | avg_j4 |
| source_summary_label | J4 |
| target_summary_column | avg_female |
| target_summary_label | Female |

## Relationships

### CONTRAST_SOURCE

- [[expression/expression_measure-j4|J4]] (contrast_column=dge_j4_female, summary_column=avg_j4, summary_label=J4)

### CONTRAST_TARGET

- [[expression/expression_measure-female|Female]] (contrast_column=dge_j4_female, summary_column=avg_female, summary_label=Female)

### HAS_EXPRESSION_CONTRAST

- [[transcripts/hg_chrom1_tn10mrna_10|Hg_chrom1_TN10mRNA_10]] (log2_fold_change=-1.4222, source_column=dge_j4_female)
- [[transcripts/hg_chrom1_tn10mrna_100|Hg_chrom1_TN10mRNA_100]] (log2_fold_change=-2.0182, source_column=dge_j4_female)
- [[transcripts/hg_chrom1_tn10mrna_1000|Hg_chrom1_TN10mRNA_1000]] (log2_fold_change=1.7699, source_column=dge_j4_female)
- [[transcripts/hg_chrom1_tn10mrna_1001|Hg_chrom1_TN10mRNA_1001]] (log2_fold_change=-4.498, source_column=dge_j4_female)
- [[transcripts/hg_chrom1_tn10mrna_1002|Hg_chrom1_TN10mRNA_1002]] (log2_fold_change=-6.5721, source_column=dge_j4_female)
- [[transcripts/hg_chrom1_tn10mrna_1003|Hg_chrom1_TN10mRNA_1003]] (log2_fold_change=-0.3715, source_column=dge_j4_female)
- [[transcripts/hg_chrom1_tn10mrna_1004|Hg_chrom1_TN10mRNA_1004]] (log2_fold_change=1.2439, source_column=dge_j4_female)
- [[transcripts/hg_chrom1_tn10mrna_1005|Hg_chrom1_TN10mRNA_1005]] (log2_fold_change=1.2439, source_column=dge_j4_female)

### TAGGED

- [[tags/differential-expression|Differential Expression]] (source_column=dge_j4_female)
