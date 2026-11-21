"""Shared contracts for every Ezra component.

These are the structured handoffs from the spec (§9) as amended by docs/decisions.md.
Every department talks to every other department only through these shapes.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SCHEMA_VERSION = "1.0"


def utcnow() -> datetime:
    return datetime.now(UTC)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class _Model(BaseModel):
    # Reject unknown fields so a malformed handoff fails loudly instead of silently.
    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# Enums (D-001 severity, D-002 verdict layers)
# ---------------------------------------------------------------------------


class Severity(StrEnum):
    """Single severity scale (D-001)."""

    CRITICAL = "critical"  # unusable/unsafe/misleading -> automatic fail
    MAJOR = "major"  # must be fixed before PASS
    MINOR = "minor"  # logged as a note, never blocks


class Verification(StrEnum):
    """How an Acceptance Criterion is checked."""

    TEST = "test"  # a Tester-written test whose name contains the criterion id
    INSPECTION = "inspection"  # Guardian reads the diff (Tier 2)
    DETERMINISTIC = "deterministic"  # a named code check (see DeterministicCheck)


class DeterministicCheck(StrEnum):
    TESTS_PASS = "tests_pass"  # the whole test suite passes
    LINT_CLEAN = "lint_clean"  # ruff reports no problems


class Department(StrEnum):
    EZRA = "ezra"
    CODE_JOE = "code_joe"
    BUILDER = "builder"
    TESTER = "tester"
    GUARDIAN = "guardian"
    LEARNER = "learner"
    ARTIFACT_CREATOR = "artifact_creator"


class Verdict(StrEnum):
    """Layer 3: the only verdict that moves a task (D-002)."""

    PASS = "PASS"
    REVISE = "REVISE"
    HOLD = "HOLD"
    ESCALATE = "ESCALATE"


class QualityGrade(StrEnum):
    """Layer 2: Rubric grade, an input to the verdict, never flow control (D-002, D-003)."""

    EXCELLENT = "excellent"
    PASS = "pass"
    CONDITIONAL = "conditional"
    FAIL = "fail"


class CriterionStatus(StrEnum):
    MET = "met"
    UNMET = "unmet"
    CANNOT_VERIFY = "cannot_verify"  # treated as UNMET by the verdict table


class ReviewTier(StrEnum):
    """Risk-tiered review (D-007)."""

    NONE = "tier0_none"
    DETERMINISTIC = "tier1_deterministic"
    CHECKLIST = "tier2_checklist"
    FULL_RUBRIC = "tier3_full_rubric"


class ResultStatus(StrEnum):
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"


class TaskStatus(StrEnum):
    CREATED = "created"
    RUNNING = "running"
    IN_REVIEW = "in_review"
    HELD = "held"
    DONE = "done"
    ESCALATED = "escalated"
    FAILED = "failed"


# ---------------------------------------------------------------------------
# Acceptance Criteria (D-001)
# ---------------------------------------------------------------------------


class AcceptanceCriterion(_Model):
    id: str = Field(pattern=r"^AC\d+$", description="e.g. AC1; Tester test names contain it")
    text: str
    severity: Severity
    verification: Verification
    check: DeterministicCheck | None = Field(
        default=None, description="Required when verification is deterministic"
    )
    required_evidence: str = ""

    @model_validator(mode="after")
    def _check_matches_verification(self) -> AcceptanceCriterion:
        if (self.verification is Verification.DETERMINISTIC) != (self.check is not None):
            raise ValueError("'check' must be set exactly when verification is deterministic")
        return self


# ---------------------------------------------------------------------------
# Loop counters (D-004) and limits
# ---------------------------------------------------------------------------


class Limits(_Model):
    max_infra_retries: int = 2
    internal_iteration_cap: int = 2
    internal_iteration_cap_after_revise: int = 1
    correction_cycle_limit: int = 1
    task_budget_usd: float = 2.0
    daily_budget_usd: float = 10.0
    test_timeout_seconds: int = 120


class LoopCounters(_Model):
    """The three separate counters from D-004. Ezra owns them; departments ask, never set."""

    internal_iterations_used: int = 0
    internal_iteration_cap: int = 2
    internal_iteration_cap_after_revise: int = 1
    correction_cycles_used: int = 0
    correction_cycle_limit: int = 1

    @classmethod
    def from_limits(cls, limits: Limits) -> LoopCounters:
        return cls(
            internal_iteration_cap=limits.internal_iteration_cap,
            internal_iteration_cap_after_revise=limits.internal_iteration_cap_after_revise,
            correction_cycle_limit=limits.correction_cycle_limit,
        )

    def can_iterate_internally(self) -> bool:
        return self.internal_iterations_used < self.internal_iteration_cap

    def record_internal_iteration(self) -> None:
        if not self.can_iterate_internally():
            raise LoopLimitError("internal iteration cap reached")
        self.internal_iterations_used += 1

    def correction_budget_left(self) -> bool:
        return self.correction_cycles_used < self.correction_cycle_limit

    def start_revision(self) -> None:
        """Called when Guardian issues REVISE. Consumes the task's correction cycle."""
        if not self.correction_budget_left():
            raise LoopLimitError("correction budget exhausted; must ESCALATE")
        self.correction_cycles_used += 1
        self.internal_iterations_used = 0
        self.internal_iteration_cap = self.internal_iteration_cap_after_revise


