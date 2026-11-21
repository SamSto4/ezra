import doctest
import hashlib
from pathlib import Path

import minitext

ROOT = Path(__file__).resolve().parents[2]
UNCHANGED = {
    "core.py": "bd7269e4783341cf2af7139764bdbad5f47e0da0aee7a4c9da804aa28e7ffbfe",
    "stats.py": "398e18650d9fc1af972e1d31a9065ae7f388b1b905101a353b6a92fef84074ea",
}


def test_readme_names_every_public_function():
    text = (ROOT / "README.md").read_text()
    missing = [name for name in minitext.__all__ if name not in text]
    assert not missing, missing


def test_readme_examples_are_true():
    text = (ROOT / "README.md").read_text()
    globs = {name: getattr(minitext, name) for name in minitext.__all__}
    test = doctest.DocTestParser().get_doctest(text, globs, "README", "README.md", 0)
    assert len(test.examples) >= len(minitext.__all__)
    result = doctest.DocTestRunner(optionflags=doctest.NORMALIZE_WHITESPACE).run(test)
    assert result.failed == 0


def test_code_unchanged():
    for name, digest in UNCHANGED.items():
        data = (ROOT / "minitext" / name).read_bytes()
        assert hashlib.sha256(data).hexdigest() == digest, name
