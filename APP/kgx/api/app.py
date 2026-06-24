"""
FastAPI app factory.

Each route module receives only the dependencies it needs.
No globals — everything is injected via create_app().
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from kgx.db import KnowledgeGraphDB
from kgx.domain_sources import (
    load_domain_detail_layouts,
    load_domain_semantic_registry,
    load_domain_semantic_schema,
)
from kgx.skills import SkillRegistry, SkillRunner

from .routes_graph import make_graph_router
from .routes_entity import make_entity_router
from .routes_query import make_query_router
from .routes_export import make_export_router
from .routes_chat import make_chat_router
from .routes_skills import make_skills_router
from .routes_watch import make_watch_router
from .routes_layout import make_layout_router

# UI static files live next to the api package
UI_DIR = Path(__file__).resolve().parent.parent / "ui"


def create_app(config: dict) -> FastAPI:
    """
    Build a fully wired FastAPI application.

    config keys:
      db_path   (str)  -- path to vault.db
      server    (dict) -- host, port, cors_origins
      ui        (dict) -- theme, etc.
    """
    # Database — single instance shared across all routes via dependency
    db = KnowledgeGraphDB(config["db_path"])
    llm_config = config.get("llm", {})
    domain_name = (config.get("domain") or {}).get("name")
    ui_config = config.get("ui", {})
    semantic_schema = load_domain_semantic_schema(domain_name, ui_config)
    semantic_registry = load_domain_semantic_registry(domain_name, ui_config)
    chat_router, llm_client = make_chat_router(db, llm_config, ui_config=ui_config, domain_name=domain_name)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        try:
            yield
        finally:
            db.close()
            llm_client.close()

    app = FastAPI(
        title="Knowledge Graph Explorer",
        description="Local-first knowledge graph explorer backed by SQLite.",
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS (defaults to localhost only)
    origins = config.get("server", {}).get("cors_origins", [])
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    # Store config subsets in app.state for routes that need it
    app.state.ui_config = ui_config
    app.state.detail_layouts = load_domain_detail_layouts(domain_name, app.state.ui_config)
    app.state.semantic_schema = semantic_schema
    app.state.semantic_registry = semantic_registry
    explore_config = config.get("explore", {})
    embedding_config = config.get("embedding", {})
    db_build_config = config.get("db_build", {})

    @app.get("/api/config")
    def get_config():
        ui_config = dict(app.state.ui_config)
        if app.state.detail_layouts:
            ui_config["detail_layouts"] = app.state.detail_layouts
        if app.state.semantic_schema:
            ui_config["semantic_schema"] = app.state.semantic_schema
        if app.state.semantic_registry:
            ui_config["semantic_registry"] = app.state.semantic_registry
        return {
            "db_path": config["db_path"],
            "ui": ui_config,
            "explore": explore_config,
            "embedding": embedding_config,
        }

    # Register route modules — each gets only what it needs
    app.include_router(make_graph_router(db, explore_config),  prefix="/api")
    app.include_router(make_entity_router(db, explore_config), prefix="/api")
    app.include_router(make_query_router(db),  prefix="/api")
    app.include_router(make_export_router(db), prefix="/api")
    app.include_router(chat_router, prefix="/api")

    skills_cfg = config.get("skills", {})
    db_build_cfg = db_build_config
    registry = SkillRegistry(skills_cfg.get("directory", "./skills"))
    runner = SkillRunner(python=skills_cfg.get("python", "python3"))
    app.include_router(make_skills_router(registry, runner, db_build_cfg, domain_name=domain_name), prefix="/api")
    app.include_router(make_watch_router(config["db_path"]), prefix="/api")
    app.include_router(
        make_layout_router(db, config.get("llm", {}), embedding_config, app.state.ui_config, db_build_config),
        prefix="/api",
    )

    # Serve UI static files at root (must be last — catches all unmatched routes)
    if UI_DIR.exists():
        app.mount("/", StaticFiles(directory=str(UI_DIR), html=True), name="ui")

    return app
