---
id: "contrast_definition:f-vs-m"
type: "contrast_definition"
name: "F vs M"
---

# F vs M

## Properties

| Field | Value |
|---|---|
| category | contrast |
| contrast_order | 7 |
| label | F vs M |
| order_index | 7 |
| source_column | dge_female_male |
| source_summary_column | avg_female |
| source_summary_label | Female |
| target_summary_column | avg_male |
| target_summary_label | Male |

## Relationships

### CONTRAST_SOURCE

- [[expression/expression_measure-female|Female]] (contrast_column=dge_female_male, summary_column=avg_female, summary_label=Female)

### CONTRAST_TARGET

- [[expression/expression_measure-male|Male]] (contrast_column=dge_female_male, summary_column=avg_male, summary_label=Male)

### HAS_EXPRESSION_CONTRAST

- [[transcripts/hg_chrom1_tn10mrna_1|Hg_chrom1_TN10mRNA_1]] (log2_fold_change=-0.4065, source_column=dge_female_male)
- [[transcripts/hg_chrom1_tn10mrna_1001|Hg_chrom1_TN10mRNA_1001]] (log2_fold_change=-2.5119, source_column=dge_female_male)
- [[transcripts/hg_chrom1_tn10mrna_1003|Hg_chrom1_TN10mRNA_1003]] (log2_fold_change=1.4933, source_column=dge_female_male)
- [[transcripts/hg_chrom1_tn10mrna_1004|Hg_chrom1_TN10mRNA_1004]] (log2_fold_change=1.5671, source_column=dge_female_male)
- [[transcripts/hg_chrom1_tn10mrna_1005|Hg_chrom1_TN10mRNA_1005]] (log2_fold_change=1.5671, source_column=dge_female_male)
- [[transcripts/hg_chrom4_tn10mrna_7223|Hg_chrom4_TN10mRNA_7223]] (log2_fold_change=-1.4472, source_column=dge_female_male)
- [[transcripts/hg_chrom2_tn10mrna_3439|Hg_chrom2_TN10mRNA_3439]] (log2_fold_change=-1.4019, source_column=dge_female_male)
- [[transcripts/hg_chrom2_tn10mrna_2403|Hg_chrom2_TN10mRNA_2403]] (log2_fold_change=1.8725, source_column=dge_female_male)

### TAGGED

- [[tags/differential-expression|Differential Expression]] (source_column=dge_female_male)
