from kgx.genomics_source import load_detail_layouts, load_semantic_schema


def test_genomics_layouts_have_builtin_defaults_without_source():
    detail_layouts = load_detail_layouts({})

    assert "genomics_source_groups" in detail_layouts
    groups = detail_layouts["genomics_source_groups"]["groups"]
    assert groups[0]["id"] == "core"
    assert groups[1]["id"] == "genomics"
    effectors = next(group for group in groups if group["id"] == "effectors")
    assert any(field["key"] == "glycines_effectors_dna" for field in effectors["fields"])

    semantic_schema = load_semantic_schema({})
    assert semantic_schema["group_order"][0] == "core"
    assert "effectors" in semantic_schema["groups"]
    assert any(field["key"] == "schachtii_effectors_known" for field in semantic_schema["groups"]["effectors"]["fields"])


def test_genomics_layouts_merge_dataset_source_without_replacing_defaults():
    detail_layouts = load_detail_layouts({
        "detail_layout_source": "/workspace/KnowledgeGraph/sample_data/1_source/genomics_scn/config.py",
    })
    groups = detail_layouts["genomics_source_groups"]["groups"]

    genomics = next(group for group in groups if group["id"] == "genomics")
    effectors = next(group for group in groups if group["id"] == "effectors")

    assert any(field["key"] == "nested_genes" for field in genomics["fields"])
    assert any(field["key"] == "glycines_effectors_dna" and field["label"] == "SCN known (N)" for field in effectors["fields"])
