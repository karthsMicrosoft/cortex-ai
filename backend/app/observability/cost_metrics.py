"""
RAG / LLM cost metrics (PR Round 20 / beta).

Emits a custom OpenTelemetry counter ``cortex.rag.cost_usd_estimate`` with
dimensions {model, route} for every LLM call made by the backend, alongside
companion counters for prompt + completion tokens.

Pricing snapshot (USD per 1M tokens, captured 2026-05):
  - gpt-4o-mini             : $0.15 input / $0.60 output
  - gpt-4o                  : $2.50 input / $10.00 output
  - text-embedding-3-small  : $0.02 input / $0.00 output (no completion side)

The helper is **always safe**: if OpenTelemetry SDK isn't installed, isn't
initialised, or any meter call fails, the error is logged at DEBUG and
swallowed — telemetry must never break a request.
"""
from __future__ import annotations

import logging
from typing import Final

logger = logging.getLogger(__name__)

# Pricing in USD per 1,000,000 tokens. Source: Azure OpenAI / OpenAI public
# pricing as of 2026-05. Update this table when pricing changes — it is the
# single source of truth for the cost metric.
PRICING_USD_PER_1M: Final[dict[str, dict[str, float]]] = {
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "text-embedding-3-small": {"input": 0.02, "output": 0.0},
}

_METER_NAME: Final[str] = "cortex.rag"
_COST_METRIC: Final[str] = "cortex.rag.cost_usd_estimate"
_PROMPT_METRIC: Final[str] = "cortex.rag.prompt_tokens"
_COMPLETION_METRIC: Final[str] = "cortex.rag.completion_tokens"


def _compute_cost(
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
) -> float:
    """Compute USD cost for one LLM call.

    Returns 0.0 (and logs a warning) when *model* is not in the pricing
    table — we'd rather under-report than blow up a request. Negative
    token counts are clamped to zero.
    """
    pricing = PRICING_USD_PER_1M.get(model)
    if pricing is None:
        logger.warning(
            "cost_metrics: unknown model %r — emitting cost=0.0", model,
        )
        return 0.0
    p_tokens = max(int(prompt_tokens or 0), 0)
    c_tokens = max(int(completion_tokens or 0), 0)
    return (
        (p_tokens / 1_000_000.0) * pricing["input"]
        + (c_tokens / 1_000_000.0) * pricing["output"]
    )


async def emit_llm_cost(
    model: str,
    prompt_tokens: int,
    completion_tokens: int = 0,
    *,
    route: str,
) -> None:
    """Emit cost + token counters for one LLM call.

    Always safe: exceptions are caught and logged at DEBUG so telemetry
    never breaks the request. No-op when the OpenTelemetry SDK isn't
    installed or initialised.
    """
    try:
        cost = _compute_cost(model, prompt_tokens, completion_tokens)
        from opentelemetry import metrics  # local import — optional dep

        meter = metrics.get_meter(_METER_NAME)
        attributes = {"model": model, "route": route}

        cost_counter = meter.create_counter(
            _COST_METRIC,
            unit="USD",
            description="Estimated USD cost per LLM call",
        )
        cost_counter.add(cost, attributes=attributes)

        prompt_counter = meter.create_counter(
            _PROMPT_METRIC,
            unit="tokens",
            description="Prompt tokens consumed per LLM call",
        )
        prompt_counter.add(max(int(prompt_tokens or 0), 0), attributes=attributes)

        completion_counter = meter.create_counter(
            _COMPLETION_METRIC,
            unit="tokens",
            description="Completion tokens produced per LLM call",
        )
        completion_counter.add(
            max(int(completion_tokens or 0), 0), attributes=attributes,
        )
    except Exception:  # noqa: BLE001 — telemetry must never break the call
        logger.debug("emit_llm_cost failed", exc_info=True)
