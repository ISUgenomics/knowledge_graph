from kgx.domain_sources import load_domain_semantic_registry, load_domain_semantic_schema

from .base import ChatModule
from .default import DefaultChatModule
from .genomics import GenomicsChatModule
from .people import PeopleChatModule


def get_chat_module(domain_name: str | None, ui_config: dict | None = None) -> ChatModule:
    name = str(domain_name or "").strip().lower()
    if name == "genomics":
        return GenomicsChatModule(
            semantic_schema=load_domain_semantic_schema(name, ui_config),
            semantic_registry=load_domain_semantic_registry(name, ui_config),
        )
    if name == "people":
        return PeopleChatModule(
            semantic_schema=load_domain_semantic_schema(name, ui_config),
            semantic_registry=load_domain_semantic_registry(name, ui_config),
        )
    return DefaultChatModule()


__all__ = ["ChatModule", "DefaultChatModule", "GenomicsChatModule", "PeopleChatModule", "get_chat_module"]
