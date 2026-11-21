"""Loads the reference outputs in docs/reference-outputs/ as data.

Each reference file marks its examples with an HTML comment right before a fenced block:

    <!-- example: acceptance-criteria/best -->
    ```json
    { ... }
    ```

The marker names the file's kind and a label. Labels starting with "best" are outputs that
must pass every benchmark check; labels starting with "weak" must fail at least one. The
test suite holds the checks to that, so the reference files and the code can't drift apart.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from ezra.config import PROJECT_ROOT

REFERENCE_DIR = PROJECT_ROOT / "docs" / "reference-outputs"

# Which scorer judges each example. Quality-rubric holds two things: an answer that gets
# graded, and Guardian's review of it.
SCORERS = {
    "acceptance-criteria": "criteria",
    "standards": "standard",
    "model-evals": "eval",
    "quality-rubric": "answer",
}
REVIEW_SUFFIX = "-review"

_MARKER = re.compile(
    r"<!--\s*example:\s*(?P<kind>[a-z-]+)/(?P<label>[a-z-]+)\s*-->\s*\n"
    r"```(?P<lang>[a-z]*)\n(?P<body>.*?)\n```",
    re.DOTALL,
)


class ReferenceError(ValueError):
    pass


@dataclass(frozen=True)
class ReferenceExample:
    kind: str  # file stem, e.g. "acceptance-criteria"
    label: str  # e.g. "best", "weak", "best-review"
    lang: str  # fence language: json or markdown
    body: str
    source: Path

    @property
    def id(self) -> str:
        return f"{self.kind}/{self.label}"

    @property
    def expected_to_pass(self) -> bool:
        return self.label.startswith("best")

    @property
    def scorer(self) -> str:
        if self.label.endswith(REVIEW_SUFFIX):
            return "review"
        return SCORERS[self.kind]


def load_examples(reference_dir: Path = REFERENCE_DIR) -> list[ReferenceExample]:
    """Every marked example, in file order. Fails loudly on a malformed reference file."""
    examples: list[ReferenceExample] = []
    for path in sorted(reference_dir.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        found = list(_MARKER.finditer(text))
        if text.count("<!-- example:") != len(found):
            raise ReferenceError(f"{path.name}: an example marker isn't followed by a fenced block")
        for m in found:
            if m["kind"] != path.stem:
                raise ReferenceError(f"{path.name}: marker kind '{m['kind']}' != file name")
            if m["kind"] not in SCORERS:
                raise ReferenceError(f"{path.name}: no scorer for kind '{m['kind']}'")
            if not m["label"].startswith(("best", "weak")):
                raise ReferenceError(f"{path.name}: label '{m['label']}' must start with "
                                     "best or weak")
            examples.append(ReferenceExample(kind=m["kind"], label=m["label"], lang=m["lang"],
                                             body=m["body"], source=path))
    ids = [e.id for e in examples]
    if len(ids) != len(set(ids)):
        raise ReferenceError(f"duplicate example ids: {ids}")
    return examples


def example(example_id: str, reference_dir: Path = REFERENCE_DIR) -> ReferenceExample:
    for e in load_examples(reference_dir):
        if e.id == example_id:
            return e
    raise KeyError(example_id)
