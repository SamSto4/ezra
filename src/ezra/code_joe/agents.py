"""Code Joe's four roles. Each is one function around Gateway calls.

- plan       (Opus, one structured call): steps + the interface spec Builder and Tester share
- build      (Sonnet, tool loop): writes the code, can't read or write acceptance tests
- write_tests(Sonnet, tool loop): writes acceptance tests from criteria + interface only
- adjudicate (Opus, one structured call): after failing checks, is the code or the test wrong?

System prompts are static so they cache; task details go in the user message.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ezra.code_joe.tools import AgentError, AgentRun, FileTools, run_agent
from ezra.code_joe.workspace import ACCEPTANCE_TEST_DIR, Role
from ezra.contracts import (
    AcceptanceCriterion,
    Department,
    InterfaceItem,
    ModelInvocation,
    TaskEnvelope,
    Verification,
)

PLAN_MAX_TOKENS = 12_000
AGENT_MAX_TOKENS = 16_000
ADJUDICATE_MAX_TOKENS = 6_000
AGENT_MAX_TURNS = 14
CONTEXT_CHARS = 40_000


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Plan(_M):
    summary: str
    steps: list[str]
    interface: list[InterfaceItem]
    test_file: str = Field(description="tests/acceptance/test_<topic>.py")


class Adjudication(_M):
    fault: Literal["code", "tests", "both"]
    reason: str
    builder_instructions: str
    tester_instructions: str


def _strict(schema: dict) -> dict:
    """Structured outputs need additionalProperties: false on every object."""
    if isinstance(schema, dict):
        schema.pop("title", None)
        schema.pop("default", None)
        if schema.get("type") == "object":
            schema["additionalProperties"] = False
            schema["required"] = list(schema.get("properties", {}))
        for v in schema.values():
            _strict(v)
    elif isinstance(schema, list):
        for v in schema:
            _strict(v)
    return schema


def _schema(model: type[BaseModel]) -> dict:
    s = model.model_json_schema()
    defs = s.pop("$defs", {})
    text = json.dumps(s)
    for name, d in defs.items():  # inline $refs; these schemas aren't recursive
        text = text.replace(json.dumps({"$ref": f"#/$defs/{name}"}), json.dumps(d))
    return _strict(json.loads(text))


PLAN_SCHEMA = _schema(Plan)
ADJUDICATION_SCHEMA = _schema(Adjudication)


def criteria_text(criteria: list[AcceptanceCriterion], only: Verification | None = None) -> str:
    rows = [c for c in criteria if only is None or c.verification is only]
    return "\n".join(f"- {c.id} [{c.severity}, checked by {c.verification}"
                     f"{':' + c.check if c.check else ''}] {c.text}" for c in rows)


def interface_text(items: list[InterfaceItem]) -> str:
    return "\n".join(f"- {i.path}: `{i.signature}` ({i.symbol}). {i.description}"
                     for i in items)


def project_context(root: Path, include_acceptance: bool = False) -> str:
    """Tracked text files of the project, capped. Small projects fit whole."""
    # Tracked plus new untracked files, so Builder's new files are visible too.
    files = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"],
                           cwd=root, capture_output=True, text=True,
                           check=True).stdout.splitlines()
    out, used = [], 0
    for f in files:
        if not include_acceptance and f.startswith(ACCEPTANCE_TEST_DIR + "/"):
            continue
        p = root / f
        try:
            text = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        chunk = f"### {f}\n```\n{text}\n```\n"
        if used + len(chunk) > CONTEXT_CHARS:
            out.append(f"### {f}\n(omitted: context limit)\n")
            continue
        out.append(chunk)
        used += len(chunk)
    return "\n".join(out)


# -- plan ----------------------------------------------------------------------------

PLAN_SYSTEM = """\
You are Code Joe, the lead of Ezra's coding department. You plan a change to a small Python
project; you don't write the code. Two workers act on your plan in parallel:
- Builder implements it. Builder can't see or write the acceptance tests.
- Tester writes acceptance tests from the Acceptance Criteria and your interface spec only,
  without seeing Builder's code.

So the interface spec is the contract between them. List every public function, class or
module the tests will import: the file path, the symbol, its exact signature with types,
and one sentence on behavior. Use the import path the tests should use (for example a
package-level export). Keep the plan to the smallest change that meets the criteria; don't
add features. Don't put files under tests/acceptance/ in the interface.

test_file is the single acceptance test file Tester will write, under tests/acceptance/,
named test_<topic>.py.
"""


def make_plan(call: Callable[..., Any], env: TaskEnvelope, worktree: Path
              ) -> tuple[Plan, list[ModelInvocation]]:
    user = (f"## Task\n{env.description}\n\n## Acceptance criteria\n"
            f"{criteria_text(env.acceptance_criteria)}\n\n## Constraints\n"
            + ("\n".join(f"- {c}" for c in env.constraints) or "- none")
            + f"\n\n## Project files\n{project_context(worktree)}")
    resp = call(operation="code_joe.plan", department=Department.CODE_JOE, system=PLAN_SYSTEM,
                messages=[{"role": "user", "content": user}], max_tokens=PLAN_MAX_TOKENS,
                task_id=env.task_id,
                output_format={"type": "json_schema", "schema": PLAN_SCHEMA})
    invs = [resp.invocation]
    if resp.truncated or not resp.text.strip():
        raise AgentError("plan was cut off or empty", invs)
    try:
        plan = Plan.model_validate_json(resp.text)
    except ValidationError as e:
        raise AgentError(f"plan didn't match its schema: {e}", invs) from e
    tf = plan.test_file
    if not (tf.startswith(ACCEPTANCE_TEST_DIR + "/") and Path(tf).name.startswith("test_")
            and tf.endswith(".py")):
        plan = plan.model_copy(update={"test_file": f"{ACCEPTANCE_TEST_DIR}/test_task.py"})
    return plan, invs


# -- build ---------------------------------------------------------------------------

BUILD_SYSTEM = """\
You are Builder in Ezra's coding department. Implement the plan in the project using the
file tools. Rules:
- Implement exactly the interface spec: same paths, names and signatures. Tests written by
  someone else will import them.
