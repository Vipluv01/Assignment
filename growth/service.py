"""Request handlers shared by the local server (server.py) and the Vercel functions (api/)."""
from __future__ import annotations

import datetime as dt

from . import copilot
from .engine import DEFAULT_SETTINGS, DEFINITIONS, Model


def dashboard(payload: dict) -> dict:
    model = Model(payload.get("overlay"))
    as_of = model.clamp(payload.get("as_of"))
    as_of = min(max(as_of, model.history_start), max(model.default_as_of(), model.history_end))
    w = model.settings["window_days"]
    d = dt.date.fromisoformat(as_of)
    recent_since = (d - dt.timedelta(days=w - 1)).isoformat()
    prev_end = (d - dt.timedelta(days=w)).isoformat()
    prev_since = (d - dt.timedelta(days=2 * w - 1)).isoformat()
    return {
        "as_of": as_of,
        "bounds": {"min": model.history_start, "max": model.default_as_of(), "event_start": model.event_start, "event_end": model.event_end},
        "event": model.event,
        "overview": model.overview(as_of),
        "campaigns": model.campaign_table(as_of),
        "recent": {"since": recent_since, "to": as_of, "rows": model.campaign_table(as_of, recent_since), "total": model.metrics(as_of, recent_since)},
        "previous": {"since": prev_since, "to": prev_end, "rows": _window(model, prev_end, prev_since), "total": _window_total(model, prev_end, prev_since)},
        "series": model.time_series(as_of),
        "decisions": model.decisions(as_of),
        "campaign_meta": model.campaigns,
        "targets": model.targets,
        "tasks": model.table("tasks", as_of),
        "settings": model.settings,
        "default_settings": DEFAULT_SETTINGS,
        "definitions": DEFINITIONS,
        "duplicates_removed": model.duplicates_removed,
        "warnings": model.warnings,
        "ai_provider": copilot.provider_name(),
    }


def _window(model, end, since):
    if end < model.history_start:
        return []
    return model.campaign_table(end, since)


def _window_total(model, end, since):
    if end < model.history_start:
        return None
    return model.metrics(end, since)


def chat(payload: dict) -> dict:
    return copilot.chat(payload)
