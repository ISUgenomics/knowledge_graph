from __future__ import annotations

from fastapi import APIRouter

from kgx.db import KnowledgeGraphDB
from kgx.semantic_onboarding import (
    extract_registry_patch_artifact,
    generate_domain_onboarding_artifact,
)


def make_semantic_router(
    db: KnowledgeGraphDB,
    *,
    domain_name: str | None = None,
    ui_config: dict | None = None,
    explore_config: dict | None = None,
    db_build_config: dict | None = None,
) -> APIRouter:
    router = APIRouter(tags=["semantic"])

    @router.get("/semantic/onboarding")
    def semantic_onboarding():
        return generate_domain_onboarding_artifact(
            domain_name,
            db,
            ui_config=ui_config or {},
            explore_config=explore_config or {},
            db_build_config=db_build_config or {},
        )

    @router.get("/semantic/patch")
    def semantic_patch():
        artifact = generate_domain_onboarding_artifact(
            domain_name,
            db,
            ui_config=ui_config or {},
            explore_config=explore_config or {},
            db_build_config=db_build_config or {},
        )
        return extract_registry_patch_artifact(artifact)

    return router
