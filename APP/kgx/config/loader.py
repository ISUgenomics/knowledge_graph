"""
Configuration loader for Knowledge Graph Explorer.

Reads the default KGX config, merges with defaults, and validates with pydantic.
Creates the default config file on first run.
"""

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

DEFAULT_CONFIG_PATH = Path("config/default.yaml")


def _default_person_profile_url_templates() -> list[str]:
    domain = "iastate.edu"
    return [
        f"https://www.{domain}/directory/{{slug}}",
        f"https://www.{domain}/people/{{slug}}",
        f"https://www.bcb.{domain}/people/{{slug}}",
        f"https://www.biology.{domain}/people/{{slug}}",
        f"https://www.eeob.{domain}/people/{{slug}}",
        f"https://www.genetics.{domain}/people/{{slug}}",
        f"https://www.gdcb.{domain}/people/{{slug}}",
        f"https://www.bbmb.{domain}/people/{{slug}}",
        f"https://www.agron.{domain}/people/{{slug}}",
        f"https://www.ppem.{domain}/people/{{slug}}",
        f"https://www.micro.{domain}/people/{{slug}}",
        f"https://www.ans.{domain}/people/{{slug}}",
        f"https://www.fshn.{domain}/people/{{slug}}",
        f"https://www.hort.{domain}/people/{{slug}}",
        f"https://www.vdpam.{domain}/people/{{slug}}",
        f"https://www.nrem.{domain}/people/{{slug}}",
        f"https://www.cs.{domain}/people/{{slug}}",
        f"https://www.ece.{domain}/people/{{slug}}",
        f"https://www.me.{domain}/people/{{slug}}",
        f"https://www.abe.{domain}/people/{{slug}}",
        f"https://www.imse.{domain}/people/{{slug}}",
        f"https://www.engineering.{domain}/people/{{slug}}",
        f"https://www.aere.{domain}/directory/{{slug}}",
        f"https://www.ccee.{domain}/directory/{{slug}}",
        f"https://www.mse.{domain}/people/{{slug}}",
        f"https://www.datascience.{domain}/people/{{slug}}",
        f"https://www.aiira.{domain}/people/{{slug}}",
        f"https://www.chem.{domain}/people/{{slug}}",
        f"https://www.math.{domain}/people/{{slug}}",
        f"https://www.physics.{domain}/people/{{slug}}",
        f"https://www.stat.{domain}/people/{{slug}}",
        f"https://www.las.{domain}/people/{{slug}}",
        f"https://www.cals.{domain}/people/{{slug}}",
        f"https://www.cvm.{domain}/people/{{slug}}",
        f"https://www.extension.{domain}/people/{{slug}}",
        f"https://www.engl.{domain}/people/{{slug}}",
        f"https://www.soc.{domain}/people/{{slug}}",
        f"https://www.history.{domain}/directory/{{slug}}",
        f"https://www.ivybusiness.{domain}/directory/{{slug}}",
        f"https://www.biorenew.{domain}/people/{{slug}}",
        f"https://www.card.{domain}/people/{{slug}}",
        f"https://www.intrans.{domain}/people/{{slug}}",
    ]


def _default_person_staff_listing_urls() -> list[str]:
    return [
        "https://www.biotech.iastate.edu/staff/",
        "https://www.lib.iastate.edu/about-us/staff-directory",
        "https://trac-ai.iastate.edu/profiles/",
        "https://celt.iastate.edu/about/staff-directory/",
    ]


class DBConfig(BaseModel):
    path: str = "../../runtime_data/vault/vault.db"


class LLMConfig(BaseModel):
    provider: str = "ollama"
    base_url: str = "http://localhost:11434"
    model: str = "qwen3-coder:30b"
    fast_model: str | None = None
    temperature: float = 0.0


class SkillsConfig(BaseModel):
    enabled: bool = True
    directory: str = "../../skills"
    python: str = "python3"
    model: str = "qwen3-coder:30b"


class ServerConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8000
    cors_origins: list[str] = Field(default_factory=list)


class TimelineOrderRangeConfig(BaseModel):
    min: float | None = None
    max: float | None = None


