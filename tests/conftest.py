import subprocess
from pathlib import Path

import pytest

from ezra.contracts import (
    AcceptanceCriterion,
    Budget,
    Department,
    DeterministicCheck,
    Severity,
    TaskEnvelope,
    Verification,
)


def crit(cid: str, severity: Severity = Severity.MAJOR,
         verification: Verification = Verification.TEST,
         check: DeterministicCheck | None = None) -> AcceptanceCriterion:
    return AcceptanceCriterion(id=cid, text=f"criterion {cid}", severity=severity,
                               verification=verification, check=check)


def envelope(criteria: list[AcceptanceCriterion], task_id: str = "task_test01") -> TaskEnvelope:
    return TaskEnvelope(task_id=task_id, target_department=Department.CODE_JOE,
                        description="test task", acceptance_criteria=criteria,
                        budget=Budget(task_limit_usd=2.0, daily_limit_usd=10.0))


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.py").write_text("x = 1\n")
    (repo / "tests" / "acceptance").mkdir(parents=True)
    (repo / "tests" / "acceptance" / ".gitkeep").write_text("")
    ident = ["-c", "user.name=t", "-c", "user.email=t@t"]
    for cmd in (["init", "-q"], ["add", "-A"], [*ident, "commit", "-q", "-m", "init"]):
        subprocess.run(["git", *cmd], cwd=repo, check=True, capture_output=True)
    return repo
