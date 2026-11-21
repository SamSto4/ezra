"""Deterministic benchmark checks for each kind of reference output (D-001, D-007).

Each scorer takes an output as text (JSON or markdown, as an agent would produce it) and
returns a BenchmarkScore:

- gates: hard rules from existing contracts and decisions. Failing one means the output is
  broken (it would be repaired, rejected or can't be used as evidence).
- warnings: the reference files' checklists as cheap text checks. Never blocking; logged.
- metrics: sizes, so token cost can be tracked next to quality.

These checks cost zero model calls. They don't judge meaning (is the scope right, is the
answer true): that stays with Guardian. Nothing here feeds the D-002 verdict table.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Callable
from functools import cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ezra.config import CONFIG_DIR, PROJECT_ROOT, _load_yaml
from ezra.contracts import Department, QualityGrade, Verification
from ezra.guardian import rubric as rubric_mod
from ezra.intake import IntakeDecision, Route, problems_with
from ezra.pricing import PriceTable, load_pricing

STANDARD_TEMPLATE = PROJECT_ROOT / "standards" / "templates" / "standard-template.md"


class BenchmarkScore(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: str
    benchmark_version: str
    gates: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)

    @property
    def passed(self) -> bool:
        """No hard rule broken."""
        return not self.gates

    @property
    def clean(self) -> bool:
        """No hard rule broken and every checklist item met."""
        return not self.gates and not self.warnings


@cache
def load_benchmarks(config_dir: Path = CONFIG_DIR) -> dict[str, Any]:
    return _load_yaml(config_dir / "benchmarks.yaml")


def _new(kind: str) -> BenchmarkScore:
    return BenchmarkScore(kind=kind, benchmark_version=str(load_benchmarks()["version"]))


def _has_phrase(text: str, phrases: list[str]) -> list[str]:
    low = text.lower()
    return [p for p in phrases if re.search(rf"(?<!\w){re.escape(p.lower())}(?!\w)", low)]


def _sentences(text: str) -> int:
    return len([s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s])


def _words(text: str) -> int:
    return len(text.split())


def _parse_json(text: str, score: BenchmarkScore) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        score.gates.append(f"not valid JSON ({e.msg})")
        return None


def _schema_errors(e: ValidationError, limit: int = 6) -> list[str]:
    out = []
    for err in e.errors()[:limit]:
        where = ".".join(str(p) for p in err["loc"]) or "record"
        out.append(f"schema: {where}: {err['msg']}")
    return out


# -- Acceptance Criteria (docs/reference-outputs/acceptance-criteria.md) -----------------

# GUESS: a test criterion is concrete when it names a call or quotes code.
_CONCRETE = re.compile(r"\w\(|`[^`]+`")


def score_criteria(text: str) -> BenchmarkScore:
    """Score an intake answer (the IntakeDecision JSON) against the criteria reference."""
    score = _new("acceptance-criteria")
    data = _parse_json(text, score)
    if data is None:
        return score
    try:
        decision = IntakeDecision.model_validate(data)
    except ValidationError as e:
        score.gates.extend(_schema_errors(e))
        return score
    return score_intake_decision(decision, score)


def score_intake_decision(decision: IntakeDecision,
                          score: BenchmarkScore | None = None) -> BenchmarkScore:
    score = score or _new("acceptance-criteria")
    cfg = load_benchmarks()["acceptance_criteria"]
    score.gates.extend(f"intake rule: {p}" for p in problems_with(decision))
    if decision.route is not Route.CODE:
        return score
    crits = decision.acceptance_criteria
    score.metrics.update(criteria=len(crits),
                         chars=sum(len(c.text) for c in crits) + len(decision.task_title)
                         + len(decision.task_description))
    if not cfg["min_criteria"] <= len(crits) <= cfg["max_criteria"]:
        score.warnings.append(f"{len(crits)} criteria; the reference aims for "
                              f"{cfg['min_criteria']}-{cfg['max_criteria']}")
    if len(decision.task_title) > cfg["max_title_chars"]:
        score.warnings.append(f"title is {len(decision.task_title)} characters "
                              f"(under {cfg['max_title_chars']})")
    n = _sentences(decision.task_description)
    if n > cfg["max_description_sentences"]:
        score.warnings.append(f"description is {n} sentences "
                              f"(at most {cfg['max_description_sentences']})")
    for c in crits:
        vague = _has_phrase(c.text, cfg["vague_phrases"])
        if vague:
            score.warnings.append(f"{c.id}: vague wording {vague}; Guardian may only manage "
                                  "cannot_verify")
        if c.verification is Verification.TEST and not _CONCRETE.search(c.text):
            score.warnings.append(f"{c.id}: test criterion names no call or code to test")
    return score


# -- Standards (docs/reference-outputs/standards.md, standards/README.md) ---------------

_STD_ENUMS = {
    "status": {"draft", "active", "deprecated", "archived"},
    "scope": {"global", "department", "project"},
    "severity": {"critical", "major", "minor"},
    "source": {"user_confirmed", "system_defined", "learner_inferred"},
    "verification": {v.value for v in Verification},
}
_STD_ID = re.compile(r"^STD-(?P<letter>[GDP])-\d{3,}$")
_SCOPE_LETTER = {"global": "G", "department": "D", "project": "P"}
_FRONTMATTER = re.compile(r"\A---\n(?P<yaml>.*?)\n---\n(?P<body>.*)\Z", re.DOTALL)


def _split_standard(text: str) -> tuple[dict, dict[str, str]] | None:
    m = _FRONTMATTER.match(text.strip() + "\n")
    if not m:
        return None
    meta = yaml.safe_load(m["yaml"]) or {}
    sections: dict[str, str] = {}
    for part in re.split(r"^## ", m["body"], flags=re.MULTILINE)[1:]:
        head, _, content = part.partition("\n")
        sections[head.strip()] = content.strip()
    return meta, sections


@cache
def template_fields(template: Path = STANDARD_TEMPLATE) -> tuple[list[str], list[str]]:
    """Frontmatter fields and section names from the Standards template (single source)."""
    split = _split_standard(template.read_text(encoding="utf-8"))
    if split is None:
        raise ValueError(f"{template} has no frontmatter")
    meta, sections = split
    return list(meta), list(sections)


# Words dropped before comparing pass and fail conditions: negations and the and/or that
# flips with them ("X and Y" passes, "not X or Y" fails).
_NEGATION_WORDS = {"not", "no", "isn", "doesn", "t", "and", "or", "never"}


def _normalise(text: str) -> str:
    text = re.sub(r"[^\w\s]", " ", text.lower())
    return " ".join(w for w in text.split() if w not in _NEGATION_WORDS)


def score_standard(text: str) -> BenchmarkScore:
    score = _new("standards")
    cfg = load_benchmarks()["standards"]
    split = _split_standard(text)
    if split is None:
        score.gates.append("no YAML frontmatter between --- lines")
        return score
    meta, sections = split
    fields, template_sections = template_fields()
    score.metrics.update(words=_words(text), sections=len(sections))

    missing = [f for f in fields if f not in meta]
    if missing:
        score.gates.append(f"missing fields: {missing}")
    extra = sorted(set(meta) - set(fields))
    if extra:
        score.gates.append(f"fields not in the template: {extra}")
    for key, allowed in _STD_ENUMS.items():
        if key in meta and meta[key] not in allowed:
            score.gates.append(f"{key} '{meta[key]}' is not one of {sorted(allowed)}")
    applies = meta.get("applies_to") or []
    known = {"all"} | {d.value for d in Department}
    if not isinstance(applies, list) or not applies or set(applies) - known:
        score.gates.append(f"applies_to must be 'all' or departments, got {applies}")
    m = _STD_ID.match(str(meta.get("id", "")))
    if not m:
        score.gates.append(f"id '{meta.get('id')}' doesn't match STD-<G|D|P>-<number>")
    elif _SCOPE_LETTER.get(meta.get("scope")) not in (None, m["letter"]):
        score.gates.append(f"id letter {m['letter']} doesn't match scope '{meta.get('scope')}'")
    if meta.get("scope") == "project" and not meta.get("project"):
        score.gates.append("scope 'project' needs 'project' set")
    if meta.get("status") == "active" and not meta.get("guardian_validation"):
        score.gates.append("status 'active' needs a guardian_validation record (D-006)")
    if "required_evidence" in meta and not str(meta.get("required_evidence") or "").strip():
        score.gates.append("required_evidence is empty")

    for name in cfg["required_sections"]:
        if not sections.get(name):
            score.gates.append(f"section '{name}' is missing or empty")
    for name in template_sections:
        if name not in cfg["required_sections"] and not sections.get(name):
            score.warnings.append(f"section '{name}' is missing")
    passing, failing = sections.get("Passing conditions", ""), sections.get(
        "Failure conditions", "")
    if passing and failing and _normalise(passing) == _normalise(failing):
        score.gates.append("passing and failure conditions are the same sentence negated "
                           "(circular: nothing for Guardian to check)")

    requirement = sections.get("Requirement", "")
    n = _sentences(requirement)
    if n > cfg["max_requirement_sentences"]:
        score.warnings.append(f"Requirement has {n} sentences; one Standard, one requirement")
    long_words = _has_phrase(text, cfg["length_phrases"])
    if long_words:
        score.warnings.append(f"wording that rewards length: {long_words}")
    if meta.get("source") == "user_confirmed" and not re.search(
            r"[\"“”']", sections.get("Rationale", "")):
        score.warnings.append("source is user_confirmed but Rationale quotes no user words")
    if meta.get("status") == "draft" and meta.get("guardian_validation"):
        score.warnings.append("draft with a guardian_validation record: activate it?")
    return score


# -- Quality Rubric: graded answers (docs/reference-outputs/quality-rubric.md) -----------


def score_answer(text: str) -> BenchmarkScore:
    """The cheap, deterministic part of the rubric (F Clarity, G Presentation) only.

    A clean result does not mean a good answer: accuracy and usefulness need Guardian.
    """
    score = _new("quality-rubric")
    cfg = load_benchmarks()["answers"]
    words = _words(text)
    headings = len(re.findall(r"^#{1,6} ", text, flags=re.MULTILINE))
    score.metrics.update(words=words, headings=headings)
    first = text.strip().split("\n\n", 1)[0]
    pre = _has_phrase(first, cfg["preamble_phrases"])
    if pre:
        score.warnings.append(f"preamble instead of the answer: {pre}")
    last = text.strip().rsplit("\n\n", 1)[-1]
    sign = _has_phrase(last, cfg["signoff_phrases"])
    if sign:
        score.warnings.append(f"sign-off: {sign}")
    if headings and words < cfg["short_answer_words"]:
        score.warnings.append(f"{headings} headings in a {words}-word answer")
    if re.search(r"^#{1,6} (conclusion|summary|recap)\b", text, flags=re.MULTILINE | re.I):
        score.warnings.append("recap section repeats the answer")
    return score


# -- Quality Rubric: Guardian's review ----------------------------------------------------


class RubricReview(BaseModel):
    """The structured review Guardian writes for a Tier 3 grade (reference: best-review)."""

    model_config = ConfigDict(extra="forbid")
    rubric_version: str
    scores: dict[str, tuple[int, str]]
    critical_failures: list[str]
    agent_checks: dict[str, bool]
    grade: QualityGrade
    notes: list[str] = Field(default_factory=list)


def score_review(text: str, rubric: rubric_mod.Rubric | None = None) -> BenchmarkScore:
    score = _new("quality-rubric-review")
    rubric = rubric or rubric_mod.default_rubric()
    data = _parse_json(text, score)
    if data is None:
        score.gates.append("Guardian's review must be structured (GRD-2: a reason per score)")
        return score
    try:
        review = RubricReview.model_validate(data)
    except ValidationError as e:
        score.gates.extend(_schema_errors(e))
        return score
    score.metrics.update(chars=len(text), notes=len(review.notes))
    if review.rubric_version != rubric.version:
        score.gates.append(f"rubric_version {review.rubric_version} != current "
                           f"{rubric.version}")
    no_reason = [k for k, (_, why) in review.scores.items() if not why.strip()]
    if no_reason:
        score.gates.append(f"scores without a reason (GRD-2): {no_reason}")
    known_checks = {c.id for checks in rubric.agent_checks.values() for c in checks}
    unknown = sorted(set(review.agent_checks) - known_checks)
    if unknown:
        score.gates.append(f"unknown agent checks: {unknown}")
    try:
        expected = rubric_mod.grade({k: s for k, (s, _) in review.scores.items()},
                                    review.critical_failures, rubric)
    except ValueError as e:
        score.gates.append(f"scores don't fit rubric v{rubric.version}: {e}")
        return score
    score.metrics["weighted_score"] = expected.weighted_score
    if review.grade is not expected.grade:
        score.gates.append(f"grade '{review.grade}' but the scores give '{expected.grade}' "
                           "(rubric.grade)")
    below = [k for k, (s, _) in review.scores.items() if s < 5]
    if below and not review.notes:
        score.warnings.append(f"scores below 5 {below} but no actionable note")
    return score


# -- Model Evals (docs/reference-outputs/model-evals.md) ----------------------------------


class _E(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EvalTokens(_E):
    input: int = Field(ge=0)
    cache_read: int = Field(ge=0)
    output: int = Field(ge=0)
    cache_write: int = Field(default=0, ge=0)


class EvalCase(_E):
    case: str
    hard_gates_passed: bool
    tokens: EvalTokens
    cost_usd: float = Field(ge=0)
    failures: list[str]


class EvalSummary(_E):
    pass_rate: float = Field(ge=0, le=1)
    total_cost_usd: float = Field(ge=0)
    cost_per_pass_usd: float | None
    failure_types: dict[str, int]


class EvalRecord(_E):
    model: str
    effort: str
    operation: str
    suite: str = Field(pattern=r"^[\w.-]+@\d+$")
    prompt_version: str = Field(pattern=r"^[\w.-]+@\d+$")
    rubric_version: str
    run_at: str
    runs_per_case: int = Field(ge=1)
    cases: list[EvalCase] = Field(min_length=1)
    summary: EvalSummary
    status: str
    notes: list[str] = Field(default_factory=list)


def score_eval(text: str, pricing: PriceTable | None = None) -> BenchmarkScore:
    score = _new("model-evals")
    cfg = load_benchmarks()["model_evals"]
    tol = cfg["cost_tolerance_usd"]
    data = _parse_json(text, score)
    if data is None:
        return score
    try:
        rec = EvalRecord.model_validate(data)
    except ValidationError as e:
        score.gates.extend(_schema_errors(e))
        return score
    pricing = pricing or load_pricing()
    score.metrics.update(cases=len(rec.cases), chars=len(text))
    if pricing.get(rec.model) is None:
        score.gates.append(f"model '{rec.model}' isn't an exact id in config/pricing.yaml")
    if rec.status not in cfg["statuses"]:
        score.gates.append(f"status '{rec.status}' is not one of {cfg['statuses']}")

    failure_types: Counter[str] = Counter()
    for c in rec.cases:
        if c.hard_gates_passed == bool(c.failures):
            score.gates.append(f"{c.case}: hard_gates_passed={c.hard_gates_passed} but "
                               f"failures={c.failures}")
        failure_types.update(f.split(":", 1)[0] for f in c.failures)
        cost = pricing.cost(rec.model, input_tokens=c.tokens.input,
                            output_tokens=c.tokens.output,
                            cache_read_tokens=c.tokens.cache_read,
                            cache_write_tokens=c.tokens.cache_write)
        if cost is not None and abs(cost - c.cost_usd) > tol:
            score.gates.append(f"{c.case}: cost_usd {c.cost_usd} but the tokens price at "
                               f"{cost:.5f}")

    passes = sum(c.hard_gates_passed for c in rec.cases)
    total = sum(c.cost_usd for c in rec.cases)
    s = rec.summary
    if abs(s.pass_rate - passes / len(rec.cases)) > 1e-6:
        score.gates.append(f"pass_rate {s.pass_rate} but {passes}/{len(rec.cases)} passed")
    if abs(s.total_cost_usd - total) > tol:
        score.gates.append(f"total_cost_usd {s.total_cost_usd} but cases sum to {total:.5f}")
    expected_cpp = total / passes if passes else None
    if (expected_cpp is None) != (s.cost_per_pass_usd is None) or (
            expected_cpp is not None and abs(s.cost_per_pass_usd - expected_cpp) > tol):
        score.gates.append(f"cost_per_pass_usd {s.cost_per_pass_usd} but total/passes is "
                           f"{expected_cpp}")
    if dict(failure_types) != s.failure_types:
        score.gates.append(f"failure_types {s.failure_types} but cases give "
                           f"{dict(failure_types)}")
    if rec.runs_per_case < cfg["min_runs_for_spread"]:
        if rec.status == "qualified":
            score.gates.append(f"qualified on {rec.runs_per_case} run(s) per case; needs "
                               f"{cfg['min_runs_for_spread']} (D-012)")
        if not any("run" in n.lower() for n in rec.notes):
            score.warnings.append(f"{rec.runs_per_case} run(s) per case and no note saying "
                                  "it's below the spread threshold")
    return score


# -- dispatch ----------------------------------------------------------------------------

SCORERS: dict[str, Callable[[str], BenchmarkScore]] = {
    "criteria": score_criteria,
    "standard": score_standard,
    "answer": score_answer,
    "review": score_review,
    "eval": score_eval,
}


def score(scorer: str, text: str) -> BenchmarkScore:
    try:
        fn = SCORERS[scorer]
    except KeyError:
        raise ValueError(f"unknown benchmark '{scorer}'; one of {sorted(SCORERS)}") from None
    return fn(text)
