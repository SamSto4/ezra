"""A fake Anthropic client shaped like the parts the Gateway uses. No network."""

from __future__ import annotations

from types import SimpleNamespace as NS
from typing import Any


def attempt(model=None, kind="message", input_tokens=10, output_tokens=5, cache_read=0,
            cache_write=0):
    return NS(type=kind, model=model, input_tokens=input_tokens, output_tokens=output_tokens,
              cache_read_input_tokens=cache_read, cache_creation_input_tokens=cache_write)


def message(text="Four.", *, model="claude-sonnet-5-5", stop_reason="end_turn",
            iterations=None, input_tokens=10, output_tokens=5, cache_read=0, cache_write=0,
            stop_details=None):
    usage = NS(input_tokens=input_tokens, output_tokens=output_tokens,
               cache_read_input_tokens=cache_read, cache_creation_input_tokens=cache_write,
               iterations=iterations)
    content = [NS(type="thinking", thinking=""), NS(type="text", text=text)] if text else []
    return NS(model=model, stop_reason=stop_reason, usage=usage, content=content,
              stop_details=stop_details)


class _Stream:
    def __init__(self, msg):
        self._msg = msg
        self.request_id = "req_fake123"

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        return self._msg


class FakeMessages:
    def __init__(self, replies: list[Any], count: int = 100, count_error: Exception | None = None):
        self.replies = list(replies)
        self.count = count
        self.count_error = count_error
        self.stream_calls: list[dict[str, Any]] = []
        self.count_calls: list[dict[str, Any]] = []

    def count_tokens(self, **kwargs):
        self.count_calls.append(kwargs)
        if self.count_error:
            raise self.count_error
        return NS(input_tokens=self.count)

    def stream(self, **kwargs):
        self.stream_calls.append(kwargs)
        reply = self.replies.pop(0)
        if isinstance(reply, BaseException):
            raise reply
        return _Stream(reply)


class FakeClient:
    def __init__(self, replies: list[Any] | None = None, **kwargs):
        self.messages = FakeMessages(replies or [message()], **kwargs)
        self.beta = NS(messages=self.messages)


# -- scripted client for Code Joe: one reply queue per role (Builder and Tester run in
# parallel threads, so a single shared queue would hand out replies in random order) ------

import threading  # noqa: E402


def tool_turn(*calls, stop_reason="tool_use", input_tokens=200, output_tokens=80):
    """calls: (name, input) pairs -> one assistant turn that asks for those tools."""
    blocks = [NS(type="tool_use", id=f"tu_{i}_{name}", name=name, input=inp)
              for i, (name, inp) in enumerate(calls)]
    usage = NS(input_tokens=input_tokens, output_tokens=output_tokens,
               cache_read_input_tokens=0, cache_creation_input_tokens=0, iterations=None)
    return NS(model="claude-sonnet-5-5", stop_reason=stop_reason, usage=usage,
              content=blocks, stop_details=None)


class ScriptedMessages:
    def __init__(self, scripts: dict[str, list[Any]], count: int = 100,
                 counts: dict[str, int] | None = None):
        self.scripts = {k: list(v) for k, v in scripts.items()}
        self.count = count
        self.counts = counts or {}  # per system prompt: steers worst-case estimates
        self.lock = threading.Lock()
        self.calls: list[dict[str, Any]] = []

    def count_tokens(self, **kwargs):
        return NS(input_tokens=self.counts.get(kwargs["system"][0]["text"], self.count))

    def stream(self, **kwargs):
        key = kwargs["system"][0]["text"]
        with self.lock:
            self.calls.append(kwargs)
            queue = self.scripts.get(key)
            if not queue:
                raise AssertionError(f"no scripted reply left for: {key[:60]!r}")
            reply = queue.pop(0)
        if isinstance(reply, BaseException):
            raise reply
        return _Stream(reply)


class ScriptedClient:
    def __init__(self, scripts: dict[str, list[Any]], **kwargs):
        self.messages = ScriptedMessages(scripts, **kwargs)
        self.beta = NS(messages=self.messages)
