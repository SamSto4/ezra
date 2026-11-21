"""Local HTTP API for the UI (M7, D-011). A thin layer over ezra.core, like the CLI.

Safety:
- Served on 127.0.0.1 only (see `serve`).
- Requests whose Host isn't localhost are refused, which blocks DNS-rebinding pages.
- Every request that changes something (POST) needs the `X-Ezra-Client` header. A web page
  on another site can't add a custom header without a CORS preflight, and this server
  allows no cross-origin requests, so other sites can't start tasks or answer HOLDs.

Long actions (run, resume, review, approve, reject) start in a background thread and return
at once; the UI follows them through the live events stream.
"""

from __future__ import annotations

import json
import subprocess
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ezra import core
from ezra.gateway import (
    BudgetHold,
    Gateway,
    GatewayError,
    MissingCredentials,
    ModelRefusal,
    start_of_local_day,
)
from ezra.intake import IntakeError
from ezra.roster import agent_stats, system_view
from ezra.store import Store
from ezra.trace import Trace

CLIENT_HEADER = "x-ezra-client"
LOCAL_HOSTS = {"127.0.0.1", "localhost", "[::1]", "testserver"}
UI_DIST = Path(__file__).resolve().parents[2] / "ui" / "dist"


@dataclass
class Job:
    task_id: str
    action: str
    state: str = "running"  # running, finished, failed
    outcome: str | None = None
    error: str | None = None
    started_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class AskBody(BaseModel):
    request: str


class RunBody(BaseModel):
    task_budget_usd: float | None = None  # can only lower the task's cap
    memory: str | None = None  # "off", "lessons" or "frozen" for this run only


class AnswerBody(BaseModel):
    approved: bool
    extend_usd: float | None = None


def _hostname(host: str) -> str:
    """The Host header without its port ("[::1]:8765" -> "[::1]")."""
    if host.startswith("["):
        return host.split("]", 1)[0] + "]"
    return host.rsplit(":", 1)[0]


def _dump(obj: Any) -> Any:
    return obj.model_dump(mode="json") if hasattr(obj, "model_dump") else obj


def trace_json(tr: Trace) -> dict[str, Any]:
    return {
        "task": _dump(tr.envelope), "status": str(tr.status), "verdict": tr.verdict,
        "spend_usd": tr.spend_usd, "calls": tr.calls, "unpriced_calls": tr.unpriced_calls,
        "rows": [{"at": r.at.isoformat(), "step": r.step, "kind": r.kind, "detail": r.detail,
                  "data": r.data, "invocation": _dump(r.invocation) if r.invocation else None}
                 for r in tr.rows],
        "totals": [t.__dict__ for t in tr.totals],
        "reviews": [_dump(r) for r in tr.reviews],
        "approvals": [_dump(a) for a in tr.approvals],
    }


def outcome_json(out: core.RunOutcome) -> dict[str, Any]:
    return {"task_id": out.task_id, "status": str(out.status), "outcome": out.outcome,
            "holds": out.holds, "stopped": out.stopped, "spend_usd": out.spend_usd,
            "reviews": out.reviews, "review": _dump(out.review) if out.review else None,
            "result": _dump(out.result) if out.result else None}


