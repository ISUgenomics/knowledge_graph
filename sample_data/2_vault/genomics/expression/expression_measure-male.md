---
id: "expression_measure:male"
type: "expression_measure"
name: "Male"
---

# Male

## Properties

| Field | Value |
|---|---|
| category | summary |
| label | Male |
| order_index | 6 |
| source_column | avg_male |
| stage_order | 6 |

## Relationships

### CONTRAST_TARGET

- [[contrasts/contrast_definition-j4-vs-m|J4 vs M]] (contrast_column=dge_j4_male, summary_column=avg_male, summary_label=Male)
- [[contrasts/contrast_definition-f-vs-m|F vs M]] (contrast_column=dge_female_male, summary_column=avg_male, summary_label=Male)

### HAS_EXPRESSION_SUMMARY

- [[transcripts/hg_chrom1_tn10mrna_1|Hg_chrom1_TN10mRNA_1]] (expression_value=145.0865, source_column=avg_male)
- [[transcripts/hg_chrom1_tn10mrna_10|Hg_chrom1_TN10mRNA_10]] (expression_value=32.8574, source_column=avg_male)
- [[transcripts/hg_chrom1_tn10mrna_100|Hg_chrom1_TN10mRNA_100]] (expression_value=66.6529, source_column=avg_male)
- [[transcripts/hg_chrom1_tn10mrna_1000|Hg_chrom1_TN10mRNA_1000]] (expression_value=26.3548, source_column=avg_male)
- [[transcripts/hg_chrom1_tn10mrna_1001|Hg_chrom1_TN10mRNA_1001]] (expression_value=21.7263, source_column=avg_male)
- [[transcripts/hg_chrom1_tn10mrna_1002|Hg_chrom1_TN10mRNA_1002]] (expression_value=0.134, source_column=avg_male)
- [[transcripts/hg_chrom1_tn10mrna_1003|Hg_chrom1_TN10mRNA_1003]] (expression_value=920.7134, source_column=avg_male)
- [[transcripts/hg_chrom1_tn10mrna_1004|Hg_chrom1_TN10mRNA_1004]] (expression_value=433.2653, source_column=avg_male)
- [[transcripts/hg_chrom1_tn10mrna_1005|Hg_chrom1_TN10mRNA_1005]] (expression_value=433.2653, source_column=avg_male)

### TAGGED

- [[tags/expression|Expression]] (source_column=avg_male)
