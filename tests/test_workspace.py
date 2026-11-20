"""Path guard escapes and git worktree lifecycle."""

import os
import subprocess

import pytest

from ezra.code_joe.workspace import (
    PathEscapeError,
    PathGuard,
    ProtectedPathError,
    Role,
    changed_files,
    commit_all,
    create_worktree,
    is_within,
    remove_worktree,
)


@pytest.fixture
def root(tmp_path):
    r = tmp_path / "wt"
    (r / "pkg").mkdir(parents=True)
    (r / "tests" / "acceptance").mkdir(parents=True)
    (r / ".git").mkdir()
    (tmp_path / "outside.txt").write_text("secret")
    return r


@pytest.mark.parametrize("path", ["../outside.txt", "pkg/../../outside.txt", "/etc/passwd",
                                  "", "a\x00b"])
def test_escapes_rejected(root, path):
    with pytest.raises(PathEscapeError):
        PathGuard(root, Role.BUILDER).check_read(path)


def test_symlink_escape_rejected(root, tmp_path):
    os.symlink(tmp_path / "outside.txt", root / "pkg" / "link.txt")
    os.symlink(tmp_path, root / "dirlink")
    g = PathGuard(root, Role.BUILDER)
    for p in ("pkg/link.txt", "dirlink/outside.txt", "dirlink/new_file.py"):
        with pytest.raises(PathEscapeError):
            g.check_write(p)


@pytest.mark.parametrize("path", [".git/config", ".GIT/config", ".Git/hooks/pre-commit"])
def test_git_dir_rejected_in_any_case(root, path):
    with pytest.raises(PathEscapeError):
        PathGuard(root, Role.BUILDER).check_write(path)


def test_absolute_path_inside_root_allowed(root):
    g = PathGuard(root, Role.BUILDER)
    assert g.check_write(str(root / "pkg" / "a.py")) == (root / "pkg" / "a.py").resolve()


def test_builder_cannot_write_acceptance_tests(root):
    g = PathGuard(root, Role.BUILDER)
    assert g.check_write("pkg/mod.py")
    with pytest.raises(ProtectedPathError):
        g.check_write("tests/acceptance/test_ac1.py")
    with pytest.raises(ProtectedPathError):
        g.check_write("pkg/../tests/acceptance/test_ac1.py")


@pytest.mark.parametrize("path", ["Tests/Acceptance/test_ac1.py", "tests/ACCEPTANCE/x.py",
                                  "TESTS/acceptance/x.py"])
def test_builder_cannot_bypass_protection_with_case(root, path):
    # macOS filesystems are case-insensitive: these are the same directory.
    with pytest.raises(ProtectedPathError):
        PathGuard(root, Role.BUILDER).check_write(path)


def test_acceptance_lookalike_dir_is_not_protected(root):
    assert PathGuard(root, Role.BUILDER).check_write("tests/acceptance_helpers/x.py")


def test_builder_cannot_reach_acceptance_tests_through_symlink(root):
    os.symlink(root / "tests" / "acceptance", root / "pkg" / "sneaky")
    with pytest.raises(ProtectedPathError):
        PathGuard(root, Role.BUILDER).check_write("pkg/sneaky/test_ac1.py")


def test_tester_only_writes_acceptance_tests(root):
    g = PathGuard(root, Role.TESTER)
    assert g.check_write("tests/acceptance/test_ac1.py")
    with pytest.raises(ProtectedPathError):
        g.check_write("pkg/mod.py")


def test_reader_is_read_only(root):
    g = PathGuard(root, Role.READER)
    assert g.check_read("pkg")
    with pytest.raises(ProtectedPathError):
        g.check_write("pkg/mod.py")


def test_is_within(root):
    assert is_within(root, "pkg/a.py")
    assert not is_within(root, "../outside.txt")


def test_worktree_lifecycle(git_repo, tmp_path):
    wt = create_worktree(git_repo, "task_abc123", tmp_path / "worktrees")
    assert wt.branch == "ezra/task_abc123" and (wt.path / "app.py").exists()

    (wt.path / "app.py").write_text("x = 2\n")
    (wt.path / "new.py").write_text("y = 1\n")
    (wt.path / "with space.py").write_text("z = 1\n")
    assert changed_files(wt) == ["app.py", "new.py", "with space.py"]

    sha = commit_all(wt, "task work")
    assert sha and changed_files(wt) == ["app.py", "new.py", "with space.py"]  # vs base
    assert commit_all(wt, "nothing to do") is None

    # The original checkout is untouched: work lives only on the task branch.
    assert (git_repo / "app.py").read_text() == "x = 1\n"
    branches = subprocess.run(["git", "branch"], cwd=git_repo, capture_output=True,
                              text=True).stdout
    assert "ezra/task_abc123" in branches

    remove_worktree(wt, delete_branch=True)
    assert not wt.path.exists()


def test_unsafe_task_id_rejected(git_repo, tmp_path):
    with pytest.raises(ValueError):
        create_worktree(git_repo, "../evil", tmp_path / "worktrees")
