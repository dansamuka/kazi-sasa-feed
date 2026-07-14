"""Execute collectors independently with consistent health metadata."""
from __future__ import annotations

import sys
import time
from collections.abc import Sized
from typing import Any, Iterable

from collectors.base import CollectorContext, CollectorRunSummary, CollectorSpec


def _configured_count(config: Any) -> int:
    if config is None:
        return 0
    if isinstance(config, Sized) and not isinstance(config, (str, bytes, bytearray, dict)):
        return len(config)
    if isinstance(config, dict):
        return len(config.get("boards", config)) if config else 0
    return 1


def _config_is_empty(config: Any) -> bool:
    if config is None:
        return False
    if isinstance(config, (str, bytes, bytearray)):
        return not bool(config)
    if isinstance(config, Sized):
        return len(config) == 0
    return False


class CollectorRunner:
    """Run registered collectors without allowing one source to abort others."""

    def __init__(self, specs: Iterable[CollectorSpec]):
        self.specs = list(specs)
        keys = [spec.key for spec in self.specs]
        if len(keys) != len(set(keys)):
            duplicates = sorted({key for key in keys if keys.count(key) > 1})
            raise ValueError(f"duplicate collector keys: {duplicates}")

    def run(self, context: CollectorContext) -> CollectorRunSummary:
        summary = CollectorRunSummary()
        selected = context.selected_sources

        for spec in self.specs:
            if selected is not None and spec.key not in selected:
                continue

            missing_env = [name for name in spec.required_env if not context.env.get(name)]
            if missing_env:
                summary.per_source_counts[spec.key] = 0
                summary.statuses[spec.key] = {
                    "status": "skipped_missing_config",
                    "reason": f"missing environment configuration: {', '.join(missing_env)}",
                    "missing_env": missing_env,
                    "source_kind": spec.source_kind,
                    "schedule_class": spec.schedule_class,
                    "freshness_hours": spec.freshness_hours,
                    "timeout_seconds": spec.timeout_seconds,
                }
                print(f"INFO: {spec.key} skipped; missing {', '.join(missing_env)}", file=sys.stderr)
                continue

            try:
                config = spec.resolve_config(context) if spec.resolve_config else None
            except Exception as exc:  # noqa: BLE001
                summary.per_source_counts[spec.key] = 0
                summary.statuses[spec.key] = {
                    "status": "error",
                    "error": f"configuration failed: {exc}",
                    "source_kind": spec.source_kind,
                    "schedule_class": spec.schedule_class,
                    "freshness_hours": spec.freshness_hours,
                    "timeout_seconds": spec.timeout_seconds,
                }
                print(f"ERROR {spec.key}: configuration failed - {exc}", file=sys.stderr)
                continue

            configured_targets = _configured_count(config)
            if spec.resolve_config is not None:
                summary.configured_counts[spec.key] = configured_targets
            if spec.skip_when_config_empty and spec.resolve_config is not None and _config_is_empty(config):
                summary.per_source_counts[spec.key] = 0
                summary.statuses[spec.key] = {
                    "status": "skipped_no_targets",
                    "reason": "collector has no enabled configured targets",
                    "configured_targets": configured_targets,
                    "source_kind": spec.source_kind,
                    "schedule_class": spec.schedule_class,
                    "freshness_hours": spec.freshness_hours,
                    "timeout_seconds": spec.timeout_seconds,
                }
                continue

            if context.http is not None and hasattr(context.http, "set_policy"):
                context.http.set_policy(
                    spec.key,
                    timeout_seconds=spec.timeout_seconds,
                    min_interval_seconds=spec.min_interval_seconds,
                    cache_ttl_seconds=spec.cache_ttl_seconds,
                )

            before = len(context.builder.opportunities)
            started = time.perf_counter()
            try:
                returned = int(spec.collect(context, config) or 0)
                added_delta = len(context.builder.opportunities) - before
                duration_ms = round((time.perf_counter() - started) * 1000)
                status = "collected" if added_delta > 0 else "empty"
                row = {
                    "status": status,
                    "returned_count": returned,
                    "added_delta": added_delta,
                    "duration_ms": duration_ms,
                    "source_kind": spec.source_kind,
                    "schedule_class": spec.schedule_class,
                    "freshness_hours": spec.freshness_hours,
                    "timeout_seconds": spec.timeout_seconds,
                }
                if configured_targets:
                    row["configured_targets"] = configured_targets
                if returned != added_delta:
                    row["count_mismatch"] = True
                    row["reason"] = "collector return count differs from opportunities added"
                summary.per_source_counts[spec.key] = added_delta
                summary.statuses[spec.key] = row
            except Exception as exc:  # noqa: BLE001
                duration_ms = round((time.perf_counter() - started) * 1000)
                partial_added = len(context.builder.opportunities) - before
                if partial_added > 0:
                    del context.builder.opportunities[before:]
                summary.per_source_counts[spec.key] = 0
                summary.statuses[spec.key] = {
                    "status": "error",
                    "error": str(exc),
                    "duration_ms": duration_ms,
                    "rolled_back_partial": partial_added,
                    "source_kind": spec.source_kind,
                    "schedule_class": spec.schedule_class,
                    "freshness_hours": spec.freshness_hours,
                    "timeout_seconds": spec.timeout_seconds,
                }
                if configured_targets:
                    summary.statuses[spec.key]["configured_targets"] = configured_targets
                print(f"ERROR {spec.key}: {exc}", file=sys.stderr)

        return summary