- Read a file before changing it, and write complete files.
- Keep existing behavior working. No new dependencies.
- You can't read or write tests/acceptance/; acceptance tests are someone else's job. You
  may add or update other tests if useful.
- You can't run code. Reason carefully about edge cases in the criteria instead.
When you're done, reply with two or three sentences on what you changed. Don't call tools
in that final reply.
"""


def build(call: Callable[..., Any], env: TaskEnvelope, plan: Plan, worktree: Path,
          feedback: str = "") -> AgentRun:
    user = (f"## Task\n{env.description}\n\n## Plan\n{plan.summary}\n"
            + "\n".join(f"{i}. {s}" for i, s in enumerate(plan.steps, 1))
            + f"\n\n## Interface spec\n{interface_text(plan.interface)}"
            f"\n\n## Acceptance criteria\n{criteria_text(env.acceptance_criteria)}"
            "\n\n## Constraints\n" + ("\n".join(f"- {c}" for c in env.constraints) or "- none"))
    if feedback:
        user += f"\n\n## Fix needed (your previous attempt failed checks)\n{feedback}"
    return run_agent(call, operation="builder.implement", department=Department.BUILDER,
                     system=BUILD_SYSTEM, user=user, tools=FileTools(worktree, Role.BUILDER),
                     max_turns=AGENT_MAX_TURNS, max_tokens=AGENT_MAX_TOKENS,
                     task_id=env.task_id)


# -- write tests ----------------------------------------------------------------------

TEST_SYSTEM = """\
You are Tester in Ezra's coding department. Write pytest acceptance tests that check the
Acceptance Criteria, using the file tools. Rules:
- Write only the test file you are given (under tests/acceptance/). You can read tests/ to
  match the project's style; you can't read the implementation, by design.
- Use only the interface spec to know what to import and call.
- Every criterion listed needs at least one test whose name contains its id in lowercase,
  e.g. test_ac1_counts_two_sentences for AC1. Never put another criterion's id in a test
  name (no test_ac1_and_ac2).
- Test exactly what the criterion says, with the inputs and outputs it names. Don't test
  behavior the criteria don't mention.
- Tests must be deterministic: no network, no sleeps, no randomness.
When you're done, reply with one or two sentences. Don't call tools in that final reply.
"""


def write_tests(call: Callable[..., Any], env: TaskEnvelope, plan: Plan, worktree: Path,
                feedback: str = "") -> AgentRun:
    user = (f"## Test file to write\n{plan.test_file}\n\n## Interface spec\n"
            f"{interface_text(plan.interface)}\n\n## Criteria to test\n"
            f"{criteria_text(env.acceptance_criteria, only=Verification.TEST)}")
    if feedback:
        user += f"\n\n## Fix needed (your previous tests were judged wrong)\n{feedback}"
    return run_agent(call, operation="tester.write_tests", department=Department.TESTER,
                     system=TEST_SYSTEM, user=user, tools=FileTools(worktree, Role.TESTER),
                     max_turns=AGENT_MAX_TURNS, max_tokens=AGENT_MAX_TOKENS,
                     task_id=env.task_id)


# -- adjudicate --------------------------------------------------------------------------

ADJUDICATE_SYSTEM = """\
You are Code Joe. Checks failed after Builder and Tester finished. Decide who must fix it:
- "code": the implementation doesn't do what a criterion says.
- "tests": a test checks something the criteria don't say, has a bug, or misuses the
  interface spec.
- "both": each has a real problem.
The Acceptance Criteria are the source of truth; neither the code nor the tests are. Give
each party you blame short, concrete instructions. Leave the other party's instructions
empty.
"""


def adjudicate(call: Callable[..., Any], env: TaskEnvelope, plan: Plan, worktree: Path,
               failures: str) -> tuple[Adjudication, list[ModelInvocation]]:
    user = (f"## Acceptance criteria\n{criteria_text(env.acceptance_criteria)}\n\n"
            f"## Interface spec\n{interface_text(plan.interface)}\n\n## Failing checks\n"
            f"{failures}\n\n## Project files now\n"
            f"{project_context(worktree, include_acceptance=True)}")
    resp = call(operation="code_joe.adjudicate", department=Department.CODE_JOE,
                system=ADJUDICATE_SYSTEM, messages=[{"role": "user", "content": user}],
                max_tokens=ADJUDICATE_MAX_TOKENS, task_id=env.task_id,
                output_format={"type": "json_schema", "schema": ADJUDICATION_SCHEMA})
    invs = [resp.invocation]
    try:
        return Adjudication.model_validate_json(resp.text), invs
    except ValidationError as e:
        raise AgentError(f"adjudication didn't match its schema: {e}", invs) from e
