---
id: "expression_measure:j4"
type: "expression_measure"
name: "J4"
---

# J4

## Properties

| Field | Value |
|---|---|
| category | summary |
| label | J4 |
| order_index | 4 |
| source_column | avg_j4 |
| stage_order | 4 |

## Relationships

### CONTRAST_SOURCE

- [[contrasts/contrast_definition-j4-vs-m|J4 vs M]] (contrast_column=dge_j4_male, summary_column=avg_j4, summary_label=J4)
- [[contrasts/contrast_definition-j4-vs-f|J4 vs F]] (contrast_column=dge_j4_female, summary_column=avg_j4, summary_label=J4)

### CONTRAST_TARGET

- [[contrasts/contrast_definition-j3-vs-j4|J3 vs J4]] (contrast_column=dge_j3_j4, summary_column=avg_j4, summary_label=J4)

### HAS_EXPRESSION_SUMMARY

- [[transcripts/hg_chrom1_tn10mrna_1|Hg_chrom1_TN10mRNA_1]] (expression_value=77.6182, source_column=avg_j4)
- [[transcripts/hg_chrom1_tn10mrna_10|Hg_chrom1_TN10mRNA_10]] (expression_value=56.1002, source_column=avg_j4)
- [[transcripts/hg_chrom1_tn10mrna_100|Hg_chrom1_TN10mRNA_100]] (expression_value=336.799, source_column=avg_j4)
- [[transcripts/hg_chrom1_tn10mrna_1000|Hg_chrom1_TN10mRNA_1000]] (expression_value=8.2757, source_column=avg_j4)
- [[transcripts/hg_chrom1_tn10mrna_1001|Hg_chrom1_TN10mRNA_1001]] (expression_value=78.2628, source_column=avg_j4)
- [[transcripts/hg_chrom1_tn10mrna_1002|Hg_chrom1_TN10mRNA_1002]] (expression_value=5.3677, source_column=avg_j4)
- [[transcripts/hg_chrom1_tn10mrna_1003|Hg_chrom1_TN10mRNA_1003]] (expression_value=3059.7389, source_column=avg_j4)
- [[transcripts/hg_chrom1_tn10mrna_1004|Hg_chrom1_TN10mRNA_1004]] (expression_value=494.4395, source_column=avg_j4)
- [[transcripts/hg_chrom1_tn10mrna_1005|Hg_chrom1_TN10mRNA_1005]] (expression_value=494.4395, source_column=avg_j4)
- [[transcripts/hg_chrom4_tn10mrna_7223|Hg_chrom4_TN10mRNA_7223]] (expression_value=26.3638, source_column=avg_j4)
- [[transcripts/hg_chrom2_tn10mrna_3439|Hg_chrom2_TN10mRNA_3439]] (expression_value=246.7852, source_column=avg_j4)
- [[transcripts/hg_chrom2_tn10mrna_2403|Hg_chrom2_TN10mRNA_2403]] (expression_value=242.7982, source_column=avg_j4)

### TAGGED

- [[tags/expression|Expression]] (source_column=avg_j4)
