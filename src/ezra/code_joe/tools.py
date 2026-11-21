"""File tools for Builder and Tester, and the agent loop that runs them.

The models get file tools only: list, read, write. No shell. Every path goes through the
PathGuard (M1), and each role also has a read scope: Tester may read only tests/, so it
writes acceptance tests without seeing Builder's code, and Builder may not read
tests/acceptance/, so it can't fit its code to the tests.

The loop is written by hand instead of using the SDK's tool runner so that every model
call still goes through the Gateway: budget check, reservation and logging per turn.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

from ezra.code_joe.workspace import ACCEPTANCE_TEST_DIR, PathGuard, Role
from ezra.contracts import ModelInvocation

MAX_READ_CHARS = 30_000
MAX_LIST = 300


class AgentError(Exception):
    def __init__(self, message: str, invocations: list[ModelInvocation]):
        super().__init__(message)
        self.invocations = invocations


# -- tool inputs, validated before anything runs ---------------------------------------


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ListIn(_In):
    path: str = "."


class ReadIn(_In):
    path: str


class WriteIn(_In):
    path: str
    content: str


_INPUTS = {"list_files": ListIn, "read_file": ReadIn, "write_file": WriteIn}


def tool_definitions() -> list[dict[str, Any]]:
    """Streaming requests with client tools set eager_input_streaming, so inputs are
    validated here (pydantic) instead of on the server."""
    return [
        {"name": "list_files", "eager_input_streaming": True,
         "description": "List files under a directory of the project (relative path). "
                        "Call this first to see what exists.",
         "input_schema": {"type": "object", "properties": {"path": {"type": "string"}},
                          "additionalProperties": False}},
        {"name": "read_file", "eager_input_streaming": True,
         "description": "Read a text file of the project (relative path). Read a file "
                        "before you change it.",
         "input_schema": {"type": "object", "properties": {"path": {"type": "string"}},
                          "required": ["path"], "additionalProperties": False}},
        {"name": "write_file", "eager_input_streaming": True,
         "description": "Create or overwrite a project file with the full new content. "
                        "Always send the complete file, not a fragment.",
         "input_schema": {"type": "object",
                          "properties": {"path": {"type": "string"},
                                         "content": {"type": "string"}},
                          "required": ["path", "content"], "additionalProperties": False}},
    ]


class FileTools:
    def __init__(self, root: Path, role: Role):
        self.root = Path(root).resolve()
        self.guard = PathGuard(self.root, role)
        self.role = role
        self.written: list[str] = []

    def _readable(self, rel: str) -> bool:
        parts = Path(rel).as_posix().casefold()
        if self.role is Role.TESTER:
            return parts == "tests" or parts.startswith("tests/") or parts == "."
        if self.role is Role.BUILDER:
            acc = ACCEPTANCE_TEST_DIR.casefold()
            return not (parts == acc or parts.startswith(acc + "/"))
        return True

    def run(self, name: str, raw_input: Any) -> tuple[str, bool]:
        """Returns (result text, is_error). Never raises for bad input or blocked paths."""
        model = _INPUTS.get(name)
        if model is None:
            return f"Unknown tool '{name}'.", True
        try:
            args = model.model_validate(raw_input)
        except ValidationError:
            return json.dumps({"INVALID_JSON": json.dumps(raw_input, default=str)}), True
        try:
            if name == "list_files":
                return self._list(args.path), False
            if name == "read_file":
                return self._read(args.path), False
            return self._write(args.path, args.content), False
        except PermissionError as e:
            return f"Not allowed: {e}", True
        except (OSError, UnicodeDecodeError) as e:
            return f"Error: {e}", True

    def _list(self, path: str) -> str:
        target = self.guard.check_read(path)
        if not self._readable(self.guard.relative(target)):
            raise PermissionError(f"{self.role} may not read {path}")
        if not target.is_dir():
            return f"{path} is not a directory."
        files = sorted(self.guard.relative(p) for p in target.rglob("*")
                       if p.is_file() and ".git" not in p.relative_to(self.root).parts
                       and "__pycache__" not in p.parts
                       and self._readable(self.guard.relative(p)))
        return "\n".join(files[:MAX_LIST]) or "(no files)"

    def _read(self, path: str) -> str:
        target = self.guard.check_read(path)
        if not self._readable(self.guard.relative(target)):
            raise PermissionError(f"{self.role} may not read {path}")
        text = target.read_text(encoding="utf-8")
        return text if len(text) <= MAX_READ_CHARS else text[:MAX_READ_CHARS] + "\n…(cut)"

    def _write(self, path: str, content: str) -> str:
        target = self.guard.check_write(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        rel = self.guard.relative(target)
        if rel not in self.written:
            self.written.append(rel)
        return f"Wrote {rel} ({len(content)} characters)."


# -- the agent loop ----------------------------------------------------------------------


@dataclass
class AgentRun:
    summary: str
    turns: int
    invocations: list[ModelInvocation] = field(default_factory=list)
    files_written: list[str] = field(default_factory=list)


def run_agent(call: Callable[..., Any], *, operation: str, department: Any, system: str,
              user: str, tools: FileTools, max_turns: int, max_tokens: int,
              task_id: str, context: list[tuple[str, str]] | None = None) -> AgentRun:
    """`call` is Gateway.call (or a wrapper that handles HOLDs). Loops until the model
    stops asking for tools, or fails clearly at the turn cap."""
    messages: list[dict[str, Any]] = [{"role": "user", "content": user}]
    invocations: list[ModelInvocation] = []
    defs = tool_definitions()
    for turn in range(1, max_turns + 1):
        resp = call(operation=operation, department=department, system=system,
                    messages=messages, max_tokens=max_tokens, task_id=task_id, tools=defs,
                    cache_conversation=True, context=context)
        invocations.append(resp.invocation)
        msg = resp.message
        if resp.invocation.fallback_used:
            # A fallback model can't read this model's thinking blocks, so continuing the
            # conversation is unreliable. Fail this agent run clearly instead.
            raise AgentError(f"{operation}: the model fell back mid-task", invocations)
        tool_uses = [b for b in msg.content if getattr(b, "type", None) == "tool_use"]
        messages.append({"role": "assistant", "content": msg.content})  # echoed unchanged
        if not tool_uses:
            if resp.truncated:
                raise AgentError(f"{operation}: answer cut off at the length limit",
                                 invocations)
            return AgentRun(summary=resp.text.strip(), turns=turn, invocations=invocations,
                            files_written=tools.written)
        results = []
        for block in tool_uses:
            if resp.truncated:
                # The input may be cut off mid-file: never run it.
                text, is_error = ("Your message was cut off, so this call was not run. "
                                  "Write smaller files, one per call."), True
            else:
                text, is_error = tools.run(block.name, block.input)
            results.append({"type": "tool_result", "tool_use_id": block.id,
                            "content": text, **({"is_error": True} if is_error else {})})
        messages.append({"role": "user", "content": results})  # one message, every result
    raise AgentError(f"{operation}: stopped at the {max_turns}-turn cap", invocations)
