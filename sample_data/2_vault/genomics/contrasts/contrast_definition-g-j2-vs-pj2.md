---
id: "contrast_definition:g-j2-vs-pj2"
type: "contrast_definition"
name: "G(J2) vs pJ2"
---

# G(J2) vs pJ2

## Properties

| Field | Value |
|---|---|
| category | contrast |
| contrast_order | 9 |
| label | G(J2) vs pJ2 |
| order_index | 9 |
| source_column | dge_j2g_pj2b |
| source_summary_column | avg_pj2 |
| source_summary_label | pJ2 |

## Relationships

### CONTRAST_SOURCE

- [[expression/expression_measure-pj2|pJ2]] (contrast_column=dge_j2g_pj2b, summary_column=avg_pj2, summary_label=pJ2)

### HAS_EXPRESSION_CONTRAST

- [[transcripts/hg_chrom1_tn10mrna_1|Hg_chrom1_TN10mRNA_1]] (log2_fold_change=4.8104, source_column=dge_j2g_pj2b)
- [[transcripts/hg_chrom1_tn10mrna_1000|Hg_chrom1_TN10mRNA_1000]] (log2_fold_change=5.3453, source_column=dge_j2g_pj2b)

### TAGGED

- [[tags/differential-expression|Differential Expression]] (source_column=dge_j2g_pj2b)
