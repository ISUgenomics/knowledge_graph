"""
Query routes — /api/query (read-only SQL), /api/mutate/preview + /api/mutate/execute

Mutation safety model:
  1. Client POSTs to /api/mutate/preview → gets back {sql, preview, token}
  2. User sees a confirmation dialog in the UI
  3. Client POSTs to /api/mutate/execute with the token → executes

Tokens are single-use, stored in-memory (reset on server restart).
"""

import hashlib
import time
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from kgx.db import KnowledgeGraphDB


class QueryRequest(BaseModel):
    sql: str
    params: list[Any] = []


class MutatePreviewRequest(BaseModel):
    sql: str
    params: list[Any] = []


class MutateExecuteRequest(BaseModel):
    token: str


# In-memory pending mutations: token -> {sql, params, expires_at}
_pending: dict[str, dict] = {}
_TOKEN_TTL = 300  # seconds — token expires if not used


def _make_token(sql: str) -> str:
    return hashlib.sha256(f"{sql}{time.time()}".encode()).hexdigest()[:16]


def _prune_expired():
    now = time.time()
    expired = [t for t, v in _pending.items() if v["expires_at"] < now]
    for t in expired:
        del _pending[t]


def make_query_router(db: KnowledgeGraphDB) -> APIRouter:
    router = APIRouter(tags=["query"])

    @router.post("/query")
    def run_query(req: QueryRequest):
        """
        Execute a read-only SQL SELECT query.
        Returns results as a list of dicts.
        Rejects non-SELECT statements.
        """
        try:
            results = db.execute_read(req.sql, req.params or None)
            return {"results": results, "count": len(results), "sql": req.sql}
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Query error: {e}")

    @router.post("/mutate/preview")
    def mutate_preview(req: MutatePreviewRequest):
        """
        Preview a mutation. Returns a confirmation token.
        The token must be passed to /api/mutate/execute to apply.
        """
        sql = req.sql.strip()
        if sql.upper().startswith("SELECT"):
            raise HTTPException(status_code=400, detail="Use /api/query for SELECT statements.")

        _prune_expired()
        token = _make_token(sql)
        _pending[token] = {
            "sql": sql,
            "params": req.params,
            "expires_at": time.time() + _TOKEN_TTL,
        }

        # Estimate affected rows without executing
        try:
            preview_sql = f"SELECT COUNT(*) as n FROM ({_preview_query(sql)})"
            preview = db.execute_read(preview_sql)
            affected_estimate = preview[0]["n"] if preview else "unknown"
        except Exception:
            affected_estimate = "unknown"

        return {
            "token": token,
            "sql": sql,
            "affected_estimate": affected_estimate,
            "expires_in": _TOKEN_TTL,
            "message": "Send this token to /api/mutate/execute to confirm.",
        }

    @router.post("/mutate/execute")
    def mutate_execute(req: MutateExecuteRequest):
        """Execute a previewed mutation using the confirmation token."""
        _prune_expired()
        pending = _pending.pop(req.token, None)
        if not pending:
            raise HTTPException(
                status_code=400,
                detail="Invalid or expired token. Preview the mutation again."
            )

        try:
            rows_affected = db.execute_write(pending["sql"], pending["params"] or None)
            return {
                "success": True,
                "sql": pending["sql"],
                "rows_affected": rows_affected,
            }
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Mutation error: {e}")

    return router


_ALLOWED_TABLES = {"entities", "relationships", "aliases", "saved_views", "chat_history", "embeddings"}


def _preview_query(sql: str) -> str:
    """
    Build a count-only version of a mutation to estimate affected rows.
    Table name is validated against an allowlist to prevent injection.
    """
    upper = sql.upper()
    parts = sql.split()
    if "DELETE FROM" in upper and len(parts) >= 3:
        table = parts[2].strip(";").strip('"').strip("'")
        if table.lower() not in _ALLOWED_TABLES:
            return "SELECT 1"
        where = sql[upper.find("WHERE"):] if "WHERE" in upper else ""
        return f"SELECT * FROM {table} {where}"
    if upper.startswith("UPDATE") and len(parts) >= 2:
        table = parts[1].strip(";").strip('"').strip("'")
        if table.lower() not in _ALLOWED_TABLES:
            return "SELECT 1"
        where = sql[upper.find("WHERE"):] if "WHERE" in upper else ""
        return f"SELECT * FROM {table} {where}"
    return "SELECT 1"
