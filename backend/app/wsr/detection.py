"""WSR detection configuration (Go-Live naming and upcoming horizon)."""

from __future__ import annotations

from app.config import settings

DEFAULT_GO_LIVE_MARKERS = ("go-live", "go live")
DEFAULT_SIGN_OFF_MARKERS = (
    "sign-off",
    "sign off",
    "review & approval",
    "review and approval",
    "uat sign-off",
    "project plan sign-off",
    "signed off",
    "approved",
    "accepted",
    "presented",
)


def go_live_markers() -> tuple[str, ...]:
    items = [
        item.strip().lower()
        for item in (settings.wsr_go_live_markers or "").split(",")
        if item.strip()
    ]
    return tuple(items) if items else DEFAULT_GO_LIVE_MARKERS


def sign_off_markers() -> tuple[str, ...]:
    return DEFAULT_SIGN_OFF_MARKERS


def gate_name_markers() -> tuple[str, ...]:
    return sign_off_markers() + go_live_markers() + ("approval",)


def upcoming_horizon_days() -> int:
    try:
        days = int(settings.wsr_upcoming_days)
    except (TypeError, ValueError):
        days = 7
    return max(1, days)