class TimelineOrderConfig(BaseModel):
    field_candidates: list[str] = Field(default_factory=list)
    derive: list[str] = Field(default_factory=list)
    numeric_range: TimelineOrderRangeConfig = Field(default_factory=TimelineOrderRangeConfig)
    direction: str = "asc"


class TimelineAnchorsConfig(BaseModel):
    x_step: float = 140.0
    z: float = 0.0
    same_value_spread: str = "symmetric"
    same_value_y_step: float = 90.0


class TimelineAssignmentConfig(BaseModel):
    primary_anchor_rule: str = "strongest_then_earliest"
    edge_type_priority: list[str] = Field(default_factory=list)


class TimelineLayerConfig(BaseModel):
    mode: str = "soft"
    z: float = 0.0
    y_jitter: float = 0.0


class TimelineUnanchoredConfig(BaseModel):
    mode: str = "hide_or_dim"


class TimelineDetectionConfig(BaseModel):
    allow_anchor_type_override: bool = True
    allow_order_field_override: bool = True
    detected_type_min_count: int = 1


class TimelineLayoutConfig(BaseModel):
    enabled: bool = False
    profile_name: str = "default"
    anchor_type: str = ""
    featured_top_ids: list[str] = Field(default_factory=list)
    order: TimelineOrderConfig = Field(default_factory=TimelineOrderConfig)
    anchors: TimelineAnchorsConfig = Field(default_factory=TimelineAnchorsConfig)
    assignment: TimelineAssignmentConfig = Field(default_factory=TimelineAssignmentConfig)
    layers: dict[str, TimelineLayerConfig] = Field(default_factory=dict)
    unanchored: TimelineUnanchoredConfig = Field(default_factory=TimelineUnanchoredConfig)
    detection: TimelineDetectionConfig = Field(default_factory=TimelineDetectionConfig)


class HierarchyRelationClassesConfig(BaseModel):
    hierarchy: list[str] = Field(default_factory=lambda: ["BROADER", "PARENT_OF", "NARROWER", "CHILD_OF"])
    structural: list[str] = Field(default_factory=lambda: [
        "AUTHORED", "CREATED", "WROTE", "PUBLISHED", "PRODUCED",
        "PRESENTED", "ISSUED", "FILED", "FUNDED", "GRANTED",
    ])
    affiliation: list[str] = Field(default_factory=lambda: [
        "MEMBER_OF", "AFFILIATED_WITH", "BELONGS_TO", "WORKS_AT", "PART_OF",
    ])
    annotation: list[str] = Field(default_factory=lambda: [
        "TAGGED", "HAS_TAG", "ABOUT", "TOPIC", "KEYWORD", "MENTIONS",
    ])
    associative: list[str] = Field(default_factory=lambda: [
        "COAUTHOR", "RELATED", "SIMILAR", "CITES", "CITED", "COLLABORATOR",
    ])


class HierarchyBandsConfig(BaseModel):
    organization_y: float = 0.6
    person_y: float = 0.0
    publication_y: float = -0.65
    tag_core_y: float = -3.25
    tag_domain_y: float = -1.3
    tag_field_y: float = -1.95
    tag_topic_y: float = -2.6


class HierarchyLayoutConfig(BaseModel):
    enabled: bool = True
    profile_name: str = "default"
    relation_classes: HierarchyRelationClassesConfig = Field(default_factory=HierarchyRelationClassesConfig)
    type_families: dict[str, str] = Field(default_factory=dict)
    type_aliases: dict[str, str] = Field(default_factory=dict)
    type_levels: dict[str, float] = Field(default_factory=dict)
    driver_direction_overrides: dict[str, str] = Field(default_factory=dict)
    bands: HierarchyBandsConfig = Field(default_factory=HierarchyBandsConfig)
    annotation_driver_default: bool = True
    mediator_one_side_default: bool = False
    strict_bands_default: bool = False


class VisualizationTimelineContractConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preferred_anchor_types: list[str] = Field(default_factory=list)
    anchor_order_fields: dict[str, list[str]] = Field(default_factory=dict)
    field_aliases: dict[str, list[str]] = Field(default_factory=dict)
    weak_order_fields: list[str] = Field(default_factory=lambda: ["created_at", "updated_at", "pmid"])
    required_metadata_by_type: dict[str, list[str]] = Field(default_factory=dict)


class VisualizationHierarchyContractConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    relation_classes: HierarchyRelationClassesConfig = Field(default_factory=HierarchyRelationClassesConfig)
    type_families: dict[str, str] = Field(default_factory=dict)
    type_aliases: dict[str, str] = Field(default_factory=dict)
    type_levels: dict[str, float] = Field(default_factory=dict)
    driver_direction_overrides: dict[str, str] = Field(default_factory=dict)
    bands: HierarchyBandsConfig = Field(default_factory=HierarchyBandsConfig)
    annotation_driver_default: bool = True
    mediator_one_side_default: bool = False
    strict_bands_default: bool = False


class VisualizationBuildConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timeline: VisualizationTimelineContractConfig = Field(default_factory=VisualizationTimelineContractConfig)
    hierarchical: VisualizationHierarchyContractConfig = Field(default_factory=VisualizationHierarchyContractConfig)


class LayoutsConfig(BaseModel):
    timeline: TimelineLayoutConfig | None = None
    hierarchical: HierarchyLayoutConfig | None = None


class UIConfig(BaseModel):
    theme: str = "dark"
    default_layout: str = "force"
    node_size_by_degree: bool = True
    show_labels: bool = True
    max_visible_nodes: int = 5000
    edge_filters_default_visible: list[str] = Field(default_factory=list)  # empty = all visible
    detail_layout_source: str = ""
    semantic_registry_overlay: str = ""
    layouts: LayoutsConfig | None = Field(
        default_factory=lambda: LayoutsConfig(
            timeline=TimelineLayoutConfig(),
            hierarchical=HierarchyLayoutConfig(),
        )
    )


class ExploreConfig(BaseModel):
    """Configurable rules for Explore mode graph projection."""

    stub_type: str = ""
    stub_flag: str = "profiled"
    include_node_types: list[str] = Field(default_factory=list)
    include_rel_types: list[str] = Field(default_factory=list)
    include_rel_patterns: list[dict[str, Any]] = Field(default_factory=list)
    excluded_node_types: list[str] = Field(default_factory=list)
    preserve_node_types: list[str] = Field(default_factory=list)
    included_tag_roots: list[str] = Field(default_factory=list)
    mediator_type: str = ""
    mediator_edge: str = ""
    derived_edge_type: str = "RELATED"
    derived_path_edges: list[dict[str, Any]] = Field(default_factory=list)
    hierarchy_edge: str = ""
    annotation_edge: str = ""
    default_hidden_rel_types: list[str] = Field(default_factory=list)
    skipped_rel_types: list[str] = Field(default_factory=list)
    required_node_types_all: list[str] = Field(default_factory=list)
    required_node_types_any: list[str] = Field(default_factory=list)
    required_rel_types_all: list[str] = Field(default_factory=list)
    required_rel_types_any: list[str] = Field(default_factory=list)


class ExplorePresetConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str = ""
    description: str = ""
    include_node_types: list[str] | None = None
    include_rel_types: list[str] | None = None
    include_rel_patterns: list[dict[str, Any]] | None = None
    excluded_node_types: list[str] | None = None
    preserve_node_types: list[str] | None = None
    included_tag_roots: list[str] | None = None
    mediator_type: str | None = None
    mediator_edge: str | None = None
    derived_edge_type: str | None = None
    derived_path_edges: list[dict[str, Any]] | None = None
    hierarchy_edge: str | None = None
    annotation_edge: str | None = None
    default_hidden_rel_types: list[str] | None = None
    skipped_rel_types: list[str] | None = None
    required_node_types_all: list[str] | None = None
    required_node_types_any: list[str] | None = None
    required_rel_types_all: list[str] | None = None
    required_rel_types_any: list[str] | None = None


class ExploreModuleConfig(ExploreConfig):
    active_preset: str = ""
    presets: dict[str, ExplorePresetConfig] = Field(default_factory=dict)


class EmbeddingConfig(BaseModel):
    """Configurable text extraction for entity embeddings."""

    type_fields: dict[str, list[str]] = Field(default_factory=dict)
    default_fields: list[str] = Field(default_factory=lambda: ["title", "summary", "description"])
    max_field_length: int = 600
    skip_stub_type: str = ""
    skip_stub_flag: str = "profiled"


