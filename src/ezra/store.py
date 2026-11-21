"""SQLite store for tasks, model invocations, results, reviews and trace events (D-010).

One local file. Every row carries the task_id so a whole task can be traced end to end.
Secrets never go in here: callers pass contracts, and contracts carry no credentials.
"""

from __future__ import annotations

import functools
import hashlib
import json
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ezra.contracts import (
    ApprovalRecord,
    ApprovalStatus,
    GuardianReview,
    Lesson,
    LessonStatus,
    ModelInvocation,
    StandardDepartmentResult,
    TaskEnvelope,
    TaskStatus,
    utcnow,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    task_id      TEXT PRIMARY KEY,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    status       TEXT NOT NULL,
    target       TEXT NOT NULL,
    description  TEXT NOT NULL,
    envelope     TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS model_invocations (
    invocation_id         TEXT PRIMARY KEY,
    task_id               TEXT,
    operation_id          TEXT NOT NULL,
    department            TEXT NOT NULL,
    operation_type        TEXT NOT NULL,
    model_id              TEXT NOT NULL,
    input_tokens          INTEGER NOT NULL,
    output_tokens         INTEGER NOT NULL,
    cache_read_tokens     INTEGER NOT NULL,
    cache_creation_tokens INTEGER NOT NULL,
    estimated_cost_usd    REAL,
    actual_cost_usd       REAL,
    latency_ms            INTEGER NOT NULL,
    success               INTEGER NOT NULL,
    created_at            TEXT NOT NULL,
    record                TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_inv_task ON model_invocations(task_id);
CREATE INDEX IF NOT EXISTS idx_inv_created ON model_invocations(created_at);
CREATE TABLE IF NOT EXISTS department_results (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id     TEXT NOT NULL,
    department  TEXT NOT NULL,
    status      TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    record      TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS guardian_reviews (
    review_id   TEXT PRIMARY KEY,
    task_id     TEXT NOT NULL,
    tier        TEXT NOT NULL,
    verdict     TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    record      TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id     TEXT,
    created_at  TEXT NOT NULL,
    kind        TEXT NOT NULL,
    data        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_task ON events(task_id);
CREATE TABLE IF NOT EXISTS approval_records (
    approval_id TEXT PRIMARY KEY,
    task_id     TEXT,
    level       INTEGER NOT NULL,
    kind        TEXT NOT NULL,
    status      TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    record      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_approvals_status ON approval_records(status);
CREATE TABLE IF NOT EXISTS run_leases (
    task_id     TEXT PRIMARY KEY,
    pid         INTEGER NOT NULL,
    host        TEXT NOT NULL,
    started_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS texts (
    sha         TEXT PRIMARY KEY,
    created_at  TEXT NOT NULL,
    text        TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS lessons (
    lesson_id   TEXT PRIMARY KEY,
    operation   TEXT NOT NULL,
    project     TEXT,
    status      TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    record      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_lessons_op ON lessons(operation, status);
CREATE TABLE IF NOT EXISTS lesson_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    lesson_id   TEXT NOT NULL,
    version     INTEGER NOT NULL,
    action      TEXT NOT NULL,
    task_id     TEXT,
    reason      TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    record      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_lesson_history ON lesson_history(lesson_id);
CREATE TABLE IF NOT EXISTS lesson_uses (
    task_id     TEXT NOT NULL,
    lesson_id   TEXT NOT NULL,
    operation   TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    PRIMARY KEY (task_id, lesson_id, operation)
);
"""


def _ts(dt: datetime | None = None) -> str:
    # Fixed-width UTC text, so string comparison in SQL matches time order.
    return (dt or utcnow()).astimezone(UTC).isoformat(timespec="microseconds")


def text_sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _locked(method):
    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)
    return wrapper


class _ThreadSafe(type):
    """Wraps every public method in the store's lock. Builder and Tester run in parallel
    threads and share one connection, so every read and write is serialized."""

    def __new__(mcs, name, bases, ns):
        for key, value in list(ns.items()):
            if callable(value) and not key.startswith("_"):
                ns[key] = _locked(value)
        return super().__new__(mcs, name, bases, ns)


class Store(metaclass=_ThreadSafe):
    def __init__(self, path: Path | str):
        self.path = Path(path)
        if str(path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.conn = sqlite3.connect(str(path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def close(self) -> None:
        self.conn.close()

    # -- tasks -------------------------------------------------------------

    def save_task(self, env: TaskEnvelope, status: TaskStatus = TaskStatus.CREATED) -> None:
        now = _ts()
        with self.conn:
            self.conn.execute(
                """INSERT INTO tasks (task_id, created_at, updated_at, status, target,
                                      description, envelope)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(task_id) DO UPDATE SET
                     updated_at=excluded.updated_at, status=excluded.status,
                     envelope=excluded.envelope""",
                (env.task_id, _ts(env.created_at), now, status, env.target_department,
                 env.description, env.model_dump_json()),
            )

    def set_task_status(self, task_id: str, status: TaskStatus) -> None:
        with self.conn:
            cur = self.conn.execute(
                "UPDATE tasks SET status=?, updated_at=? WHERE task_id=?",
                (status, _ts(), task_id),
            )
        if cur.rowcount == 0:
            raise KeyError(f"unknown task {task_id}")

    def get_task(self, task_id: str) -> tuple[TaskEnvelope, TaskStatus] | None:
        row = self.conn.execute(
            "SELECT envelope, status FROM tasks WHERE task_id=?", (task_id,)
        ).fetchone()
        if row is None:
            return None
        return TaskEnvelope.model_validate_json(row["envelope"]), TaskStatus(row["status"])

    def list_tasks(self, limit: int = 50) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """SELECT t.task_id, t.created_at, t.updated_at, t.status, t.description,
                      COALESCE(SUM(COALESCE(i.actual_cost_usd, i.estimated_cost_usd, 0)), 0)
                        AS spend_usd
               FROM tasks t LEFT JOIN model_invocations i ON i.task_id = t.task_id
               GROUP BY t.task_id ORDER BY t.created_at DESC LIMIT ?""", (limit,)).fetchall()
        return [dict(r) for r in rows]

    # -- model invocations -------------------------------------------------

    def record_invocation(self, inv: ModelInvocation) -> None:
        with self.conn:
            self.conn.execute(
                """INSERT INTO model_invocations VALUES
                   (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (inv.invocation_id, inv.task_id, inv.operation_id, inv.department,
                 inv.operation_type, inv.model_id, inv.input_tokens, inv.output_tokens,
                 inv.cache_read_tokens, inv.cache_creation_tokens, inv.estimated_cost_usd,
                 inv.actual_cost_usd, inv.latency_ms, int(inv.success),
                 _ts(inv.created_at), inv.model_dump_json()),
            )

    def invocations_for_task(self, task_id: str) -> list[ModelInvocation]:
        rows = self.conn.execute(
            "SELECT record FROM model_invocations WHERE task_id=? ORDER BY created_at",
            (task_id,),
        ).fetchall()
        return [ModelInvocation.model_validate_json(r["record"]) for r in rows]

    _COST = "COALESCE(actual_cost_usd, estimated_cost_usd, 0)"

    def invocation_stats(self) -> list[dict[str, Any]]:
        """Per operation: calls, failures, tokens, cost, latency, tasks touched, last call."""
        rows = self.conn.execute(
            f"""SELECT operation_id, COUNT(*) AS calls, SUM(1 - success) AS failures,
                       SUM(input_tokens) AS input_tokens, SUM(output_tokens) AS output_tokens,
                       SUM(cache_read_tokens) AS cache_read_tokens,
                       SUM(cache_creation_tokens) AS cache_creation_tokens,
                       SUM({self._COST}) AS cost_usd, SUM(latency_ms) AS latency_ms,
                       COUNT(DISTINCT task_id) AS tasks, MAX(created_at) AS last_at
                FROM model_invocations GROUP BY operation_id""").fetchall()
        return [dict(r) for r in rows]

    def cache_reads_by_model(self) -> list[dict[str, Any]]:
        rows = self.conn.execute("SELECT model_id, SUM(cache_read_tokens) AS cache_read_tokens "
                                 "FROM model_invocations GROUP BY model_id").fetchall()
        return [dict(r) for r in rows]

    def prompt_versions(self) -> dict[str, list[str]]:
        """Distinct prompt versions per operation, newest first (M6 attribution)."""
        rows = self.conn.execute(
            """SELECT operation_id, json_extract(record, '$.prompt_version') AS v,
                      MAX(created_at) AS last FROM model_invocations
               WHERE COALESCE(json_extract(record, '$.prompt_version'), '') != ''
               GROUP BY operation_id, v ORDER BY last DESC""").fetchall()
        out: dict[str, list[str]] = {}
        for r in rows:
            out.setdefault(r["operation_id"], []).append(r["v"])
        return out

    def review_counts(self) -> dict[str, int]:
        """Guardian verdict counts, plus `_tier1`: reviews settled with no model call."""
        out: dict[str, int] = {}
        for r in self.conn.execute("SELECT verdict, tier FROM guardian_reviews").fetchall():
            out[r["verdict"]] = out.get(r["verdict"], 0) + 1
            if r["tier"] == "tier1_deterministic":
                out["_tier1"] = out.get("_tier1", 0) + 1
        return out

    def event_counts(self) -> dict[str, int]:
        rows = self.conn.execute("SELECT kind, COUNT(*) AS n FROM events GROUP BY kind")
        return {r["kind"]: r["n"] for r in rows.fetchall()}

    def spend_for_task(self, task_id: str) -> float:
        row = self.conn.execute(
            f"SELECT COALESCE(SUM({self._COST}), 0) AS s FROM model_invocations WHERE task_id=?",
            (task_id,),
        ).fetchone()
        return float(row["s"])

    def spend_since(self, since: datetime) -> float:
        row = self.conn.execute(
            f"SELECT COALESCE(SUM({self._COST}), 0) AS s FROM model_invocations "
            "WHERE created_at >= ?",
            (_ts(since),),
        ).fetchone()
        return float(row["s"])

    # -- results and reviews -----------------------------------------------

    def record_result(self, result: StandardDepartmentResult) -> None:
        with self.conn:
            self.conn.execute(
                """INSERT INTO department_results (task_id, department, status, created_at,
                                                   record) VALUES (?, ?, ?, ?, ?)""",
                (result.task_id, result.source_department, result.status, _ts(),
                 result.model_dump_json()),
            )

    def results_for_task(self, task_id: str) -> list[StandardDepartmentResult]:
        rows = self.conn.execute(
            "SELECT record FROM department_results WHERE task_id=? ORDER BY id", (task_id,)
        ).fetchall()
        return [StandardDepartmentResult.model_validate_json(r["record"]) for r in rows]

    def record_review(self, review: GuardianReview) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT INTO guardian_reviews VALUES (?, ?, ?, ?, ?, ?)",
                (review.review_id, review.task_id, review.tier, review.verdict,
                 _ts(review.created_at), review.model_dump_json()),
            )

    def reviews_for_task(self, task_id: str) -> list[GuardianReview]:
        rows = self.conn.execute(
            "SELECT record FROM guardian_reviews WHERE task_id=? ORDER BY created_at",
            (task_id,),
        ).fetchall()
        return [GuardianReview.model_validate_json(r["record"]) for r in rows]

    # -- run leases (M6) --------------------------------------------------------
    # Which process is driving a task right now. A crash leaves the row behind with a dead
    # pid, which is how `ezra run --resume` tells a stuck task from one that's still going.

    def get_lease(self, task_id: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT pid, host, started_at FROM run_leases WHERE task_id=?",
                                (task_id,)).fetchone()
        return dict(row) if row else None

    def take_lease(self, task_id: str, pid: int, host: str) -> None:
        with self.conn:
            self.conn.execute("INSERT OR REPLACE INTO run_leases (task_id, pid, host, "
                              "started_at) VALUES (?, ?, ?, ?)", (task_id, pid, host, _ts()))

    def release_lease(self, task_id: str, pid: int) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM run_leases WHERE task_id=? AND pid=?",
                              (task_id, pid))

    # -- texts (M6 attribution) -------------------------------------------------
    # Full prompt, context and reply text, stored once per distinct content and referenced
    # by sha256 from invocation records. Lives only in the local, gitignored database.

    def put_text(self, text: str) -> str:
        sha = text_sha(text)
        with self.conn:
            self.conn.execute("INSERT OR IGNORE INTO texts (sha, created_at, text) "
                              "VALUES (?, ?, ?)", (sha, _ts(), text))
        return sha

    def get_text(self, sha: str) -> str | None:
        """Full hash, or a unique prefix of at least 8 hex characters."""
        if len(sha) < 64:
            if len(sha) < 8 or any(c not in "0123456789abcdef" for c in sha):
                return None
            rows = self.conn.execute("SELECT text FROM texts WHERE sha >= ? AND sha < ? "
                                     "LIMIT 2", (sha, sha + "g")).fetchall()
            return rows[0]["text"] if len(rows) == 1 else None
        row = self.conn.execute("SELECT text FROM texts WHERE sha = ?", (sha,)).fetchone()
        return row["text"] if row else None

    # -- trace events --------------------------------------------------------

    def log_event(self, task_id: str | None, kind: str, **data: Any) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT INTO events (task_id, created_at, kind, data) VALUES (?, ?, ?, ?)",
                (task_id, _ts(), kind, json.dumps(data, default=str)),
            )

    def events_for_task(self, task_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT created_at, kind, data FROM events WHERE task_id IS ? ORDER BY id", (task_id,)
        ).fetchall()
        return [{"at": r["created_at"], "kind": r["kind"], **json.loads(r["data"])} for r in rows]

    def last_event_id(self) -> int:
        row = self.conn.execute("SELECT COALESCE(MAX(id), 0) AS m FROM events").fetchone()
        return int(row["m"])

    def events_after(self, last_id: int, task_id: str | None = None,
                     limit: int = 200) -> list[dict[str, Any]]:
        """Events with id > last_id, oldest first: what a live view hasn't seen yet."""
        sql = "SELECT id, task_id, created_at, kind, data FROM events WHERE id > ?"
        args: list[Any] = [last_id]
        if task_id is not None:
            sql += " AND task_id = ?"
            args.append(task_id)
        rows = self.conn.execute(sql + " ORDER BY id LIMIT ?", (*args, limit)).fetchall()
        return [{"id": r["id"], "task_id": r["task_id"], "at": r["created_at"],
                 "kind": r["kind"], "data": json.loads(r["data"])} for r in rows]

    # -- approval records (D-009, D-011) -------------------------------------

    def create_approval(self, rec: ApprovalRecord) -> None:
        with self.conn:
            self.conn.execute(
                # OR IGNORE: a graph step that reruns after a pause re-raises the same
                # hold with the same id; it must not create a second pending row.
                "INSERT OR IGNORE INTO approval_records VALUES (?, ?, ?, ?, ?, ?, ?)",
                (rec.approval_id, rec.task_id, rec.level, rec.kind, rec.status,
                 _ts(rec.created_at), rec.model_dump_json()),
            )

    def get_approval(self, approval_id: str) -> ApprovalRecord | None:
        row = self.conn.execute(
            "SELECT record FROM approval_records WHERE approval_id=?", (approval_id,)
        ).fetchone()
        return ApprovalRecord.model_validate_json(row["record"]) if row else None

    def pending_approvals(self) -> list[ApprovalRecord]:
        rows = self.conn.execute(
            "SELECT record FROM approval_records WHERE status=? ORDER BY created_at",
            (ApprovalStatus.PENDING,),
        ).fetchall()
        return [ApprovalRecord.model_validate_json(r["record"]) for r in rows]

    def approvals_for_task(self, task_id: str) -> list[ApprovalRecord]:
        rows = self.conn.execute(
            "SELECT record FROM approval_records WHERE task_id=? ORDER BY created_at",
            (task_id,),
        ).fetchall()
        return [ApprovalRecord.model_validate_json(r["record"]) for r in rows]

    def resolve_approval(self, approval_id: str, approved: bool,
                         response: str | None = None,
                         extra_details: dict[str, Any] | None = None) -> ApprovalRecord:
        rec = self.get_approval(approval_id)
        if rec is None:
            raise KeyError(f"No approval '{approval_id}'")
        if rec.status is not ApprovalStatus.PENDING:
            raise ValueError(f"Approval '{approval_id}' is already {rec.status}")
        rec = rec.model_copy(update={
            "status": ApprovalStatus.APPROVED if approved else ApprovalStatus.REJECTED,
            "response": response, "resolved_at": utcnow(),
            "details": {**rec.details, **(extra_details or {})}})
        with self.conn:
            self.conn.execute(
                "UPDATE approval_records SET status=?, record=? WHERE approval_id=?",
                (rec.status, rec.model_dump_json(), approval_id),
            )
        return rec

    # -- lessons: progressive learning (D-012) -------------------------------

    def save_lesson(self, lesson: Lesson, action: str, task_id: str | None = None,
                    reason: str = "") -> None:
        """Upsert the lesson and append its new version to the history. The history is
        append-only, so every past state of the playbook can be rebuilt."""
        with self.conn:
            self.conn.execute(
                """INSERT INTO lessons (lesson_id, operation, project, status, updated_at,
                                        record) VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(lesson_id) DO UPDATE SET status=excluded.status,
                     updated_at=excluded.updated_at, record=excluded.record""",
                (lesson.lesson_id, lesson.operation, lesson.project, lesson.status,
                 _ts(lesson.updated_at), lesson.model_dump_json()),
            )
            self.conn.execute(
                """INSERT INTO lesson_history (lesson_id, version, action, task_id, reason,
                                               created_at, record)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (lesson.lesson_id, lesson.version, action, task_id, reason, _ts(),
                 lesson.model_dump_json()),
            )

    def get_lesson(self, lesson_id: str) -> Lesson | None:
        row = self.conn.execute(
            "SELECT record FROM lessons WHERE lesson_id=?", (lesson_id,)).fetchone()
        return Lesson.model_validate_json(row["record"]) if row else None

    def lessons(self, status: LessonStatus | None = None,
                operation: str | None = None) -> list[Lesson]:
        sql, args = "SELECT record FROM lessons WHERE 1=1", []
        if status is not None:
            sql += " AND status=?"
            args.append(status)
        if operation is not None:
            sql += " AND operation=?"
            args.append(operation)
        rows = self.conn.execute(sql + " ORDER BY lesson_id", args).fetchall()
        return [Lesson.model_validate_json(r["record"]) for r in rows]

    def lesson_history(self, lesson_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT version, action, task_id, reason, created_at FROM lesson_history "
            "WHERE lesson_id=? ORDER BY id", (lesson_id,)).fetchall()
        return [dict(r) for r in rows]

    def record_lesson_use(self, task_id: str, lesson_id: str, operation: str) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT OR IGNORE INTO lesson_uses VALUES (?, ?, ?, ?)",
                (task_id, lesson_id, operation, _ts()))

    def lessons_used_by_task(self, task_id: str) -> list[str]:
        rows = self.conn.execute(
            "SELECT DISTINCT lesson_id FROM lesson_uses WHERE task_id=? ORDER BY lesson_id",
            (task_id,)).fetchall()
        return [r["lesson_id"] for r in rows]

    def has_event(self, task_id: str, kind: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM events WHERE task_id=? AND kind=? LIMIT 1", (task_id, kind)
        ).fetchone()
        return row is not None
