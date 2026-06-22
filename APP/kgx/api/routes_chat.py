"""
Chat route — /api/chat

Accepts natural language, returns SQL results or a mutation token.
Requires Ollama running locally.
"""

from __future__ import annotations

import hashlib
import time

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from kgx.db import KnowledgeGraphDB
from kgx.llm import OllamaClient, ChatToSQL

# Re-use the same pending mutations dict from routes_query
# (imported so both routes share the same token store)
from kgx.api.routes_query import _pending, _TOKEN_TTL, _make_token, _prune_expired


class ChatRequest(BaseModel):
    message: str
    history: list[dict] = []


def make_chat_router(db: KnowledgeGraphDB, llm_config: dict) -> tuple:
    """Returns (router, llm_client) so app.py can close the client on shutdown."""
    router = APIRouter(tags=["chat"])

    # LLM client — instantiated once per app lifecycle
    llm = OllamaClient(
        base_url=llm_config.get("base_url", "http://localhost:11434"),
        model=llm_config.get("model", "qwen3-coder:30b"),
        temperature=llm_config.get("temperature", 0.0),
    )
    chat_sql = ChatToSQL(db, llm)

    @router.get("/chat/status")
    def chat_status():
        """Check whether Ollama is reachable and which model is configured."""
        return {
            "available": llm.is_available(),
            "model": llm.model,
            "base_url": llm.base_url,
        }

    @router.post("/chat")
    def chat(req: ChatRequest):
        """
        Translate natural language to SQL and return results.

        Returns:
          {intent, content, sql?, results?, token?, error?}

        - intent="query"    → SELECT was run; results[] included
        - intent="mutation" → DML detected; token included for /api/mutate/execute
        - intent="answer"   → plain text reply, no SQL
        """
        if not llm.is_available():
            raise HTTPException(
                status_code=503,
                detail=f"Ollama not reachable at {llm.base_url}. Start it with: ollama serve"
            )

        result = chat_sql.ask(req.message, req.history or None)

        response: dict = {
            "intent": result.intent,
            "content": result.content,
        }

        if result.error:
            response["error"] = result.error

        if result.sql:
            response["sql"] = result.sql

        if result.debug:
            response["debug"] = result.debug

        if result.intent == "query":
            response["results"] = result.results
            response["count"] = len(result.results)

        elif result.intent == "mutation" and result.sql:
            # Register a preview token so the UI can use the confirm dialog
            _prune_expired()
            token = _make_token(result.sql)
            _pending[token] = {
                "sql": result.sql,
                "params": [],
                "expires_at": time.time() + _TOKEN_TTL,
            }
            response["token"] = token
            response["expires_in"] = _TOKEN_TTL

        return response

    return router, llm