def create_app(open_store: Callable[[], Store] = core.open_store,
               open_gateway: Callable[[Store], Gateway] = core.open_gateway,
               run_kwargs: dict[str, Any] | None = None,
               poll_seconds: float = 0.5) -> FastAPI:
    """`open_store`/`open_gateway` and `run_kwargs` (checkpoint and worktree paths) are
    injectable so tests can use temporary files and scripted models."""
    app = FastAPI(title="Ezra", docs_url=None, redoc_url=None, openapi_url=None)
    jobs: dict[str, Job] = {}
    jobs_lock = threading.Lock()
    extra = run_kwargs or {}

    @app.middleware("http")
    async def local_only(request: Request, call_next):
        if _hostname(request.headers.get("host") or "") not in LOCAL_HOSTS:
            return JSONResponse({"detail": "Ezra only answers on localhost."}, 403)
        if request.method not in ("GET", "HEAD") and not request.headers.get(CLIENT_HEADER):
            return JSONResponse({"detail": f"Missing {CLIENT_HEADER} header."}, 403)
        return await call_next(request)

    def with_store(fn: Callable[[Store], Any]) -> Any:
        store = open_store()
        try:
            return fn(store)
        finally:
            store.close()

    # -- reads ----------------------------------------------------------------------

    @app.get("/api/status")
    def status() -> dict[str, Any]:
        def read(store: Store) -> dict[str, Any]:
            limits = core.load_limits()
            return {"spent_today_usd": store.spend_since(start_of_local_day(
                        datetime.now(UTC))),
                    "daily_limit_usd": limits.daily_budget_usd,
                    "task_limit_usd": limits.task_budget_usd,
                    "pending_approvals": len(store.pending_approvals()),
                    "last_event_id": store.last_event_id(),
                    "running": sorted(t for t, j in jobs.items() if j.state == "running")}
        return with_store(read)

    @app.get("/api/tasks")
    def tasks(limit: int = 50) -> list[dict[str, Any]]:
        def read(store: Store) -> list[dict[str, Any]]:
            out = []
            for t in store.list_tasks(limit):
                reviews = store.reviews_for_task(t["task_id"])
                out.append({**t, "verdict": str(reviews[-1].verdict) if reviews else None,
                            "job": jobs[t["task_id"]].__dict__ if t["task_id"] in jobs
                            else None})
            return out
        return with_store(read)

    @app.get("/api/tasks/{task_id}")
    def task(task_id: str) -> dict[str, Any]:
        tr = with_store(lambda s: core.get_trace(s, task_id))
        if tr is None:
            raise HTTPException(404, f"No task '{task_id}'.")
        data = trace_json(tr)
        data["title"] = with_store(lambda s: s.task_title(task_id))
        data["job"] = jobs[task_id].__dict__ if task_id in jobs else None
        return data

    @app.get("/api/texts/{sha}")
    def text(sha: str) -> dict[str, str]:
        found = with_store(lambda s: s.get_text(sha))
        if found is None:
            raise HTTPException(404, "No stored text with that hash.")
        return {"sha": sha, "text": found}

    @app.get("/api/system")
    def system() -> dict[str, Any]:
        return with_store(system_view)

    @app.get("/api/tasks/{task_id}/diff")
    def diff(task_id: str) -> dict[str, Any]:
        """What the task changed on its branch, against where it started (read-only git)."""
        found = with_store(lambda s: s.get_task(task_id))
        if found is None:
            raise HTTPException(404, f"No task '{task_id}'.")
        env, _ = found
        branch = f"ezra/{task_id}"
        try:
            out = subprocess.run(["git", "diff", "--no-color", f"HEAD...{branch}"],
                                 cwd=env.project_ref, capture_output=True, text=True,
                                 timeout=20)
        except (OSError, subprocess.TimeoutExpired) as e:
            raise HTTPException(500, f"git diff failed: {e}") from e
        if out.returncode != 0:
            return {"branch": branch, "diff": "", "note": "No branch yet: the task hasn't "
                    "made changes."}
        text = out.stdout
        return {"branch": branch, "diff": text[:300_000],
                "truncated": len(text) > 300_000}

    @app.get("/api/agents")
    def agents() -> list[dict[str, Any]]:
        return with_store(agent_stats)

    @app.get("/api/approvals")
    def approvals() -> list[dict[str, Any]]:
        return [_dump(a) for a in with_store(core.pending_approvals)]

    @app.get("/api/events")
    def events(after: int = 0, task_id: str | None = None) -> list[dict[str, Any]]:
        return with_store(lambda s: s.events_after(after, task_id))

    @app.get("/api/events/stream")
    def events_stream(request: Request, after: int = 0, task_id: str | None = None,
                      max_seconds: float = 3600.0) -> StreamingResponse:
        """Server-Sent Events: new rows from the events table as they're written."""
        def gen() -> Iterator[str]:
            last, deadline = after, time.monotonic() + max_seconds
            store = open_store()
            try:
                yield ": connected\n\n"
                while time.monotonic() < deadline:
                    rows = store.events_after(last, task_id)
                    for row in rows:
                        last = row["id"]
                        yield f"id: {row['id']}\ndata: {json.dumps(row, default=str)}\n\n"
                    if not rows:
                        yield ": keep-alive\n\n"
                        time.sleep(poll_seconds)
            finally:
                store.close()
        return StreamingResponse(gen(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache"})

    # -- actions ----------------------------------------------------------------------

    @app.post("/api/ask")
    def ask(body: AskBody) -> dict[str, Any]:
        if not body.request.strip():
            raise HTTPException(400, "Ask something first.")
        store = open_store()
        try:
            result = core.ask(open_gateway(store), body.request)
        except MissingCredentials as e:
            raise HTTPException(503, str(e)) from e
        except BudgetHold as hold:
            raise HTTPException(409, {"hold": _dump(hold.approval)}) from hold
        except (ModelRefusal, GatewayError, IntakeError) as e:
            raise HTTPException(502, str(e)) from e
        finally:
            store.close()
        return {"route": str(result.route), "answer": result.answer,
                "unsupported_reason": result.unsupported_reason, "title": result.task_title,
                "task": _dump(result.envelope) if result.envelope else None,
                "cost_usd": sum(i.actual_cost_usd or 0.0 for i in result.invocations)}

    def start_job(task_id: str, action: str, fn: Callable[[Store, Gateway], Any]) -> Job:
        with jobs_lock:
            current = jobs.get(task_id)
            if current and current.state == "running":
                raise HTTPException(409, f"{task_id} already has a {current.action} "
                                         "in progress.")
            job = jobs[task_id] = Job(task_id=task_id, action=action)

        def work() -> None:
            store = open_store()
            try:
                out = fn(store, open_gateway(store))
                job.outcome = out.outcome
                job.state = "finished"
            except core.RunError as e:
                job.state, job.error = "failed", str(e)
            except MissingCredentials as e:
                job.state, job.error = "failed", str(e)
            except Exception as e:  # report anything else to the UI rather than vanish
                job.state, job.error = "failed", f"{type(e).__name__}: {e}"
            finally:
                store.close()

        threading.Thread(target=work, name=f"ezra-{action}-{task_id}", daemon=True).start()
        return job

    def precheck(task_id: str, fn: Callable[[Store], Any]) -> None:
        """Run the cheap checks in the request, so obvious refusals come back as errors
        instead of a failed background job."""
        try:
            with_store(fn)
        except core.RunError as e:
            raise HTTPException(409, str(e)) from e

    def _created(store: Store, task_id: str) -> None:
        found = store.get_task(task_id)
        if found is None:
            raise core.RunError(f"No task '{task_id}'.")
        if found[1] is not core.TaskStatus.CREATED:
            raise core.RunError(f"Task {task_id} is {found[1]}; only created tasks can be run.")

    @app.post("/api/tasks/{task_id}/run", status_code=202)
    def run(task_id: str, body: RunBody | None = None) -> dict[str, Any]:
        precheck(task_id, lambda s: _created(s, task_id))
        cap = body.task_budget_usd if body else None
        if cap is not None:
            limit = core.load_limits().task_budget_usd
            if not 0 < cap <= limit:
                raise HTTPException(400, f"A run's cap can only be lowered (max ${limit:.2f}).")
        memory = body.memory if body else None
        if memory not in (None, "off", "lessons", "frozen"):
            raise HTTPException(400, "memory must be off, lessons or frozen.")
        return start_job(task_id, "run", lambda s, gw: core.run_task(
            s, gw, task_id, task_budget_usd=cap, memory=memory, **extra)).__dict__

    @app.post("/api/tasks/{task_id}/learn", status_code=202)
    def learn(task_id: str) -> dict[str, Any]:
        @dataclass
        class _Done:
            outcome: str

        def go(s: Store, gw: Gateway) -> _Done:
            out = core.learn(s, gw, task_id)
            return _Done("skipped" if out.skipped and not out.reflected else "learned")
        return start_job(task_id, "learn", go).__dict__

    @app.get("/api/lessons")
    def lessons() -> list[dict[str, Any]]:
        found = with_store(lambda s: core.list_lessons(s, include_retired=True))
        return [_dump(x) for x in found]

    @app.get("/api/lessons/{lesson_id}")
    def lesson(lesson_id: str) -> dict[str, Any]:
        found = with_store(lambda s: core.lesson_history(s, lesson_id))
        if found is None:
            raise HTTPException(404, f"No lesson '{lesson_id}'.")
        les, history = found
        return {"lesson": _dump(les), "history": history}

    @app.post("/api/lessons/{lesson_id}/retire")
    def retire(lesson_id: str) -> dict[str, Any]:
        try:
            done = with_store(lambda s: core.retire_lesson(s, lesson_id, "retired in the UI"))
            return _dump(done)
        except core.RunError as e:
            raise HTTPException(409, str(e)) from e

    @app.post("/api/tasks/{task_id}/resume", status_code=202)
    def resume(task_id: str) -> dict[str, Any]:
        return start_job(task_id, "resume", lambda s, gw: core.resume_task(
            s, gw, task_id, **extra)).__dict__

    @app.post("/api/tasks/{task_id}/review", status_code=202)
    def review(task_id: str) -> dict[str, Any]:
        return start_job(task_id, "review", lambda s, gw: core.review_task(
            s, gw, task_id, **extra)).__dict__

    @app.post("/api/tasks/{task_id}/abandon")
    def abandon(task_id: str) -> dict[str, Any]:
        try:
            before = with_store(lambda s: core.abandon_task(s, task_id, "abandoned in the UI"))
        except core.RunError as e:
            raise HTTPException(409, str(e)) from e
        return {"task_id": task_id, "status_before": str(before), "status": "failed"}

    @app.post("/api/approvals/{approval_id}", status_code=202)
    def answer(approval_id: str, body: AnswerBody) -> dict[str, Any]:
        rec = with_store(lambda s: s.get_approval(approval_id))
        if rec is None:
            raise HTTPException(404, f"No approval '{approval_id}'.")
        if rec.task_id is None:
            raise HTTPException(409, "That HOLD came from a question, not a task. "
                                     "Ask again instead.")
        return start_job(rec.task_id, "approve" if body.approved else "reject",
                         lambda s, gw: core.answer_hold(
                             s, gw, approval_id, body.approved,
                             extend_usd=body.extend_usd, **extra)).__dict__

    @app.get("/api/jobs/{task_id}")
    def job(task_id: str) -> dict[str, Any]:
        if task_id not in jobs:
            raise HTTPException(404, "No job for that task in this server session.")
        return jobs[task_id].__dict__

    # -- the built UI, if present ---------------------------------------------------------

    if UI_DIST.is_dir():
        app.mount("/assets", StaticFiles(directory=UI_DIST / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str) -> FileResponse:
            return FileResponse(UI_DIST / "index.html")

    return app


def serve(port: int = 8765) -> None:
    import uvicorn
    uvicorn.run(create_app(), host="127.0.0.1", port=port, log_level="warning")
