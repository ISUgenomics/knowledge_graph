"""
Configuration loader for Knowledge Graph Explorer.

Reads config.yaml, merges with defaults, validates with pydantic.
Creates a default config.yaml on first run.
"""

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

DEFAULT_CONFIG_PATH = Path("config.yaml")


class DBConfig(BaseModel):
    path: str = "./vault.db"


class LLMConfig(BaseModel):
    provider: str = "ollama"
    base_url: str = "http://localhost:11434"
    model: str = "qwen3-coder:30b"
    fast_model: str | None = None
    temperature: float = 0.0


class SkillsConfig(BaseModel):
    enabled: bool = True
    directory: str = "../skills"
    python: str = "python3"
    model: str = "qwen3-coder:30b"


class ServerConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8000
    cors_origins: list[str] = Field(default_factory=list)


class UIConfig(BaseModel):
    theme: str = "dark"
    default_layout: str = "force"
    node_size_by_degree: bool = True
    show_labels: bool = True
    max_visible_nodes: int = 5000
    edge_filters_default_visible: list[str] = Field(default_factory=list)  # empty = all visible


class ExploreConfig(BaseModel):
    """Configurable conventions for Explore mode graph projection.
    Set any string field to "" to disable that transformation."""
    # Stub filtering: entities of this type without this metadata flag are excluded
    stub_type: str = ""               # e.g. "person" — empty to disable
    stub_flag: str = "profiled"       # metadata key that marks non-stubs
    # Entity types to exclude entirely from explore view
    exclude_types: list[str] = Field(default_factory=list)  # e.g. ["publication"]
    # Collaboration synthesis: co-occurrence on a shared entity type
    collaboration_via_type: str = ""   # e.g. "publication" — empty to disable
    collaboration_via_edge: str = ""   # e.g. "AUTHORED"
    collaboration_label: str = "COLLABORATOR"
    # Tag hierarchy flattening
    hierarchy_edge: str = ""           # e.g. "BROADER" — empty to disable
    tagging_edge: str = ""             # e.g. "TAGGED" — empty to disable
    # Relationship types to skip in explore (replaced by synthetic edges)
    skip_rel_types: list[str] = Field(default_factory=list)


class EmbeddingConfig(BaseModel):
    """Configurable text extraction for entity embeddings."""
    # Per-type metadata fields to include (order matters)
    type_fields: dict[str, list[str]] = Field(default_factory=dict)
    # Fallback fields for types not in type_fields
    default_fields: list[str] = Field(default_factory=lambda: ["title", "summary", "description"])
    # Max characters for any single field value
    max_field_length: int = 600
    # Skip stub entities (entities of stub_type without stub_flag)
    skip_stub_type: str = ""           # e.g. "person" — empty to disable
    skip_stub_flag: str = "profiled"


class KGXConfig(BaseModel):
    db: DBConfig = Field(default_factory=DBConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    skills: SkillsConfig = Field(default_factory=SkillsConfig)
    server: ServerConfig = Field(default_factory=ServerConfig)
    ui: UIConfig = Field(default_factory=UIConfig)
    explore: ExploreConfig = Field(default_factory=ExploreConfig)
    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)


_DEFAULT_YAML = """\
# Knowledge Graph Explorer configuration

db:
  path: ./vault.db

llm:
  provider: ollama
  base_url: http://localhost:11434
  model: qwen3-coder:30b
  fast_model: null
  temperature: 0

skills:
  enabled: true
  directory: ../skills
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

# Explore mode conventions — set string values to "" to disable a transformation.
# All fields are optional; when empty, explore mode shows the raw graph.
explore:
  stub_type: ""                  # entity type that has stubs (e.g. "person")
  stub_flag: profiled            # metadata key marking non-stubs
  exclude_types: []              # entity types to exclude (e.g. ["publication"])
  collaboration_via_type: ""     # entity type mediating collaboration (e.g. "publication")
  collaboration_via_edge: ""     # rel type connecting collaborators to mediator (e.g. "AUTHORED")
  collaboration_label: COLLABORATOR
  hierarchy_edge: ""             # rel type for tag hierarchy (e.g. "BROADER")
  tagging_edge: ""               # rel type for tagging (e.g. "TAGGED")
  skip_rel_types: []             # rel types to exclude (e.g. ["AUTHORED", "COAUTHOR", "BROADER"])

# Embedding text extraction — which metadata fields to use per entity type.
embedding:
  type_fields: {}                # e.g. {person: [title, institution, department, summary]}
  default_fields: [title, summary, description]
  max_field_length: 600
  skip_stub_type: ""             # skip stubs of this type (e.g. "person")
  skip_stub_flag: profiled
"""


def load_config(path: Path | str | None = None) -> KGXConfig:
    """
    Load config from yaml file. Creates default config.yaml if not found.
    Path defaults to config.yaml in the current directory.
    """
    config_path = Path(path) if path else DEFAULT_CONFIG_PATH

    if not config_path.exists():
        config_path.write_text(_DEFAULT_YAML)
        print(f"Created default config: {config_path}")

    raw: dict[str, Any] = yaml.safe_load(config_path.read_text()) or {}
    return KGXConfig(**raw)
