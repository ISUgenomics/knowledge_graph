---
id: "expression_measure:female"
type: "expression_measure"
name: "Female"
---

# Female

## Properties

| Field | Value |
|---|---|
| category | summary |
| label | Female |
| order_index | 5 |
| source_column | avg_female |
| stage_order | 5 |

## Relationships

### CONTRAST_SOURCE

- [[contrasts/contrast_definition-f-vs-m|F vs M]] (contrast_column=dge_female_male, summary_column=avg_female, summary_label=Female)

### CONTRAST_TARGET

- [[contrasts/contrast_definition-j4-vs-f|J4 vs F]] (contrast_column=dge_j4_female, summary_column=avg_female, summary_label=Female)

### HAS_EXPRESSION_SUMMARY

- [[transcripts/hg_chrom1_tn10mrna_1|Hg_chrom1_TN10mRNA_1]] (expression_value=99.0782, source_column=avg_female)
- [[transcripts/hg_chrom1_tn10mrna_10|Hg_chrom1_TN10mRNA_10]] (expression_value=20.7878, source_column=avg_female)
- [[transcripts/hg_chrom1_tn10mrna_100|Hg_chrom1_TN10mRNA_100]] (expression_value=83.0169, source_column=avg_female)
- [[transcripts/hg_chrom1_tn10mrna_1000|Hg_chrom1_TN10mRNA_1000]] (expression_value=28.1817, source_column=avg_female)
- [[transcripts/hg_chrom1_tn10mrna_1001|Hg_chrom1_TN10mRNA_1001]] (expression_value=3.4408, source_column=avg_female)
- [[transcripts/hg_chrom1_tn10mrna_1002|Hg_chrom1_TN10mRNA_1002]] (expression_value=0, source_column=avg_female)
- [[transcripts/hg_chrom1_tn10mrna_1003|Hg_chrom1_TN10mRNA_1003]] (expression_value=2350.6527, source_column=avg_female)
- [[transcripts/hg_chrom1_tn10mrna_1004|Hg_chrom1_TN10mRNA_1004]] (expression_value=1163.0151, source_column=avg_female)
- [[transcripts/hg_chrom1_tn10mrna_1005|Hg_chrom1_TN10mRNA_1005]] (expression_value=1163.0151, source_column=avg_female)
- [[transcripts/hg_chrom4_tn10mrna_7223|Hg_chrom4_TN10mRNA_7223]] (expression_value=21.0771, source_column=avg_female)
- [[transcripts/hg_chrom2_tn10mrna_3439|Hg_chrom2_TN10mRNA_3439]] (expression_value=296.221, source_column=avg_female)
- [[transcripts/hg_chrom2_tn10mrna_2403|Hg_chrom2_TN10mRNA_2403]] (expression_value=436.364, source_column=avg_female)

### TAGGED

- [[tags/expression|Expression]] (source_column=avg_female)
