---
id: "contrast_definition:egg-vs-ppj2"
type: "contrast_definition"
name: "Egg vs ppJ2"
---

# Egg vs ppJ2

## Properties

| Field | Value |
|---|---|
| category | contrast |
| contrast_order | 0 |
| label | Egg vs ppJ2 |
| order_index | 0 |
| source_column | dge_egg_ppj2 |
| source_summary_column | avg_egg |
| source_summary_label | Egg |
| target_summary_column | avg_ppj2 |
| target_summary_label | ppJ2 |

## Relationships

### CONTRAST_SOURCE

- [[expression/expression_measure-egg|Egg]] (contrast_column=dge_egg_ppj2, summary_column=avg_egg, summary_label=Egg)

### CONTRAST_TARGET

- [[expression/expression_measure-ppj2|ppJ2]] (contrast_column=dge_egg_ppj2, summary_column=avg_ppj2, summary_label=ppJ2)

### HAS_EXPRESSION_CONTRAST

- [[transcripts/hg_chrom1_tn10mrna_1|Hg_chrom1_TN10mRNA_1]] (log2_fold_change=0.516, source_column=dge_egg_ppj2)
- [[transcripts/hg_chrom1_tn10mrna_10|Hg_chrom1_TN10mRNA_10]] (log2_fold_change=-1.3014, source_column=dge_egg_ppj2)
- [[transcripts/hg_chrom1_tn10mrna_100|Hg_chrom1_TN10mRNA_100]] (log2_fold_change=1.0179, source_column=dge_egg_ppj2)
- [[transcripts/hg_chrom1_tn10mrna_1000|Hg_chrom1_TN10mRNA_1000]] (log2_fold_change=2.5312, source_column=dge_egg_ppj2)
- [[transcripts/hg_chrom1_tn10mrna_1001|Hg_chrom1_TN10mRNA_1001]] (log2_fold_change=1.4016, source_column=dge_egg_ppj2)
- [[transcripts/hg_chrom1_tn10mrna_1002|Hg_chrom1_TN10mRNA_1002]] (log2_fold_change=2.1838, source_column=dge_egg_ppj2)
- [[transcripts/hg_chrom1_tn10mrna_1003|Hg_chrom1_TN10mRNA_1003]] (log2_fold_change=0.6657, source_column=dge_egg_ppj2)
- [[transcripts/hg_chrom1_tn10mrna_1004|Hg_chrom1_TN10mRNA_1004]] (log2_fold_change=-1.0697, source_column=dge_egg_ppj2)
- [[transcripts/hg_chrom1_tn10mrna_1005|Hg_chrom1_TN10mRNA_1005]] (log2_fold_change=-1.0697, source_column=dge_egg_ppj2)
- [[transcripts/hg_chrom4_tn10mrna_7223|Hg_chrom4_TN10mRNA_7223]] (log2_fold_change=6.6057, source_column=dge_egg_ppj2)
- [[transcripts/hg_chrom2_tn10mrna_3439|Hg_chrom2_TN10mRNA_3439]] (log2_fold_change=1.6485, source_column=dge_egg_ppj2)
- [[transcripts/hg_chrom2_tn10mrna_2403|Hg_chrom2_TN10mRNA_2403]] (log2_fold_change=1.7212, source_column=dge_egg_ppj2)

### TAGGED

- [[tags/differential-expression|Differential Expression]] (source_column=dge_egg_ppj2)
