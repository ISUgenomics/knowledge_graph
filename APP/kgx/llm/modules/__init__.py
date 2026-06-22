from .base import ChatModule
from .default import DefaultChatModule
from .genomics import GenomicsChatModule
from .people import PeopleChatModule


def get_chat_module(domain_name: str | None) -> ChatModule:
    name = str(domain_name or "").strip().lower()
    if name == "genomics":
        return GenomicsChatModule()
    if name == "people":
        return PeopleChatModule()
    return DefaultChatModule()


__all__ = ["ChatModule", "DefaultChatModule", "GenomicsChatModule", "PeopleChatModule", "get_chat_module"]
