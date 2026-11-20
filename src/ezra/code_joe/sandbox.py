"""Sandboxed test and lint runs. No model is involved here.

Running tests means running Builder's code, so each run:
- gets an allowlisted environment (no API keys, no shell profile) and a throwaway HOME,
- runs with cwd set to the worktree and the worktree's own pyproject.toml passed explicitly,
  so Ezra's own config is never picked up,
- writes no caches into the worktree,
- is killed as a whole process group if it passes the timeout.

Residual risk (docs/phase-1-plan.md §4): the code still runs with the user's file
permissions. Phase 1 targets the playground repo only; a container is a later hardening step.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from ezra.contracts import CommandRun, TestCaseResult

EXCERPT_CHARS = 4000
_SAFE_PATH = "/usr/bin:/bin:/usr/sbin:/sbin"


def scrubbed_env(home: Path, extra: dict[str, str] | None = None) -> dict[str, str]:
    """Built from an allowlist, never by copying os.environ."""
    env = {
        "PATH": _SAFE_PATH,
        "HOME": str(home),
        "TMPDIR": str(home),
        "LANG": "en_US.UTF-8",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONHASHSEED": "0",
        "NO_COLOR": "1",
    }
    env.update(extra or {})
    return env


def _run(cmd: list[str], cwd: Path, env: dict[str, str], timeout: int
         ) -> tuple[int | None, bool, str, float]:
    started = time.monotonic()
    proc = subprocess.Popen(cmd, cwd=cwd, env=env, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, start_new_session=True)
    try:
        out, _ = proc.communicate(timeout=timeout)
        return proc.returncode, False, out, time.monotonic() - started
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)  # the whole group, including child processes
        out, _ = proc.communicate()
        return None, True, out or "", time.monotonic() - started


def _excerpt(text: str) -> str:
    return text if len(text) <= EXCERPT_CHARS else "…" + text[-EXCERPT_CHARS:]


def run_pytest(worktree: Path, timeout: int, paths: list[str] | None = None) -> CommandRun:
    worktree = Path(worktree).resolve()
    with tempfile.TemporaryDirectory(prefix="ezra-sandbox-") as tmp:
        home = Path(tmp)
        report = home / "report.jsonl"
        cmd = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
               "--continue-on-collection-errors",
               "-p", "ezra.code_joe.pytest_reporter", "--rootdir", str(worktree)]
        if (worktree / "pyproject.toml").exists():
            cmd += ["-c", str(worktree / "pyproject.toml")]
        cmd += paths or []
        env = scrubbed_env(home, {"EZRA_PYTEST_REPORT": str(report)})
        code, timed_out, out, secs = _run(cmd, worktree, env, timeout)
        cases = []
        if report.exists():
            for line in report.read_text().splitlines():
                rec = json.loads(line)
                cases.append(TestCaseResult(name=rec["nodeid"], outcome=rec["outcome"],
                                            message=rec.get("message", "")))
    return CommandRun(command="pytest", exit_code=code, timed_out=timed_out,
                      duration_seconds=round(secs, 2), output_excerpt=_excerpt(out), cases=cases)


def run_ruff(worktree: Path, timeout: int) -> CommandRun:
    worktree = Path(worktree).resolve()
    ruff = Path(sys.executable).parent / "ruff"
    pyproject = worktree / "pyproject.toml"
    uses_ruff_config = pyproject.exists() and "[tool.ruff" in pyproject.read_text()
    cmd = [str(ruff), "check", "--no-cache", "--output-format", "concise"]
    cmd += ["--config", str(pyproject)] if uses_ruff_config else ["--isolated"]
    cmd.append(".")
    with tempfile.TemporaryDirectory(prefix="ezra-sandbox-") as tmp:
        code, timed_out, out, secs = _run(cmd, worktree, scrubbed_env(Path(tmp)), timeout)
    return CommandRun(command="ruff", exit_code=code, timed_out=timed_out,
                      duration_seconds=round(secs, 2), output_excerpt=_excerpt(out))
