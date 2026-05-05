"""
ScenarioEventSubsystem — fires pre-scripted narrative events from scenario JSON.

Events are loaded once per game session.  On each tick the subsystem checks
whether any events are scheduled for that tick and returns them for broadcast.

Event format (from scenarios/{scenario_id}.json):
  {
    "id":             "EVT_001",
    "tick":           6,
    "type":           "INTEL" | "ALERT" | "DIPLOMATIC" | "COMBAT" | "SYSTEM",
    "classification": "TOP SECRET // NOFORN",
    "title":          "Short headline",
    "body":           "Full narrative text.",
    "source":         "NSA SIGINT"
  }
"""
from __future__ import annotations

import json
import logging
import os
from typing import NamedTuple

log = logging.getLogger(__name__)

_SCENARIOS_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "scenarios")
)


class ScenarioEventResult(NamedTuple):
    events: list[dict]


class ScenarioEventSubsystem:
    def __init__(self, game_id: str, scenario_id: str) -> None:
        self._game_id = game_id
        self._events = self._load_events(scenario_id)

    def _load_events(self, scenario_id: str) -> list[dict]:
        if not scenario_id:
            return []
        path = os.path.join(_SCENARIOS_DIR, f"{scenario_id}.json")
        try:
            with open(path) as f:
                data = json.load(f)
            events = data.get("events", [])
            log.debug(
                "ScenarioEventSubsystem loaded %d events for scenario %s",
                len(events), scenario_id,
            )
            return events
        except FileNotFoundError:
            log.warning("Scenario file not found: %s", path)
            return []
        except (json.JSONDecodeError, KeyError) as exc:
            log.error("Failed to parse scenario events: %s", exc)
            return []

    def resolve_tick(self, tick: int) -> ScenarioEventResult:
        """Return all events scheduled for this tick."""
        due = [e for e in self._events if e.get("tick") == tick]
        if due:
            log.debug(
                "Tick %d | %d scenario event(s) firing for game %s",
                tick, len(due), self._game_id,
            )
        return ScenarioEventResult(events=due)