class DomainConfig(BaseModel):
    name: str = "default"


class SourcePolicyConfig(BaseModel):
    allowed_domains: list[str] = Field(default_factory=list)
    preferred_domains: list[str] = Field(default_factory=list)
    blocked_domains: list[str] = Field(default_factory=list)
    official_only: bool = False


class DBBuildSkillConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    help_prompts: list[str] = Field(default_factory=list)


class SkillContextConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    help_prompts: list[str] = Field(default_factory=list)
    settings: dict[str, Any] = Field(default_factory=dict)
    source_policy: SourcePolicyConfig | None = None


class PersonRoleProfileConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    allowed_roles: list[str] = Field(default_factory=lambda: ["faculty", "staff", "student"])
    faculty_titles: list[str] = Field(default_factory=lambda: [
        "Professor",
        "Associate Professor",
        "Assistant Professor",
        "Distinguished Professor",
        "University Professor",
        "Emeritus Professor",
    ])
    staff_title_keywords: list[str] = Field(default_factory=lambda: [
        "Manager",
        "Coordinator",
        "Specialist",
        "Technician",
        "Director",
        "Scientist",
    ])
    staff_department_keywords: list[str] = Field(default_factory=lambda: [
        "Facility",
        "Core",
        "Center",
        "Office of",
        "Institute",
    ])
    student_title_keywords: list[str] = Field(default_factory=lambda: [
        "Graduate Student",
        "PhD Candidate",
        "Postdoc",
        "Undergraduate Researcher",
    ])
    default_role: str = "staff"
    summary_target: str = "who they are and what they do at {institution_short}"
    role_instructions: dict[str, str] = Field(default_factory=dict)


class PersonAffiliationVerificationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    not_found_action: str = "skip"
    unavailable_action: str = "fallback"
    fallback_require_any: list[str] = Field(default_factory=lambda: [
        "department",
        "institutional_email",
        "profile_page",
    ])


class PersonSkillHelpPromptsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    person_research: list[str] = Field(default_factory=list)
    signal_capture: list[str] = Field(default_factory=list)
    event_research: list[str] = Field(default_factory=list)
    center_research: list[str] = Field(default_factory=list)


class PersonResearchExtensionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    institution: str = "Iowa State University"
    institution_short: str = "ISU"
    email_domain: str = "iastate.edu"
    require_kerberos: bool = True
    kerberos_principal_hint: str = "severin@IASTATE.EDU"
    ldap_server: str = "ldap://windc1.iastate.edu"
    ldap_base: str = "dc=iastate,dc=edu"
    directory_label: str = "LDAP"
    profile_label: str = "profile"
    employee_noun: str = "employee"
    employee_type_label: str = "Employee Type"
    directory_title_label: str = "Directory Title"
    directory_department_label: str = "Directory Department"
    directory_email_label: str = "Directory Email"
    api_base_url: str = ""
    laureates_dataset_url: str = ""
    source_snapshot_dir: str = ""
    filter_openalex_by_institution: bool = True
    filter_pubmed_by_institution: bool = True
    filter_orcid_by_institution: bool = True
    use_nobel_affiliation_for_scholarly_filters: bool = False
    profile_url_templates: list[str] = Field(default_factory=_default_person_profile_url_templates)
    staff_listing_urls: list[str] = Field(default_factory=_default_person_staff_listing_urls)
    source_policy: SourcePolicyConfig | None = None
    role_profile: PersonRoleProfileConfig | None = None
    affiliation_verification: PersonAffiliationVerificationConfig | None = None
    help_prompts: PersonSkillHelpPromptsConfig | None = None
    acknowledgements: "PersonResearchAcknowledgementsConfig | None" = None
    publication_harvest: "PersonResearchPublicationHarvestConfig | None" = None


class PersonResearchAcknowledgementTargetConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_id: str
    aliases: list[str] = Field(default_factory=list)


class PersonResearchAcknowledgementsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    relation_type: str = "ACKNOWLEDGES"
    seed_from_staff_authored_only: bool = True
    expand_to_collaborators: bool = False
    fetch_remote_text: bool = False
    prefer_open_access_sources: bool = True
    use_landing_page_text: bool = True
    use_europe_pmc: bool = True
    derive_targets_from_office_structure: bool = False
    source_snapshot_dir: str = ""
    debug_dir: str = ""
    min_match_confidence: str = "high"
    section_headings: list[str] = Field(
        default_factory=lambda: [
            "acknowledgements",
            "acknowledgments",
            "funding",
            "author contributions and acknowledgements",
        ]
    )
    targets: list[PersonResearchAcknowledgementTargetConfig] = Field(default_factory=list)


class PersonResearchPublicationHarvestConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_papers_per_person: int = 25
    max_total_papers: int = 300
    # If >= 1900, interpreted as an absolute earliest publication year.
    # If < 1900, interpreted as a rolling number of years back from now.
    not_older_than: int | None = 10


class PersonResearchConfig(DBBuildSkillConfig):
    extensions: list[str] = Field(default_factory=list)
    role_profile: PersonRoleProfileConfig = Field(default_factory=PersonRoleProfileConfig)
    affiliation_verification: PersonAffiliationVerificationConfig = Field(
        default_factory=PersonAffiliationVerificationConfig
    )


class SignalCaptureConfig(DBBuildSkillConfig):
    affiliation_profile: "AffiliationProfileConfig" = Field(default_factory=lambda: AffiliationProfileConfig())


class EventResearchConfig(DBBuildSkillConfig):
    affiliation_profile: "AffiliationProfileConfig" = Field(default_factory=lambda: AffiliationProfileConfig())


class CenterResearchConfig(DBBuildSkillConfig):
    affiliation_profile: "AffiliationProfileConfig" = Field(default_factory=lambda: AffiliationProfileConfig())


class AffiliationProfileConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    institution: str = ""
    flag_field: str = "affiliated"
    internal_label: str = "Internal"
    external_label: str = "External"
    internal_domain_keywords: list[str] = Field(default_factory=list)
    internal_org_keywords: list[str] = Field(default_factory=list)
    external_org_keywords: list[str] = Field(default_factory=list)
    default_affiliated: bool = False


class TagOntologyBuildConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    registry_path: str = ""
    aliases_path: str = ""
    hierarchy_path: str = ""
    apply_on_build: bool = False


class TagAnnotationEntityPolicyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    relationship_type: str = "TAGGED"
    default_category: str = "topic"


class PersonTagPromotionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    source_entity_type: str = "publication"
    source_relation_type: str = "AUTHORED"
    annotation_relation_type: str = "TAGGED"
    hierarchy_relation_type: str = "BROADER"
    min_support_count: int = 2
    include_ancestor_tags: bool = False
    max_tags_per_person: int = 0


class TaggingBuildConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ontology: TagOntologyBuildConfig = Field(default_factory=TagOntologyBuildConfig)
    entity_policies: dict[str, TagAnnotationEntityPolicyConfig] = Field(default_factory=dict)
    person_tag_promotion: PersonTagPromotionConfig = Field(default_factory=PersonTagPromotionConfig)


class DBBuildConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_policy: SourcePolicyConfig = Field(default_factory=SourcePolicyConfig)
    visualization: VisualizationBuildConfig = Field(default_factory=VisualizationBuildConfig)
    tagging: TaggingBuildConfig = Field(default_factory=TaggingBuildConfig)
    person_research: PersonResearchConfig = Field(default_factory=PersonResearchConfig)
    signal_capture: SignalCaptureConfig = Field(default_factory=SignalCaptureConfig)
    event_research: EventResearchConfig = Field(default_factory=EventResearchConfig)
    center_research: CenterResearchConfig = Field(default_factory=CenterResearchConfig)
    extensions: dict[str, PersonResearchExtensionConfig] = Field(default_factory=dict)
    skill_contexts: dict[str, SkillContextConfig] = Field(default_factory=dict)


class KGXConfig(BaseModel):
    db: DBConfig = Field(default_factory=DBConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    skills: SkillsConfig = Field(default_factory=SkillsConfig)
    server: ServerConfig = Field(default_factory=ServerConfig)
    ui: UIConfig = Field(default_factory=UIConfig)
    explore: ExploreModuleConfig = Field(default_factory=ExploreModuleConfig)
    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)
    domain: DomainConfig = Field(default_factory=DomainConfig)
    db_build: DBBuildConfig = Field(default_factory=DBBuildConfig)


