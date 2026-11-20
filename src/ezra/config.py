"""Loads config/*.yaml into typed objects."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict

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
