"""Observability helpers (App Insights tracing, RAG cost metrics) for cortex backend.

Round 20 — combines PR alpha (tracing) + PR beta (cost metrics).
"""

from app.observability.tracing import add_user_id_hash_to_span, init_tracing

__all__ = ["init_tracing", "add_user_id_hash_to_span"]
