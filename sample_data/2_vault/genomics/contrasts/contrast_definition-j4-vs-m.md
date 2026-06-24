---
id: "contrast_definition:j4-vs-m"
type: "contrast_definition"
name: "J4 vs M"
---

# J4 vs M

## Properties

| Field | Value |
|---|---|
| category | contrast |
| contrast_order | 6 |
| label | J4 vs M |
| order_index | 6 |
| source_column | dge_j4_male |
| source_summary_column | avg_j4 |
| source_summary_label | J4 |
| target_summary_column | avg_male |
| target_summary_label | Male |

## Relationships

### CONTRAST_SOURCE

- [[expression/expression_measure-j4|J4]] (contrast_column=dge_j4_male, summary_column=avg_j4, summary_label=J4)

### CONTRAST_TARGET

- [[expression/expression_measure-male|Male]] (contrast_column=dge_j4_male, summary_column=avg_male, summary_label=Male)

### HAS_EXPRESSION_CONTRAST

- [[transcripts/hg_chrom1_tn10mrna_1|Hg_chrom1_TN10mRNA_1]] (log2_fold_change=0.7969, source_column=dge_j4_male)
- [[transcripts/hg_chrom1_tn10mrna_100|Hg_chrom1_TN10mRNA_100]] (log2_fold_change=-2.4411, source_column=dge_j4_male)
- [[transcripts/hg_chrom1_tn10mrna_1000|Hg_chrom1_TN10mRNA_1000]] (log2_fold_change=1.564, source_column=dge_j4_male)
- [[transcripts/hg_chrom1_tn10mrna_1001|Hg_chrom1_TN10mRNA_1001]] (log2_fold_change=-1.964, source_column=dge_j4_male)
- [[transcripts/hg_chrom1_tn10mrna_1002|Hg_chrom1_TN10mRNA_1002]] (log2_fold_change=-5.2839, source_column=dge_j4_male)
- [[transcripts/hg_chrom1_tn10mrna_1003|Hg_chrom1_TN10mRNA_1003]] (log2_fold_change=-1.8363, source_column=dge_j4_male)
- [[transcripts/hg_chrom1_tn10mrna_1004|Hg_chrom1_TN10mRNA_1004]] (log2_fold_change=-0.2969, source_column=dge_j4_male)
- [[transcripts/hg_chrom1_tn10mrna_1005|Hg_chrom1_TN10mRNA_1005]] (log2_fold_change=-0.2969, source_column=dge_j4_male)
- [[transcripts/hg_chrom4_tn10mrna_7223|Hg_chrom4_TN10mRNA_7223]] (log2_fold_change=1.1603, source_column=dge_j4_male)
- [[transcripts/hg_chrom2_tn10mrna_3439|Hg_chrom2_TN10mRNA_3439]] (log2_fold_change=1.7011, source_column=dge_j4_male)
- [[transcripts/hg_chrom2_tn10mrna_2403|Hg_chrom2_TN10mRNA_2403]] (log2_fold_change=-0.9995, source_column=dge_j4_male)

### TAGGED

- [[tags/differential-expression|Differential Expression]] (source_column=dge_j4_male)
