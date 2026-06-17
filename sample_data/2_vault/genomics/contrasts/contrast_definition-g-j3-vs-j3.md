---
id: "contrast_definition:g-j3-vs-j3"
type: "contrast_definition"
name: "G(J3) vs J3"
---

# G(J3) vs J3

## Properties

| Field | Value |
|---|---|
| category | contrast |
| contrast_order | 10 |
| label | G(J3) vs J3 |
| order_index | 10 |
| source_column | dge_j3g_j3b |
| source_summary_column | avg_j3 |
| source_summary_label | J3 |

## Relationships

### CONTRAST_SOURCE

- [[expression/expression_measure-j3|J3]] (contrast_column=dge_j3g_j3b, summary_column=avg_j3, summary_label=J3)

### HAS_EXPRESSION_CONTRAST

- [[transcripts/hg_chrom1_tn10mrna_10|Hg_chrom1_TN10mRNA_10]] (log2_fold_change=-5.4509, source_column=dge_j3g_j3b)
- [[transcripts/hg_chrom1_tn10mrna_1003|Hg_chrom1_TN10mRNA_1003]] (log2_fold_change=2.9626, source_column=dge_j3g_j3b)

### TAGGED

- [[tags/differential-expression|Differential Expression]] (source_column=dge_j3g_j3b)
