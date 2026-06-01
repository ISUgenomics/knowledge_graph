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


def make_skills_router(registry: SkillRegistry, runner: SkillRunner) -> APIRouter:
    router = APIRouter(tags=["skills"])

    # In-memory SSE queues: job_id -> asyncio.Queue
    _sse_queues: dict[str, asyncio.Queue] = {}

    @router.get("/skill/list")
    def skill_list(entity_type: str = ""):
        return {"skills": [s.to_dict() for s in registry.list(entity_type)]}

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
