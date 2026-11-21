"""Loads config/*.yaml into typed objects."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from ezra.contracts import Limits

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = PROJECT_ROOT / "config"
DATA_DIR = PROJECT_ROOT / ".ezra"
# Phase 1: Code Joe works only on the playground repo (docs/phase-1-plan.md §6).
PLAYGROUND_DIR = PROJECT_ROOT / "playground"


class OperationRoute(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model: str
    effort: str


class RoutingTable(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: str
    operations: dict[str, OperationRoute]

    def route(self, operation: str) -> OperationRoute:
        try:
            return self.operations[operation]
        except KeyError:
            raise KeyError(f"No route configured for operation '{operation}'") from None


def _load_yaml(path: Path) -> dict:
    with path.open() as f:
        return yaml.safe_load(f) or {}


def load_limits(config_dir: Path = CONFIG_DIR) -> Limits:
    return Limits.model_validate(_load_yaml(config_dir / "limits.yaml"))


def load_routing(config_dir: Path = CONFIG_DIR) -> RoutingTable:
    return RoutingTable.model_validate(_load_yaml(config_dir / "routing.yaml"))


class LearningConfig(BaseModel):
    """config/learning.yaml: progressive learning settings (D-012)."""

    model_config = ConfigDict(extra="forbid")
    version: str = "lessons-v1"
    memory: Literal["off", "lessons", "frozen"] = "off"
    inject_into: list[str] = Field(default_factory=lambda: [
        "code_joe.plan", "builder.implement", "tester.write_tests"])
    retrieval_token_cap: int = Field(default=700, ge=0)
    max_active_per_operation: int = Field(default=25, ge=1)
    retire_margin: int = Field(default=2, ge=1)
    merge_similarity: float = Field(default=0.6, gt=0, le=1)
    max_lessons_per_task: int = Field(default=3, ge=0, le=3)


def load_learning(config_dir: Path = CONFIG_DIR) -> LearningConfig:
    path = config_dir / "learning.yaml"
    return LearningConfig.model_validate(_load_yaml(path)) if path.exists() else LearningConfig()
