from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from kgx.llm.chat_sql import ChatToSQL


class ChatModule:
    def schema_context_lines(self, chat: "ChatToSQL") -> list[str]:
        return []

    def validation_error(self, chat: "ChatToSQL", sql: str, requested_types: list[str], message: str) -> str | None:
        return None

    def synthesize_query(self, chat: "ChatToSQL", message: str, sql: str, requested_types: list[str]) -> str | None:
        return None
