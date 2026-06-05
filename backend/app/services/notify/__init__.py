"""Notification delivery abstractions (Round 35)."""
from dataclasses import dataclass
from typing import Literal


@dataclass
class NotifyResult:
    success: bool
    channel: Literal["webpush", "email", "none"]
    error: str | None = None
    # 410 Gone means the subscription is dead and should be deleted.
    expired: bool = False