_DEFAULT_YAML = """\
# Knowledge Graph Explorer configuration

domain:
  name: default

db:
  path: ../../runtime_data/vault/vault.db

llm:
  provider: ollama
  base_url: http://localhost:11434
  model: qwen3-coder:30b
  fast_model: null
  temperature: 0

skills:
  enabled: true
  directory: ../../skills
  python: python3
  model: qwen3-coder:30b

server:
  host: 127.0.0.1
  port: 8000
  cors_origins: []

ui:
  theme: dark
  default_layout: force
  node_size_by_degree: true
  show_labels: true
  max_visible_nodes: 5000
  edge_filters_default_visible: []   # empty = all visible
  layouts:
    timeline:
      enabled: false
      profile_name: default
      anchor_type: ""
      featured_top_ids: []
      order:
        field_candidates: []
        derive: []
        numeric_range:
          min: null
          max: null
        direction: asc
      anchors:
        x_step: 140
        z: 0
        same_value_spread: symmetric
        same_value_y_step: 90
      assignment:
        primary_anchor_rule: strongest_then_earliest
        edge_type_priority: []
      layers: {}
      unanchored:
        mode: hide_or_dim
      detection:
        allow_anchor_type_override: true
        allow_order_field_override: true
        detected_type_min_count: 1
    hierarchical:
      enabled: true
      profile_name: default

explore:
  stub_type: ""
  stub_flag: profiled
  excluded_node_types: []
  mediator_type: ""
  mediator_edge: ""
  derived_edge_type: RELATED
  hierarchy_edge: ""
  annotation_edge: ""
  skipped_rel_types: []

embedding:
  type_fields:
    award: [title, year, category, motivation]
    organization: [title, summary, country]
  default_fields: [title, summary, description]
  max_field_length: 600
  skip_stub_type: ""
  skip_stub_flag: profiled

db_build:
  source_policy:
    allowed_domains: []
    preferred_domains: []
    blocked_domains: []
    official_only: false
  visualization:
    timeline:
      preferred_anchor_types: []
      anchor_order_fields: {}
      field_aliases: {}
      weak_order_fields: [created_at, updated_at, pmid]
      required_metadata_by_type: {}
    hierarchical:
      relation_classes:
        hierarchy: [BROADER, PARENT_OF, NARROWER, CHILD_OF]
        structural: [AUTHORED, CREATED, WROTE, PUBLISHED, PRODUCED, PRESENTED, ISSUED, FILED, FUNDED, GRANTED]
        affiliation: [MEMBER_OF, AFFILIATED_WITH, BELONGS_TO, WORKS_AT, PART_OF]
        annotation: [TAGGED, HAS_TAG, ABOUT, TOPIC, KEYWORD, MENTIONS]
        associative: [COAUTHOR, RELATED, SIMILAR, CITES, CITED, COLLABORATOR]
      type_families: {}
      bands:
        organization_y: 0.6
        person_y: 0.0
        publication_y: -0.65
        tag_domain_y: -1.3
        tag_field_y: -1.95
        tag_topic_y: -2.6
      annotation_driver_default: true
      mediator_one_side_default: false
      strict_bands_default: false
  tagging:
    ontology:
      registry_path: ""
      aliases_path: ""
      hierarchy_path: ""
      apply_on_build: false
    entity_policies:
      person:
        enabled: true
        relationship_type: TAGGED
        default_category: topic
      publication:
        enabled: true
        relationship_type: TAGGED
        default_category: topic
    person_tag_promotion:
      enabled: false
      source_entity_type: publication
      source_relation_type: AUTHORED
      annotation_relation_type: TAGGED
      hierarchy_relation_type: BROADER
      min_support_count: 2
      include_ancestor_tags: false
      max_tags_per_person: 0
  person_research:
    enabled: false
    extensions: []
    role_profile:
      allowed_roles: [person]
      faculty_titles: []
      staff_title_keywords: []
      staff_department_keywords: []
      student_title_keywords: []
      default_role: staff
      summary_target: "who they are and what they do"
      role_instructions: {}
    affiliation_verification:
      not_found_action: skip
      unavailable_action: fallback
      fallback_require_any: [department, institutional_email, profile_page]
    help_prompts: []
  extensions:
    isu_profile:
      institution: Iowa State University
      institution_short: ISU
      email_domain: iastate.edu
      require_kerberos: true
      kerberos_principal_hint: severin@IASTATE.EDU
      ldap_server: ldap://windc1.iastate.edu
      ldap_base: dc=iastate,dc=edu
      directory_label: LDAP
      profile_label: profile
      employee_noun: employee
      employee_type_label: Employee Type
      directory_title_label: Directory Title
      directory_department_label: Directory Department
      directory_email_label: Directory Email
      profile_url_templates: []
      staff_listing_urls: []
      role_profile:
        allowed_roles: [faculty, staff, student]
        faculty_titles:
          - Professor
          - Associate Professor
          - Assistant Professor
          - Distinguished Professor
          - University Professor
          - Emeritus Professor
        staff_title_keywords:
          - Manager
          - Coordinator
          - Specialist
          - Technician
          - Director
          - Scientist
        staff_department_keywords:
          - Facility
          - Core
          - Center
          - Office of
          - Institute
        student_title_keywords:
          - Graduate Student
          - PhD Candidate
          - Postdoc
          - Undergraduate Researcher
        default_role: staff
        summary_target: "who they are and what they do at {institution_short}"
        role_instructions: {}
      affiliation_verification:
        not_found_action: skip
        unavailable_action: fallback
        fallback_require_any: [department, institutional_email, profile_page]
    noble_profile:
      institution: Nobel Prize
      institution_short: Nobel
      email_domain: nobelprize.org
      require_kerberos: false
      kerberos_principal_hint: ""
      ldap_server: ""
      ldap_base: ""
      directory_label: Nobel Prize Directory
      profile_label: laureate profile
      employee_noun: laureate
      employee_type_label: Prize Category
      directory_title_label: Laureate Title
      directory_department_label: Affiliation
      directory_email_label: Contact Email
      api_base_url: https://api.nobelprize.org/2.1
      laureates_dataset_url: https://api.nobelprize.org/2.1/laureates?limit=2000
      source_snapshot_dir: ../../sample_data/1_source/people_nobel/api
      filter_openalex_by_institution: false
      filter_pubmed_by_institution: false
      filter_orcid_by_institution: false
      use_nobel_affiliation_for_scholarly_filters: true
      profile_url_templates: []
      staff_listing_urls: []
      source_policy:
        allowed_domains:
          - api.nobelprize.org
          - nobelprize.org
          - api.openalex.org
          - pub.orcid.org
          - orcid.org
          - eutils.ncbi.nlm.nih.gov
          - pubmed.ncbi.nlm.nih.gov
        preferred_domains:
          - api.nobelprize.org
          - nobelprize.org
        blocked_domains: []
        official_only: true
      role_profile:
        allowed_roles: [laureate, scientist, writer, economist, activist]
        faculty_titles: []
        staff_title_keywords: []
        staff_department_keywords: []
        student_title_keywords: []
        default_role: laureate
        summary_target: "who they are and why they were recognized by {institution_short}"
        role_instructions:
          laureate: Use when the person is directly identified as a Nobel laureate or prize recipient.
          scientist: Use when the person is a scientific laureate and their active scholarly role matters more than the award label.
          writer: Use for literature laureates whose primary identity is authorship or literary work.
          economist: Use for economic sciences laureates when their economics identity is primary.
          activist: Use for peace laureates whose public role is civic, diplomatic, or activist rather than academic.
      affiliation_verification:
        not_found_action: fallback
        unavailable_action: fallback
        fallback_require_any: [profile_page]
  signal_capture:
    enabled: false
    help_prompts: []
  event_research:
    enabled: false
    help_prompts: []
  center_research:
    enabled: false
    help_prompts: []
"""


