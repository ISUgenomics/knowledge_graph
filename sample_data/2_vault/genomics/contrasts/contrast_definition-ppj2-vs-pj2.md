---
id: "contrast_definition:ppj2-vs-pj2"
type: "contrast_definition"
name: "ppJ2 vs pJ2"
---

# ppJ2 vs pJ2

## Properties

| Field | Value |
|---|---|
| category | contrast |
| contrast_order | 2 |
| label | ppJ2 vs pJ2 |
| order_index | 2 |
| source_column | dge_ppj2_pj2 |
| source_summary_column | avg_ppj2 |
| source_summary_label | ppJ2 |
| target_summary_column | avg_pj2 |
| target_summary_label | pJ2 |

## Relationships

### CONTRAST_SOURCE

- [[expression/expression_measure-ppj2|ppJ2]] (contrast_column=dge_ppj2_pj2, summary_column=avg_ppj2, summary_label=ppJ2)

### CONTRAST_TARGET

- [[expression/expression_measure-pj2|pJ2]] (contrast_column=dge_ppj2_pj2, summary_column=avg_pj2, summary_label=pJ2)

### HAS_EXPRESSION_CONTRAST

- [[transcripts/hg_chrom1_tn10mrna_1|Hg_chrom1_TN10mRNA_1]] (log2_fold_change=-0.2712, source_column=dge_ppj2_pj2)
- [[transcripts/hg_chrom1_tn10mrna_100|Hg_chrom1_TN10mRNA_100]] (log2_fold_change=-0.8274, source_column=dge_ppj2_pj2)
- [[transcripts/hg_chrom1_tn10mrna_1000|Hg_chrom1_TN10mRNA_1000]] (log2_fold_change=-0.7243, source_column=dge_ppj2_pj2)
- [[transcripts/hg_chrom1_tn10mrna_1003|Hg_chrom1_TN10mRNA_1003]] (log2_fold_change=-0.368, source_column=dge_ppj2_pj2)
- [[transcripts/hg_chrom1_tn10mrna_1004|Hg_chrom1_TN10mRNA_1004]] (log2_fold_change=-0.2995, source_column=dge_ppj2_pj2)
- [[transcripts/hg_chrom1_tn10mrna_1005|Hg_chrom1_TN10mRNA_1005]] (log2_fold_change=-0.2995, source_column=dge_ppj2_pj2)
- [[transcripts/hg_chrom4_tn10mrna_7223|Hg_chrom4_TN10mRNA_7223]] (log2_fold_change=2.7822, source_column=dge_ppj2_pj2)
- [[transcripts/hg_chrom2_tn10mrna_3439|Hg_chrom2_TN10mRNA_3439]] (log2_fold_change=4.2289, source_column=dge_ppj2_pj2)
- [[transcripts/hg_chrom2_tn10mrna_2403|Hg_chrom2_TN10mRNA_2403]] (log2_fold_change=6.6851, source_column=dge_ppj2_pj2)

### TAGGED

- [[tags/differential-expression|Differential Expression]] (source_column=dge_ppj2_pj2)