class LoopLimitError(RuntimeError):
    pass


class Budget(_Model):
    task_limit_usd: float
    daily_limit_usd: float


# ---------------------------------------------------------------------------
# Task envelope (spec §9.1 + decisions)
# ---------------------------------------------------------------------------


class TaskEnvelope(_Model):
    schema_version: str = SCHEMA_VERSION
    task_id: str = Field(default_factory=lambda: new_id("task"))
    parent_task_id: str | None = None
    source: Department = Department.EZRA
    target_department: Department
    created_at: datetime = Field(default_factory=utcnow)
    description: str
    project_ref: str | None = Field(default=None, description="Path to the target git repo")
    context_refs: list[str] = Field(default_factory=list)
    acceptance_criteria: list[AcceptanceCriterion] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    counters: LoopCounters = Field(default_factory=LoopCounters)
    budget: Budget
    permissions: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique_criterion_ids(self) -> TaskEnvelope:
        ids = [c.id for c in self.acceptance_criteria]
        if len(ids) != len(set(ids)):
            raise ValueError(f"duplicate acceptance criterion ids: {ids}")
        return self


# ---------------------------------------------------------------------------
# Department results (spec §9.2 + code-specific fields)
# ---------------------------------------------------------------------------


class InterfaceItem(_Model):
    path: str
    symbol: str
    signature: str
    description: str = ""


class TestCaseResult(_Model):
    __test__: ClassVar[bool] = False  # not a pytest test class, despite the name

    name: str  # e.g. "tests/acceptance/test_ac1.py::test_ac1_counts_words"
    outcome: Literal["passed", "failed", "error", "skipped"]
    message: str = ""


class CommandRun(_Model):
    """One sandboxed run of an allowlisted command (pytest, ruff)."""

    command: Literal["pytest", "ruff"]
    exit_code: int | None  # None means it timed out
    timed_out: bool = False
    duration_seconds: float = 0.0
    output_excerpt: str = ""  # bounded excerpt; the full log is referenced, not embedded
    cases: list[TestCaseResult] = Field(default_factory=list)  # pytest only


class TokenMetrics(_Model):
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    estimated_cost_usd: float = 0.0


class StandardDepartmentResult(_Model):
    schema_version: str = SCHEMA_VERSION
    task_id: str
    source_department: Department
    status: ResultStatus
    summary: str
    artifact_refs: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    tokens: TokenMetrics = Field(default_factory=TokenMetrics)
    model_call_count: int = 0
    tool_call_count: int = 0
    correction_cycles_used: int = 0
    # Code Joe specific
    worktree_path: str | None = None
    branch: str | None = None
    changed_files: list[str] = Field(default_factory=list)
    interface_spec: list[InterfaceItem] = Field(default_factory=list)
    command_runs: list[CommandRun] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Guardian review (spec §8.5 + D-002/D-007)
# ---------------------------------------------------------------------------


class CriterionResult(_Model):
    criterion_id: str
    status: CriterionStatus
    evidence: str = ""


class Finding(_Model):
    """A problem found outside the Acceptance Criteria (e.g. an integrity check)."""

    code: str
    severity: Severity
    message: str
    auto_fixable: bool = True  # False means the verdict table must ESCALATE (row 2)


