"""Code Joe's workspace: one git worktree per task, plus a path guard for every file tool.

Safety rails (docs/phase-1-plan.md §4):
- Every path is resolved (following symlinks) and must stay inside the worktree.
- Nothing may touch the .git directory.
- Builder may not write Tester's acceptance tests; Tester may write only those.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

ACCEPTANCE_TEST_DIR = "tests/acceptance"
# Files that change how tests are collected or run. Builder may not write them, so it can't
# make the frozen acceptance tests skip or pass without checking anything (D-015).
TEST_CONFIG_ANYWHERE = frozenset({"conftest.py"})
TEST_CONFIG_AT_ROOT = frozenset({"pyproject.toml", "pytest.ini", "setup.cfg", "tox.ini"})
_TASK_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_GIT_IDENTITY = ["-c", "user.name=Ezra", "-c", "user.email=ezra@localhost"]


class PathEscapeError(PermissionError):
    """The path resolves outside the worktree, or into .git."""


class ProtectedPathError(PermissionError):
    """The path is inside the worktree but this role may not write it."""


class Role(StrEnum):
    BUILDER = "builder"
    TESTER = "tester"
    READER = "reader"  # Code Joe planning, Guardian: read-only


def is_within(root: Path | str, path: Path | str) -> bool:
    """True if `path` (relative to root, or absolute) resolves inside root after symlinks."""
    root_r = Path(root).resolve()
    p = Path(path)
    candidate = p if p.is_absolute() else root_r / p
    resolved = candidate.resolve()
    return resolved == root_r or resolved.is_relative_to(root_r)


class PathGuard:
    def __init__(self, root: Path | str, role: Role):
        self.root = Path(root).resolve()
        self.role = role

    def _resolve(self, path: str) -> Path:
        if not path or "\x00" in path:
            raise PathEscapeError(f"invalid path: {path!r}")
        p = Path(path)
        candidate = p if p.is_absolute() else self.root / p
        resolved = candidate.resolve()
        if not (resolved == self.root or resolved.is_relative_to(self.root)):
            raise PathEscapeError(f"{path!r} resolves outside the worktree")
        if self._folded_parts(resolved)[:1] == (".git",):
            raise PathEscapeError(f"{path!r} is inside .git")
        return resolved

    def _folded_parts(self, resolved: Path) -> tuple[str, ...]:
        # macOS and Windows filesystems are usually case-insensitive, so compare case-folded:
        # otherwise ".GIT/config" or "Tests/Acceptance/x.py" would slip past the checks.
        return tuple(part.casefold() for part in resolved.relative_to(self.root).parts)

    def relative(self, resolved: Path) -> str:
        return resolved.relative_to(self.root).as_posix()

    def check_read(self, path: str) -> Path:
        return self._resolve(path)

    def check_write(self, path: str) -> Path:
        resolved = self._resolve(path)
        if resolved == self.root:
            raise ProtectedPathError("cannot write the worktree root itself")
        acceptance_parts = tuple(Path(ACCEPTANCE_TEST_DIR).parts)
        parts = self._folded_parts(resolved)
        in_acceptance = len(parts) > len(acceptance_parts) and \
            parts[: len(acceptance_parts)] == acceptance_parts
        if self.role is Role.READER:
            raise ProtectedPathError(f"role {self.role} is read-only")
        if self.role is Role.BUILDER and in_acceptance:
            raise ProtectedPathError(f"Builder may not write acceptance tests: {path!r}")
        if self.role is Role.BUILDER and parts and (
                parts[-1] in TEST_CONFIG_ANYWHERE
                or (len(parts) == 1 and parts[0] in TEST_CONFIG_AT_ROOT)):
            raise ProtectedPathError(f"Builder may not change test configuration: {path!r}")
        if self.role is Role.TESTER and not in_acceptance:
            raise ProtectedPathError(f"Tester may only write under {ACCEPTANCE_TEST_DIR}/")
        return resolved


# ---------------------------------------------------------------------------
# Git worktrees
# ---------------------------------------------------------------------------


def _git(*args: str, cwd: Path) -> str:
    proc = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout


@dataclass(frozen=True)
class Worktree:
    repo: Path
    path: Path
    branch: str
    base_commit: str


def create_worktree(repo: Path | str, task_id: str, worktrees_dir: Path | str) -> Worktree:
    if not _TASK_ID_RE.match(task_id):
        raise ValueError(f"unsafe task id for a branch name: {task_id!r}")
    repo = Path(repo).resolve()
    base = _git("rev-parse", "HEAD", cwd=repo).strip()
    branch = f"ezra/{task_id}"
    path = Path(worktrees_dir).resolve() / task_id
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() or _git("branch", "--list", branch, cwd=repo).strip():
        # Left over from a setup step that was cut off before it was saved: nothing has run
        # in it yet (setup is the first step), so start it again cleanly. Never throw away a
        # branch that already holds commits.
        if _git("branch", "--list", branch, cwd=repo).strip() and \
                _git("rev-list", "--count", f"{base}..{branch}", cwd=repo).strip() != "0":
            raise RuntimeError(f"branch {branch} already has commits; not replacing it")
        if path.exists():
            _git("worktree", "remove", "--force", str(path), cwd=repo)
        _git("worktree", "prune", cwd=repo)
        if _git("branch", "--list", branch, cwd=repo).strip():
            _git("branch", "-D", branch, cwd=repo)
    _git("worktree", "add", "-b", branch, str(path), base, cwd=repo)
    return Worktree(repo=repo, path=path, branch=branch, base_commit=base)


def changed_files(wt: Worktree) -> list[str]:
    """Files changed since the base commit, committed or not, relative to the worktree."""
    committed = _git("diff", "--name-only", wt.base_commit, "HEAD", cwd=wt.path).splitlines()
    status = _git("status", "--porcelain=v1", "-uall", cwd=wt.path).splitlines()
    uncommitted = [line[3:].split(" -> ")[-1].strip('"') for line in status if line.strip()]
    return sorted(set(committed) | set(uncommitted))


def commit_all(wt: Worktree, message: str) -> str | None:
    """Commit everything on the task branch. Never pushes, never merges (D-009)."""
    _git("add", "-A", cwd=wt.path)
    if not _git("status", "--porcelain", cwd=wt.path).strip():
        return None
    _git(*_GIT_IDENTITY, "commit", "-q", "-m", message, cwd=wt.path)
    return _git("rev-parse", "HEAD", cwd=wt.path).strip()


def remove_worktree(wt: Worktree, delete_branch: bool = False) -> None:
    _git("worktree", "remove", "--force", str(wt.path), cwd=wt.repo)
    if delete_branch:
        _git("branch", "-D", wt.branch, cwd=wt.repo)
