"""Token prices and cost math for the Model Gateway.

Two numbers per call:
- worst_case(): a conservative estimate of what a call could cost, checked against the budget
  *before* it runs. Not a strict ceiling: a request declined mid-answer and then rescued by a
  fallback model bills both attempts. Refusals are rare, so one attempt is priced.
- cost(): what one attempt actually cost, from the token counts the API reports.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from ezra.config import CONFIG_DIR, _load_yaml

PER_TOKEN = 1_000_000


class ModelPrice(BaseModel):
    model_config = ConfigDict(extra="forbid")
    input: float
    output: float
    cache_read: float
    cache_write: float
    fallbacks: list[str] = Field(default_factory=list)


class PriceTable(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: str
    models: dict[str, ModelPrice]

    def get(self, model: str) -> ModelPrice | None:
        return self.models.get(model)

    def require(self, model: str) -> ModelPrice:
        price = self.get(model)
        if price is None:
            raise KeyError(f"No price configured for model '{model}' (config/pricing.yaml)")
        for fb in price.fallbacks:
            if fb not in self.models:
                raise KeyError(f"Fallback '{fb}' of '{model}' has no price (config/pricing.yaml)")
        return price

    def cost(self, model: str, *, input_tokens: int, output_tokens: int,
             cache_read_tokens: int = 0, cache_write_tokens: int = 0) -> float | None:
        """Actual cost of one attempt. None if the model has no price (never silently $0)."""
        p = self.get(model)
        if p is None:
            return None
        return (input_tokens * p.input + output_tokens * p.output
                + cache_read_tokens * p.cache_read
                + cache_write_tokens * p.cache_write) / PER_TOKEN

    def worst_case(self, model: str, *, input_tokens: int, max_tokens: int) -> float:
        """Upper bound for one call: every input token billed at the cache-write rate and
        the full max_tokens of output, both at the priciest model the call could land on
        (the requested model or one of its refusal fallbacks)."""
        candidates = [self.require(model)] + [self.models[f] for f in self.require(model).fallbacks]
        write = max(c.cache_write for c in candidates)
        out = max(c.output for c in candidates)
        return (input_tokens * write + max_tokens * out) / PER_TOKEN


    def max_output_within(self, model: str, *, input_tokens: int, budget_usd: float) -> int:
        """The largest max_tokens whose worst case stays within budget_usd (can be <= 0)."""
        candidates = [self.require(model)] + [self.models[f] for f in self.require(model).fallbacks]
        write = max(c.cache_write for c in candidates)
        out = max(c.output for c in candidates)
        return int((budget_usd * PER_TOKEN - input_tokens * write) // out)


def load_pricing(config_dir: Path = CONFIG_DIR) -> PriceTable:
    return PriceTable.model_validate(_load_yaml(config_dir / "pricing.yaml"))
