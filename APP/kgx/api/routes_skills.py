"""
Skill routes — /api/skill/*

GET  /api/skill/list                  — list available skills (+ filter by entity_type)
POST /api/skill/run                   — start a skill job, returns job_id
GET  /api/skill/job/{job_id}          — get job status + output lines
GET  /api/skill/stream/{job_id}       — SSE stream of job output (EventSource)
"""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from kgx.skills import SkillRegistry, SkillRunner


class RunRequest(BaseModel):
    skill_id: str
    args: list[str] = []


def make_skills_router(
    registry: SkillRegistry,
    runner: SkillRunner,
    db_build: dict | None = None,
    domain_name: str | None = None,
) -> APIRouter:
    router = APIRouter(tags=["skills"])
    db_build = db_build or {}
    domain_name = str(domain_name or "").strip().lower()

    def _selected_person_extensions() -> list[str]:
        person_cfg = db_build.get("person_research", {}) or {}
        return list(person_cfg.get("extensions", []) or [])

    def _resolved_source_policy(skill_id: str) -> dict:
        source_policy = dict(db_build.get("source_policy", {}) or {})
        skill_context = ((db_build.get("skill_contexts", {}) or {}).get(skill_id, {}) or {})
        for extension_name in _selected_person_extensions():
            extension_cfg = (db_build.get("extensions", {}) or {}).get(extension_name, {}) or {}
            extension_source_policy = extension_cfg.get("source_policy")
            if extension_source_policy:
                source_policy.update(extension_source_policy)
        context_source_policy = skill_context.get("source_policy")
        if context_source_policy:
            source_policy.update(context_source_policy)
        return source_policy

    def _resolved_help_prompts(skill_id: str, skill_cfg: dict) -> list[str]:
        help_prompts = list(skill_cfg.get("help_prompts", []) or [])
        skill_context = ((db_build.get("skill_contexts", {}) or {}).get(skill_id, {}) or {})
        context_prompts = list(skill_context.get("help_prompts", []) or [])
        if context_prompts:
            help_prompts.extend(context_prompts)
        for extension_name in _selected_person_extensions():
            extension_cfg = (db_build.get("extensions", {}) or {}).get(extension_name, {}) or {}
            extension_prompts = (extension_cfg.get("help_prompts", {}) or {}).get(skill_id, [])
            if extension_prompts:
                help_prompts.extend(extension_prompts)
        return help_prompts

    # In-memory SSE queues: job_id -> asyncio.Queue
    _sse_queues: dict[str, asyncio.Queue] = {}

    @router.get("/skill/list")
    def skill_list(entity_type: str = ""):
        return {"skills": [s.to_dict() for s in registry.list(entity_type, module_name=domain_name)]}

    @router.get("/skill/help/{skill_id}")
    def skill_help(skill_id: str):
        skill = registry.get(skill_id)
        if not skill:
            raise HTTPException(status_code=404, detail=f"Skill '{skill_id}' not found")

        skill_cfg = db_build.get(skill_id, {}) or {}
        settings = {k: v for k, v in skill_cfg.items() if k not in {"help_prompts"}}
        skill_context = ((db_build.get("skill_contexts", {}) or {}).get(skill_id, {}) or {})
        if skill_context.get("settings"):
            settings = {
                **dict(skill_context.get("settings", {}) or {}),
                **settings,
            }
        if skill_id == "person_research":
            resolved = {}
            for extension_name in settings.get("extensions", []) or []:
                extension_cfg = (db_build.get("extensions", {}) or {}).get(extension_name, {})
                if extension_cfg:
                    resolved.update(extension_cfg)
                    if extension_cfg.get("role_profile"):
                        settings["role_profile"] = extension_cfg["role_profile"]
                    if extension_cfg.get("affiliation_verification"):
                        settings["affiliation_verification"] = extension_cfg["affiliation_verification"]
            settings = {
                **resolved,
                **settings,
            }
        return {
            "skill": skill.to_dict(),
            "help_prompts": _resolved_help_prompts(skill_id, skill_cfg),
            "source_policy": _resolved_source_policy(skill_id),
            "settings": settings,
        }

    @router.get("/skill/jobs")
    def job_list():
        return {"jobs": runner.list_jobs()}

    @router.get("/skill/job/{job_id}")
    def job_status(job_id: str):
        job = runner.get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        d = job.to_dict()
        d["output"] = job.lines
        return d

    @router.post("/skill/run")
    async def run_skill(req: RunRequest):
        skill = registry.get(req.skill_id)
        if not skill:
            raise HTTPException(status_code=404, detail=f"Skill '{req.skill_id}' not found")

        # Collect first line (job_id) before returning
        gen = runner.run(skill, req.args)
        first = await gen.__anext__()          # "job_id:<id>"
        job_id = first.split(":", 1)[1] if ":" in first else first

        # Fire off the rest of the run in the background
        async def _drain():
            async for line in gen:
                q = _sse_queues.get(job_id)
                if q:
                    await q.put(line)
            # Signal EOF
            q = _sse_queues.get(job_id)
            if q:
                await q.put(None)

        asyncio.create_task(_drain())
        return {"job_id": job_id, "skill_id": req.skill_id, "status": "running"}

    @router.get("/skill/stream/{job_id}")
    async def stream_job(job_id: str):
        """Server-Sent Events stream for live job output."""
        job = runner.get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        queue: asyncio.Queue = asyncio.Queue()
        _sse_queues[job_id] = queue

        # Replay buffered lines already captured
        for line in job.lines:
            await queue.put(f"data:{line}")

        if job.status != "running":
            await queue.put(f"status:{job.status}")
            await queue.put(None)

        async def event_stream():
            try:
                while True:
                    item = await asyncio.wait_for(queue.get(), timeout=30.0)
                    if item is None:
                        yield "event: done\ndata: {}\n\n"
                        break
                    event_type = "message"
                    if item.startswith("status:"):
                        event_type = "status"
                        data = item[7:]
                    elif item.startswith("error:"):
                        event_type = "error"
                        data = item[6:]
                    else:
                        data = item[5:] if item.startswith("data:") else item
                    yield f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
            except asyncio.TimeoutError:
                yield "event: timeout\ndata: {}\n\n"
            finally:
                _sse_queues.pop(job_id, None)

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    return router
