from kgx.genomics_source import load_semantic_registry as load_genomics_registry
from kgx.people_source import load_semantic_registry as load_people_registry
from kgx.semantic_onboarding import describe_domain_template_coverage
from kgx.semantic_templates import (
    load_common_semantic_templates,
    load_domain_semantic_templates,
    load_domain_template_bindings,
    load_semantic_template_catalog,
)


def test_semantic_template_catalog_is_split_by_common_and_domain():
    catalog = load_semantic_template_catalog()

    assert set(catalog) == {"common", "people", "genomics"}
    assert "metadata_filter_family" in catalog["common"]
    assert "identity_record" in catalog["people"]
    assert "homology_evidence" in catalog["genomics"]


def test_common_semantic_templates_only_include_shared_patterns():
    templates = load_common_semantic_templates()

    assert "metadata_filter_family" in templates
    assert "contact_filter_family" in templates
    assert "measurement_filter_family" in templates
    assert "contrast_filter_family" in templates
    assert "identity_record" not in templates
    assert "homology_evidence" not in templates


def test_people_domain_templates_are_separate_from_genomics_templates():
    people = load_domain_semantic_templates("people")
    genomics = load_domain_semantic_templates("genomics")

    assert "identity_record" in people
    assert "affiliation_metadata" in people
    assert "relationship_authorship" in people
    assert "homology_evidence" not in people

    assert "homology_evidence" in genomics
    assert "orthology_membership" in genomics
    assert "horizontal_gene_transfer" in genomics
    assert "identity_record" not in genomics


def test_people_domain_template_bindings_reference_valid_domain_templates():
    templates = load_domain_semantic_templates("people")
    bindings = load_domain_template_bindings("people")

    assert set(bindings["categories"]) == {"people", "affiliation"}
    for bound_items in bindings["categories"].values():
        for item in bound_items:
            assert item["template_id"] in templates

    suggested_ids = {item["template_id"] for item in bindings["suggested"]}
    assert "contact_field" in suggested_ids
    assert "relationship_authorship" in suggested_ids


def test_genomics_domain_template_bindings_reference_valid_domain_templates():
    templates = load_domain_semantic_templates("genomics")
    bindings = load_domain_template_bindings("genomics")

    assert set(bindings["categories"]) == {"effectors", "homology", "orthology", "hgt"}
    for bound_items in bindings["categories"].values():
        for item in bound_items:
            assert item["template_id"] in templates

    suggested_ids = {item["template_id"] for item in bindings["suggested"]}
    assert "expression_measurement" in suggested_ids
    assert "dge_contrast" in suggested_ids
    assert "genomic_location" in suggested_ids
    assert "sequence_feature" in suggested_ids


def test_people_registry_exposes_split_template_catalog():
    registry = load_people_registry(None)

    assert "metadata_filter_family" in registry["common_templates"]
    assert "identity_record" in registry["domain_templates"]
    assert "identity_record" in registry["template_catalog"]["people"]
    assert "homology_evidence" in registry["template_catalog"]["genomics"]
    assert registry["template_bindings"]["categories"]["people"][0]["template_id"] == "identity_record"


def test_genomics_registry_exposes_split_template_catalog():
    registry = load_genomics_registry(None)

    assert "measurement_filter_family" in registry["common_templates"]
    assert "homology_evidence" in registry["domain_templates"]
    assert "identity_record" in registry["template_catalog"]["people"]
    assert "homology_evidence" in registry["template_catalog"]["genomics"]
    assert registry["template_bindings"]["categories"]["effectors"][0]["template_id"] == "effector_evidence"
    suggested_ids = {item["template_id"] for item in registry["template_bindings"]["suggested"]}
    assert "expression_measurement" in suggested_ids
    assert "dge_contrast" in suggested_ids


def test_people_domain_template_coverage_has_no_uncovered_templates():
    coverage = describe_domain_template_coverage("people")

    assert coverage["summary"]["uncovered"] == 0
    by_id = {item["template_id"]: item for item in coverage["templates"]}
    assert by_id["identity_record"]["coverage_kind"] == "bound_registry"
    assert by_id["contact_field"]["runtime_support"] == "generated_runtime"
    assert by_id["relationship_authorship"]["runtime_support"] == "generated_runtime"


def test_genomics_domain_template_coverage_has_no_uncovered_templates():
    coverage = describe_domain_template_coverage("genomics")

    assert coverage["summary"]["uncovered"] == 0
    by_id = {item["template_id"]: item for item in coverage["templates"]}
    assert by_id["homology_evidence"]["coverage_kind"] == "bound_registry"
    assert by_id["taxonomy_scope"]["coverage_kind"] == "bound_registry"
    assert by_id["expression_measurement"]["runtime_support"] == "generated_runtime"
    assert by_id["dge_contrast"]["runtime_support"] == "generated_runtime"
    assert by_id["genomic_location"]["runtime_support"] == "generated_runtime"
    assert by_id["sequence_feature"]["runtime_support"] == "generated_runtime"


def test_bound_template_categories_align_with_source_registry_categories():
    genomics = describe_domain_template_coverage("genomics")
    people = describe_domain_template_coverage("people")

    genomics_by_id = {item["template_id"]: item for item in genomics["templates"]}
    people_by_id = {item["template_id"]: item for item in people["templates"]}

    assert genomics_by_id["effector_evidence"]["bound_categories"] == ["effectors"]
    assert genomics_by_id["homology_evidence"]["bound_categories"] == ["homology"]
    assert genomics_by_id["taxonomy_scope"]["bound_categories"] == ["homology"]
    assert genomics_by_id["orthology_membership"]["bound_categories"] == ["orthology"]
    assert genomics_by_id["horizontal_gene_transfer"]["bound_categories"] == ["hgt"]
    assert people_by_id["identity_record"]["bound_categories"] == ["people"]
    assert people_by_id["affiliation_metadata"]["bound_categories"] == ["affiliation"]
