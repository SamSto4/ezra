"""Benchmarks: score agent outputs against the reference outputs in docs/reference-outputs/.

- reference.py loads the marked best/weak examples from the reference files.
- scorers.py holds one deterministic scorer per kind of output.
- config/benchmarks.yaml holds the thresholds (GUESS-marked where not yet measured).
"""

from ezra.benchmarks.reference import ReferenceExample, load_examples
from ezra.benchmarks.scorers import BenchmarkScore, score

__all__ = ["BenchmarkScore", "ReferenceExample", "load_examples", "score"]
