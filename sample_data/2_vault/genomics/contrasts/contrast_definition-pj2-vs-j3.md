---
id: "contrast_definition:pj2-vs-j3"
type: "contrast_definition"
name: "pJ2 vs J3"
---

# pJ2 vs J3

## Properties

| Field | Value |
|---|---|
| category | contrast |
| contrast_order | 3 |
| label | pJ2 vs J3 |
| order_index | 3 |
| source_column | dge_pj2_j3 |
| source_summary_column | avg_pj2 |
| source_summary_label | pJ2 |
| target_summary_column | avg_j3 |
| target_summary_label | J3 |

## Relationships

### CONTRAST_SOURCE

- [[expression/expression_measure-pj2|pJ2]] (contrast_column=dge_pj2_j3, summary_column=avg_pj2, summary_label=pJ2)

### CONTRAST_TARGET

- [[expression/expression_measure-j3|J3]] (contrast_column=dge_pj2_j3, summary_column=avg_j3, summary_label=J3)

### HAS_EXPRESSION_CONTRAST

- [[transcripts/hg_chrom1_tn10mrna_100|Hg_chrom1_TN10mRNA_100]] (log2_fold_change=2.2869, source_column=dge_pj2_j3)
- [[transcripts/hg_chrom1_tn10mrna_1000|Hg_chrom1_TN10mRNA_1000]] (log2_fold_change=-0.8309, source_column=dge_pj2_j3)
- [[transcripts/hg_chrom1_tn10mrna_1001|Hg_chrom1_TN10mRNA_1001]] (log2_fold_change=1.5744, source_column=dge_pj2_j3)
- [[transcripts/hg_chrom1_tn10mrna_1003|Hg_chrom1_TN10mRNA_1003]] (log2_fold_change=1.6025, source_column=dge_pj2_j3)
- [[transcripts/hg_chrom1_tn10mrna_1004|Hg_chrom1_TN10mRNA_1004]] (log2_fold_change=0.2018, source_column=dge_pj2_j3)
- [[transcripts/hg_chrom1_tn10mrna_1005|Hg_chrom1_TN10mRNA_1005]] (log2_fold_change=0.2018, source_column=dge_pj2_j3)

### TAGGED

- [[tags/differential-expression|Differential Expression]] (source_column=dge_pj2_j3)
