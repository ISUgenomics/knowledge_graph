---
id: "contrast_definition:g-j3-vs-j2"
type: "contrast_definition"
name: "G(J3 vs J2)"
---

# G(J3 vs J2)

## Properties

| Field | Value |
|---|---|
| category | contrast |
| contrast_order | 8 |
| label | G(J3 vs J2) |
| order_index | 8 |
| source_column | dge_j3g_j2g |
| source_summary_column | avg_j3 |
| source_summary_label | J3 |
| target_summary_column | avg_pj2 |
| target_summary_label | pJ2 |

## Relationships

### CONTRAST_SOURCE

- [[expression/expression_measure-j3|J3]] (contrast_column=dge_j3g_j2g, summary_column=avg_j3, summary_label=J3)

### CONTRAST_TARGET

- [[expression/expression_measure-pj2|pJ2]] (contrast_column=dge_j3g_j2g, summary_column=avg_pj2, summary_label=pJ2)

### HAS_EXPRESSION_CONTRAST

- [[transcripts/hg_chrom1_tn10mrna_10|Hg_chrom1_TN10mRNA_10]] (log2_fold_change=-7.1967, source_column=dge_j3g_j2g)
- [[transcripts/hg_chrom1_tn10mrna_100|Hg_chrom1_TN10mRNA_100]] (log2_fold_change=-5.5265, source_column=dge_j3g_j2g)
- [[transcripts/hg_chrom2_tn10mrna_2403|Hg_chrom2_TN10mRNA_2403]] (log2_fold_change=-3.8652, source_column=dge_j3g_j2g)

### TAGGED

- [[tags/differential-expression|Differential Expression]] (source_column=dge_j3g_j2g)
