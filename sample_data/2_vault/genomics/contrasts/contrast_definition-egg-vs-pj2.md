---
id: "contrast_definition:egg-vs-pj2"
type: "contrast_definition"
name: "Egg vs pJ2"
---

# Egg vs pJ2

## Properties

| Field | Value |
|---|---|
| category | contrast |
| contrast_order | 1 |
| label | Egg vs pJ2 |
| order_index | 1 |
| source_column | dge_egg_pj2 |
| source_summary_column | avg_egg |
| source_summary_label | Egg |
| target_summary_column | avg_pj2 |
| target_summary_label | pJ2 |

## Relationships

### CONTRAST_SOURCE

- [[expression/expression_measure-egg|Egg]] (contrast_column=dge_egg_pj2, summary_column=avg_egg, summary_label=Egg)

### CONTRAST_TARGET

- [[expression/expression_measure-pj2|pJ2]] (contrast_column=dge_egg_pj2, summary_column=avg_pj2, summary_label=pJ2)

### HAS_EXPRESSION_CONTRAST

- [[transcripts/hg_chrom1_tn10mrna_10|Hg_chrom1_TN10mRNA_10]] (log2_fold_change=-3.1626, source_column=dge_egg_pj2)
- [[transcripts/hg_chrom1_tn10mrna_1000|Hg_chrom1_TN10mRNA_1000]] (log2_fold_change=1.7901, source_column=dge_egg_pj2)
- [[transcripts/hg_chrom1_tn10mrna_1003|Hg_chrom1_TN10mRNA_1003]] (log2_fold_change=0.2818, source_column=dge_egg_pj2)
- [[transcripts/hg_chrom1_tn10mrna_1004|Hg_chrom1_TN10mRNA_1004]] (log2_fold_change=-1.3855, source_column=dge_egg_pj2)
- [[transcripts/hg_chrom1_tn10mrna_1005|Hg_chrom1_TN10mRNA_1005]] (log2_fold_change=-1.3855, source_column=dge_egg_pj2)
- [[transcripts/hg_chrom4_tn10mrna_7223|Hg_chrom4_TN10mRNA_7223]] (log2_fold_change=9.3714, source_column=dge_egg_pj2)
- [[transcripts/hg_chrom2_tn10mrna_3439|Hg_chrom2_TN10mRNA_3439]] (log2_fold_change=5.8613, source_column=dge_egg_pj2)
- [[transcripts/hg_chrom2_tn10mrna_2403|Hg_chrom2_TN10mRNA_2403]] (log2_fold_change=8.3849, source_column=dge_egg_pj2)

### TAGGED

- [[tags/differential-expression|Differential Expression]] (source_column=dge_egg_pj2)
