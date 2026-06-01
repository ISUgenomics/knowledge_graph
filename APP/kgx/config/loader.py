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


class KGXConfig(BaseModel):
    db: DBConfig = Field(default_factory=DBConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    skills: SkillsConfig = Field(default_factory=SkillsConfig)
    server: ServerConfig = Field(default_factory=ServerConfig)
    ui: UIConfig = Field(default_factory=UIConfig)


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