def _apply_visualization_defaults(config: KGXConfig, raw: dict[str, Any]) -> KGXConfig:
    """Let db_build.visualization provide layout defaults when UI profiles omit them."""
    ui_raw = (raw.get("ui") or {})
    layouts_raw = (ui_raw.get("layouts") or {})
    db_build_raw = (raw.get("db_build") or {})
    visualization_raw = (db_build_raw.get("visualization") or {})
    vis = config.db_build.visualization

    if config.ui.layouts is None:
        config.ui.layouts = LayoutsConfig()

    timeline_raw = (layouts_raw.get("timeline") or {})
    timeline_vis_raw = (visualization_raw.get("timeline") or {})
    if timeline_vis_raw:
        timeline_cfg = config.ui.layouts.timeline or TimelineLayoutConfig()
        if not timeline_raw.get("anchor_type"):
            preferred_anchor_types = vis.timeline.preferred_anchor_types
            if preferred_anchor_types:
                timeline_cfg.anchor_type = preferred_anchor_types[0]
        raw_order = (timeline_raw.get("order") or {})
        if not raw_order.get("field_candidates"):
            anchor_type = timeline_cfg.anchor_type or (vis.timeline.preferred_anchor_types[0] if vis.timeline.preferred_anchor_types else "")
            preferred_fields = (vis.timeline.anchor_order_fields or {}).get(anchor_type, [])
            if preferred_fields:
                timeline_cfg.order.field_candidates = preferred_fields
        config.ui.layouts.timeline = timeline_cfg

    hierarchical_raw = (layouts_raw.get("hierarchical") or {})
    hierarchy_vis_raw = (visualization_raw.get("hierarchical") or {})
    if hierarchy_vis_raw:
        hierarchy_cfg = config.ui.layouts.hierarchical or HierarchyLayoutConfig()
        if "relation_classes" not in hierarchical_raw:
            hierarchy_cfg.relation_classes = vis.hierarchical.relation_classes.model_copy(deep=True)
        if "type_families" not in hierarchical_raw:
            hierarchy_cfg.type_families = dict(vis.hierarchical.type_families)
        if "type_aliases" not in hierarchical_raw:
            hierarchy_cfg.type_aliases = dict(vis.hierarchical.type_aliases)
        if "type_levels" not in hierarchical_raw:
            hierarchy_cfg.type_levels = dict(vis.hierarchical.type_levels)
        if "driver_direction_overrides" not in hierarchical_raw:
            hierarchy_cfg.driver_direction_overrides = dict(vis.hierarchical.driver_direction_overrides)
        if "bands" not in hierarchical_raw:
            hierarchy_cfg.bands = vis.hierarchical.bands.model_copy(deep=True)
        if "annotation_driver_default" not in hierarchical_raw:
            hierarchy_cfg.annotation_driver_default = vis.hierarchical.annotation_driver_default
        if "mediator_one_side_default" not in hierarchical_raw:
            hierarchy_cfg.mediator_one_side_default = vis.hierarchical.mediator_one_side_default
        if "strict_bands_default" not in hierarchical_raw:
            hierarchy_cfg.strict_bands_default = vis.hierarchical.strict_bands_default
        config.ui.layouts.hierarchical = hierarchy_cfg

    return config


def _resolve_config_paths(config: KGXConfig, config_path: Path) -> KGXConfig:
    """Resolve relative db/skills paths relative to the config file location."""
    base_dir = config_path.resolve().parent

    db_path = Path(config.db.path)
    if not db_path.is_absolute():
        config.db.path = str((base_dir / db_path).resolve())

    skills_dir = Path(config.skills.directory)
    if not skills_dir.is_absolute():
        config.skills.directory = str((base_dir / skills_dir).resolve())

    return config


def load_config(path: Path | str | None = None) -> KGXConfig:
    """
    Load config from yaml file. Creates the default config file if not found.
    Path defaults to config/default.yaml in the current directory.
    """
    config_path = Path(path) if path else DEFAULT_CONFIG_PATH

    if not config_path.exists():
        config_path.write_text(_DEFAULT_YAML)
        print(f"Created default config: {config_path}")

    raw: dict[str, Any] = yaml.safe_load(config_path.read_text()) or {}
    config = KGXConfig(**raw)
    config = _apply_visualization_defaults(config, raw)
    return _resolve_config_paths(config, config_path)
