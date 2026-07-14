"""Standard contracts for registry-driven collectors."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping


ConfigResolver = Callable[["CollectorContext"], Any]
CollectorCallable = Callable[["CollectorContext", Any], int]


@dataclass(frozen=True)
class CollectorSpec:
    """Declarative metadata and executable hooks for one collector.

    The registry is the only place the orchestrator needs to know about an
    individual source. Adding a collector no longer requires editing the
    central refresh loop.
    """

    key: str
    collect: CollectorCallable
    resolve_config: ConfigResolver | None = None
    required_env: tuple[str, ...] = ()
    source_kind: str = "public_feed"
    schedule_class: str = "three_times_daily"
    freshness_hours: int = 12
    timeout_seconds: float = 30.0
    min_interval_seconds: float = 0.15
    cache_ttl_seconds: int = 900
    description: str = ""
    skip_when_config_empty: bool = True


@dataclass
class CollectorContext:
    builder: Any
    repo_root: Path
    organisations_path: str
    env: Mapping[str, str]
    http: Any | None = None
    selected_sources: set[str] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class CollectorRunSummary:
    per_source_counts: dict[str, int] = field(default_factory=dict)
    statuses: dict[str, dict[str, Any]] = field(default_factory=dict)
    configured_counts: dict[str, int] = field(default_factory=dict)

    @property
    def errors(self) -> int:
        return sum(1 for status in self.statuses.values() if status.get("status") == "error")
