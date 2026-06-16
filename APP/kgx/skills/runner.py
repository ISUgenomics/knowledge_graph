"""
Skill runner — executes a skill as an async subprocess.

Each run gets a unique job_id. Output is streamed line-by-line and forwarded
to connected SSE clients via a simple in-memory queue.

The runner does NOT import from the skill — it invokes the skill's plugin.py
via `python plugin.py <args>` so the skill's own venv/dependencies are used.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import AsyncIterator

from .registry import SkillMeta


@dataclass
class JobStatus:
    job_id: str
    skill_id: str
    status: str          # "running" | "completed" | "failed"
    started_at: float
    finished_at: float | None = None
    return_code: int | None = None
    lines: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "skill_id": self.skill_id,
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "return_code": self.return_code,
            "line_count": len(self.lines),
        }


class SkillRunner:
    def __init__(self, python: str = "python3"):
        self.python = python
        self._jobs: dict[str, JobStatus] = {}

    def list_jobs(self) -> list[dict]:
        return [j.to_dict() for j in self._jobs.values()]

    def get_job(self, job_id: str) -> JobStatus | None:
        return self._jobs.get(job_id)

    async def run(
        self,
        skill: SkillMeta,
        extra_args: list[str] | None = None,
    ) -> AsyncIterator[str]:
        """
        Run a skill and yield output lines as they arrive.
        Yields strings of the form:
          "data: <line>"   — stdout/stderr
          "status: <json>" — status update at start/end
        """
        job_id = str(uuid.uuid4())[:8]
        job = JobStatus(
            job_id=job_id,
            skill_id=skill.id,
            status="running",
            started_at=time.time(),
        )
        self._jobs[job_id] = job

        cmd = [self.python, str(skill.entry_path)] + (extra_args or [])

        yield f"job_id:{job_id}"
        yield f"status:running"

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=str(skill.path),
            )

            async for raw_line in proc.stdout:
                line = raw_line.decode("utf-8", errors="replace").rstrip()
                job.lines.append(line)
                yield f"data:{line}"

            await proc.wait()
            job.return_code = proc.returncode
            job.status = "completed" if proc.returncode == 0 else "failed"
            job.finished_at = time.time()
            yield f"status:{job.status}"

        except Exception as e:
            job.status = "failed"
            job.finished_at = time.time()
            job.lines.append(str(e))
            yield f"error:{e}"
            yield f"status:failed"