class GuardianReview(_Model):
    review_id: str = Field(default_factory=lambda: new_id("review"))
    task_id: str
    source_department: Department
    tier: ReviewTier
    criteria_version: str = "task-snapshot"
    criteria_results: list[CriterionResult] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    grade: QualityGrade | None = None
    rubric_version: str | None = None  # set when a Rubric grade was given (D-014)
    verdict: Verdict
    matched_rule: int
    required_corrections: list[str] = Field(default_factory=list)
    approval_requirements: list[str] = Field(default_factory=list)
    summary: str = ""
    created_at: datetime = Field(default_factory=utcnow)


# ---------------------------------------------------------------------------
# Model invocation record (routing addendum §11 + cache tokens)
# ---------------------------------------------------------------------------


class ContextRef(_Model):
    """One labelled piece of context injected into a call (for later attribution, D-012).
    The full text lives in the store's text table, keyed by `sha`."""

    label: str
    chars: int
    sha: str


class ModelInvocation(_Model):
    invocation_id: str = Field(default_factory=lambda: new_id("inv"))
    task_id: str | None
    operation_id: str
    department: Department
    operation_type: str
    provider: str = "anthropic"
    model_id: str  # the model that served the call (differs from requested on fallback)
    requested_model: str | None = None
    model_version: str = ""
    routing_policy_version: str = "phase1-static"
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    estimated_cost_usd: float | None = None
    actual_cost_usd: float | None = None
    latency_ms: int = 0
    success: bool = True
    escalation: bool = False
    correction_cycle_used: bool = False
    failure_reason: str | None = None
    fallback_used: bool = False
    stop_reason: str | None = None
    request_id: str | None = None
    # Attribution (M6): which prompt version and which injected context this call used.
    # Hashes point into the store's text table, where the full text is kept (locally only).
    prompt_name: str = ""
    prompt_version: str = ""  # "<name>@<first 10 hex of sha256(system prompt)>"
    context: list[ContextRef] = Field(default_factory=list)
    message_hashes: list[str] = Field(default_factory=list)
    response_hash: str | None = None
    # Lesson ids carried in the prompt (progressive learning, D-012), so a lesson's effect
    # can be traced to the calls that carried it.
    context_refs: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utcnow)


# ---------------------------------------------------------------------------
# Approval records (D-009). A HOLD is a stored, pending record (D-011), so any
# client (CLI now, UI later) can list and answer it.
# ---------------------------------------------------------------------------


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ApprovalRecord(_Model):
    approval_id: str = Field(default_factory=lambda: new_id("apr"))
    task_id: str | None
    level: int = Field(ge=1, le=4)  # D-009 level
    kind: str  # e.g. "budget_hold"
    summary: str
    details: dict[str, Any] = Field(default_factory=dict)
    status: ApprovalStatus = ApprovalStatus.PENDING
    response: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
    resolved_at: datetime | None = None


# ---------------------------------------------------------------------------
# Lessons: progressive learning (D-012 goal 3, docs/research/progressive-learning.md §4)
# ---------------------------------------------------------------------------


class LessonKind(StrEnum):
    STRATEGY = "strategy"  # a way of working that led to success
    PITFALL = "pitfall"  # a mistake Guardian or the checks caught
    CHECK = "check"  # something to verify before finishing


class LessonStatus(StrEnum):
    ACTIVE = "active"  # retrieved into prompts
    RETIRED = "retired"  # kept for history, never retrieved


class LessonSource(StrEnum):
    INFERRED = "inferred"  # distilled by the Reflector from a judged outcome
    CONFIRMED = "confirmed"  # the user confirmed it (becomes a Standard in Phase 3)


class Lesson(_Model):
    """One short, reusable lesson. Itemized and updated by small deltas, never rewritten as
    a whole playbook (ACE). Every change is a new version in the lesson history."""

    lesson_id: str = Field(default_factory=lambda: new_id("les"))
    operation: str  # the prompt it goes into, e.g. "builder.implement"
    project: str | None = None  # None = any project
    kind: LessonKind
    trigger: str  # when it applies
    text: str  # the lesson itself, one or two sentences
    evidence: list[str] = Field(default_factory=list)  # task ids that taught or reinforced it
    source: LessonSource = LessonSource.INFERRED
    status: LessonStatus = LessonStatus.ACTIVE
    helpful: int = 0
    harmful: int = 0
    uses: int = 0  # tasks it was injected into
    version: int = 1
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    @property
    def score(self) -> int:
        return self.helpful - self.harmful
