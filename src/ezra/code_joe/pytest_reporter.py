"""A tiny pytest plugin loaded into sandboxed runs with `-p ezra.code_joe.pytest_reporter`.

It writes one JSON line per test outcome (with pytest's own node id) and per collection
error to the file named by EZRA_PYTEST_REPORT. Guardian Tier 1 matches criteria against
these exact node ids, so we don't reconstruct them from JUnit class names.
"""

from __future__ import annotations

import json
import os

_PATH = os.environ.get("EZRA_PYTEST_REPORT")


def _write(record: dict) -> None:
    if _PATH:
        with open(_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")


def _short(report) -> str:
    text = getattr(report, "longreprtext", "") or ""
    return text[-1500:]


def pytest_runtest_logreport(report):
    if report.when == "call" or (report.when == "setup" and not report.passed):
        if report.passed:
            outcome = "passed"
        elif report.skipped:
            outcome = "skipped"
        else:
            outcome = "failed" if report.when == "call" else "error"
        _write({"nodeid": report.nodeid, "outcome": outcome, "message": _short(report)})


def pytest_collectreport(report):
    if report.failed:
        _write({"nodeid": report.nodeid or "<collection>", "outcome": "error",
                "message": _short(report)})
