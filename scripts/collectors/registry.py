"""Built-in collector registry for Kazi Sasa Phase 3.

Collector order deliberately preserves the Phase 2 orchestration order so
existing IDs and default feed ordering remain stable when the same source data
is returned.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from collectors.base import CollectorContext, CollectorSpec
from registry import adapter_boards, load_organisation_registry


def _safe_legacy_config(repo_root: Path, name: str) -> list[dict]:
    path = repo_root / "config" / name
    if not path.exists():
        print(f"INFO: {name} not present, skipping that source", file=sys.stderr)
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("boards", data) if isinstance(data, dict) else data


def _adapter_targets(context: CollectorContext, adapter: str, legacy_name: str) -> list[dict]:
    registry_path = context.repo_root / context.organisations_path
    if registry_path.exists():
        return adapter_boards(load_organisation_registry(registry_path), adapter)
    print(
        f"WARN: organisation registry {context.organisations_path} missing; falling back to {legacy_name}",
        file=sys.stderr,
    )
    return _safe_legacy_config(context.repo_root, legacy_name)


def adapter_targets(context: CollectorContext, adapter: str, legacy_name: str) -> list[dict]:
    """Public compatibility wrapper for resolving configured ATS targets."""
    return _adapter_targets(context, adapter, legacy_name)


def _african_iso3(context: CollectorContext) -> list[str]:
    path = context.repo_root / "config" / "african_locations.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return [row["iso3"] for row in data.get("countries", []) if row.get("iso3")]


def _adzuna_searches(context: CollectorContext) -> list[dict]:
    path = context.repo_root / "config" / "adzuna_queries.json"
    if not path.exists():
        return [{"country": "za", "query": None, "max_pages": 3, "results_per_page": 50}]
    return json.loads(path.read_text(encoding="utf-8")).get("searches", [])


def _reliefweb(context: CollectorContext, countries: list[str]) -> int:
    from collectors.reliefweb import collect_reliefweb

    return collect_reliefweb(
        context.builder,
        appname=context.env["RELIEFWEB_APPNAME"],
        country_iso3=countries,
        session=context.http,
    )


def _untalent(context: CollectorContext, _config: Any) -> int:
    from collectors.untalent import collect_untalent

    return collect_untalent(
        context.builder,
        feed_url=context.env["UNTALENT_FEED_URL"],
        token=context.env.get("UNTALENT_API_TOKEN"),
        session=context.http,
    )




def _cornerstone(context: CollectorContext, targets: list[dict]) -> int:
    from collectors.cornerstone import collect_cornerstone
    return collect_cornerstone(context.builder, targets, session=context.http)


def _successfactors(context: CollectorContext, targets: list[dict]) -> int:
    from collectors.successfactors import collect_successfactors
    return collect_successfactors(context.builder, targets, session=context.http)


def _oracle_cx(context: CollectorContext, targets: list[dict]) -> int:
    from collectors.oracle_cx import collect_oracle_cx
    return collect_oracle_cx(context.builder, targets, session=context.http)



def _pageup(context: CollectorContext, targets: list[dict]) -> int:
    from collectors.pageup import collect_pageup
    return collect_pageup(context.builder, targets, session=context.http)


def _official_html(context: CollectorContext, targets: list[dict]) -> int:
    from collectors.official_html import collect_official_html
    return collect_official_html(context.builder, targets, session=context.http)




def _workday(context: CollectorContext, targets: list[dict]) -> int:
    from collectors.workday import collect_workday
    return collect_workday(context.builder, targets, session=context.http)


def _smartrecruiters(context: CollectorContext, targets: list[dict]) -> int:
    from collectors.smartrecruiters import collect_smartrecruiters
    return collect_smartrecruiters(context.builder, targets, session=context.http)


def _workable(context: CollectorContext, targets: list[dict]) -> int:
    from collectors.workable import collect_workable
    return collect_workable(context.builder, targets, session=context.http)


def _multinational_html(context: CollectorContext, targets: list[dict]) -> int:
    from collectors.multinational_html import collect_multinational_html
    return collect_multinational_html(context.builder, targets, session=context.http)


def _public_institution_html(context: CollectorContext, targets: list[dict]) -> int:
    from collectors.public_institution_html import collect_public_institution_html
    return collect_public_institution_html(context.builder, targets, session=context.http)

def _public_portals(context: CollectorContext, adapter: str) -> list[dict]:
    path = context.repo_root / "config" / "public_portals.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return [row for row in data.get("portals", []) if row.get("enabled") and row.get("adapter") == adapter]


def _government_html(context: CollectorContext, portals: list[dict]) -> int:
    from collectors.government_html import collect_government_html
    return collect_government_html(context.builder, portals, session=context.http)


def _government_pdf(context: CollectorContext, portals: list[dict]) -> int:
    from collectors.government_pdf import collect_government_pdf
    return collect_government_pdf(context.builder, portals, session=context.http)


def _government_circular(context: CollectorContext, portals: list[dict]) -> int:
    from collectors.government_circular import collect_government_circular
    return collect_government_circular(context.builder, portals, session=context.http)


def _adzuna(context: CollectorContext, searches: list[dict]) -> int:
    from collectors.adzuna import collect_adzuna_portfolio

    return collect_adzuna_portfolio(
        context.builder,
        app_id=context.env["ADZUNA_APP_ID"],
        app_key=context.env["ADZUNA_APP_KEY"],
        searches=searches,
        session=context.http,
    )

def _greenhouse(context: CollectorContext, boards: list[dict]) -> int:
    from collectors.greenhouse import collect_greenhouse

    return collect_greenhouse(context.builder, boards, session=context.http)


def _ashby(context: CollectorContext, boards: list[dict]) -> int:
    from collectors.ashby import collect_ashby

    return collect_ashby(context.builder, boards, session=context.http)


def _lever(context: CollectorContext, boards: list[dict]) -> int:
    from collectors.lever import collect_lever

    return collect_lever(context.builder, boards, session=context.http)


def _pinpoint(context: CollectorContext, boards: list[dict]) -> int:
    from collectors.pinpoint import collect_pinpoint

    return collect_pinpoint(context.builder, boards, session=context.http)


def _recruitee(context: CollectorContext, boards: list[dict]) -> int:
    from collectors.recruitee import collect_recruitee

    return collect_recruitee(context.builder, boards, session=context.http)


def _single_source(module_name: str, function_name: str):
    def run(context: CollectorContext, _config: Any) -> int:
        module = __import__(f"collectors.{module_name}", fromlist=[function_name])
        return getattr(module, function_name)(context.builder, session=context.http)

    return run


def default_collector_specs() -> list[CollectorSpec]:
    """Return every enabled built-in collector in deterministic priority order."""
    return [
        CollectorSpec(
            key="reliefweb",
            collect=_reliefweb,
            resolve_config=_african_iso3,
            required_env=("RELIEFWEB_APPNAME",),
            source_kind="institutional_aggregator",
            schedule_class="twice_daily",
            freshness_hours=18,
            min_interval_seconds=0.35,
            cache_ttl_seconds=1800,
            description="ReliefWeb humanitarian and development jobs across all African countries",
        ),
        CollectorSpec(
            key="untalent",
            collect=_untalent,
            required_env=("UNTALENT_FEED_URL",),
            source_kind="institutional_aggregator",
            schedule_class="twice_daily",
            freshness_hours=18,
            min_interval_seconds=0.35,
            cache_ttl_seconds=1800,
            description="UN Talent JSON/RSS feed",
        ),
        CollectorSpec(
            key="cornerstone",
            collect=_cornerstone,
            resolve_config=lambda context: _adapter_targets(context, "cornerstone", "cornerstone_sources.json"),
            source_kind="institution_official",
            schedule_class="three_times_daily",
            freshness_hours=18,
            timeout_seconds=45,
            min_interval_seconds=0.8,
            cache_ttl_seconds=900,
            description="Cornerstone-hosted DFI and multilateral career sites",
        ),
        CollectorSpec(
            key="successfactors",
            collect=_successfactors,
            resolve_config=lambda context: _adapter_targets(context, "successfactors", "successfactors_sources.json"),
            source_kind="institution_official",
            schedule_class="three_times_daily",
            freshness_hours=18,
            timeout_seconds=40,
            min_interval_seconds=0.6,
            cache_ttl_seconds=1200,
            description="Public SAP SuccessFactors institutional career sites",
        ),
        CollectorSpec(
            key="oracle_cx",
            collect=_oracle_cx,
            resolve_config=lambda context: _adapter_targets(context, "oracle_cx", "oracle_cx_sources.json"),
            source_kind="institution_official",
            schedule_class="three_times_daily",
            freshness_hours=18,
            timeout_seconds=40,
            min_interval_seconds=0.6,
            cache_ttl_seconds=1200,
            description="Public Oracle Candidate Experience institutional career sites",
        ),
        CollectorSpec(
            key="pageup",
            collect=_pageup,
            resolve_config=lambda context: _adapter_targets(context, "pageup", "pageup_sources.json"),
            source_kind="institution_official",
            schedule_class="three_times_daily",
            freshness_hours=18,
            timeout_seconds=40,
            min_interval_seconds=0.6,
            cache_ttl_seconds=1200,
            description="Public PageUp NGO and UN career sites",
        ),
        CollectorSpec(
            key="official_html",
            collect=_official_html,
            resolve_config=lambda context: _adapter_targets(context, "official_html", "official_html_sources.json"),
            source_kind="institution_official",
            schedule_class="daily",
            freshness_hours=30,
            timeout_seconds=40,
            min_interval_seconds=0.75,
            cache_ttl_seconds=1800,
            description="Official DFI and multilateral vacancy pages and archives",
        ),
        CollectorSpec(
            key="public_institution_html",
            collect=_public_institution_html,
            resolve_config=lambda context: _adapter_targets(context, "public_institution_html", "public_institution_sources.json"),
            source_kind="government_official",
            schedule_class="daily",
            freshness_hours=36,
            timeout_seconds=40,
            min_interval_seconds=0.6,
            cache_ttl_seconds=1800,
            description="Kenya public-institution official career and vacancy pages",
        ),
        CollectorSpec(
            key="workday",
            collect=_workday,
            resolve_config=lambda context: _adapter_targets(context, "workday", "workday_sources.json"),
            source_kind="employer_ats",
            schedule_class="three_times_daily",
            freshness_hours=18,
            timeout_seconds=45,
            min_interval_seconds=0.5,
            cache_ttl_seconds=900,
            description="Public Workday Candidate Experience employer sites",
        ),
        CollectorSpec(
            key="smartrecruiters",
            collect=_smartrecruiters,
            resolve_config=lambda context: _adapter_targets(context, "smartrecruiters", "smartrecruiters_sources.json"),
            source_kind="employer_ats",
            schedule_class="three_times_daily",
            freshness_hours=18,
            timeout_seconds=40,
            min_interval_seconds=0.4,
            cache_ttl_seconds=900,
            description="Public SmartRecruiters employer postings",
        ),
        CollectorSpec(
            key="workable",
            collect=_workable,
            resolve_config=lambda context: _adapter_targets(context, "workable", "workable_sources.json"),
            source_kind="employer_ats",
            schedule_class="three_times_daily",
            freshness_hours=18,
            timeout_seconds=40,
            min_interval_seconds=0.4,
            cache_ttl_seconds=900,
            description="Public Workable employer postings",
        ),
        CollectorSpec(
            key="multinational_html",
            collect=_multinational_html,
            resolve_config=lambda context: _adapter_targets(context, "multinational_html", "multinational_html_sources.json"),
            source_kind="employer_official",
            schedule_class="daily",
            freshness_hours=30,
            timeout_seconds=40,
            min_interval_seconds=0.6,
            cache_ttl_seconds=1800,
            description="Controlled official career pages for Phase 11 multinationals",
        ),
        CollectorSpec(
            key="government_html",
            collect=_government_html,
            resolve_config=lambda context: _public_portals(context, "government_html"),
            source_kind="government_official",
            schedule_class="daily",
            freshness_hours=30,
            timeout_seconds=45,
            min_interval_seconds=0.8,
            cache_ttl_seconds=1800,
            description="Official government HTML vacancy portals",
        ),
        CollectorSpec(
            key="government_pdf",
            collect=_government_pdf,
            resolve_config=lambda context: _public_portals(context, "government_pdf"),
            source_kind="government_official",
            schedule_class="daily",
            freshness_hours=36,
            timeout_seconds=60,
            min_interval_seconds=1.0,
            cache_ttl_seconds=3600,
            description="Direct official government PDF vacancy documents",
        ),
        CollectorSpec(
            key="government_circular",
            collect=_government_circular,
            resolve_config=lambda context: _public_portals(context, "government_circular"),
            source_kind="government_official",
            schedule_class="daily",
            freshness_hours=36,
            timeout_seconds=60,
            min_interval_seconds=1.0,
            cache_ttl_seconds=3600,
            description="Official government circular and advertisement indexes",
        ),
        CollectorSpec(
            key="adzuna",
            collect=_adzuna,
            resolve_config=_adzuna_searches,
            required_env=("ADZUNA_APP_ID", "ADZUNA_APP_KEY"),
            source_kind="commercial_aggregator",
            schedule_class="three_times_daily",
            description="Adzuna South Africa general and priority-role search portfolio",
        ),
        CollectorSpec(
            key="greenhouse",
            collect=_greenhouse,
            resolve_config=lambda context: _adapter_targets(context, "greenhouse", "greenhouse_boards.json"),
            source_kind="employer_ats",
            description="Configured Greenhouse employer boards",
        ),
        CollectorSpec(
            key="ashby",
            collect=_ashby,
            resolve_config=lambda context: _adapter_targets(context, "ashby", "ashby_boards.json"),
            source_kind="employer_ats",
            description="Configured Ashby employer boards",
        ),
        CollectorSpec(
            key="lever",
            collect=_lever,
            resolve_config=lambda context: _adapter_targets(context, "lever", "lever_boards.json"),
            source_kind="employer_ats",
            description="Configured Lever employer boards",
        ),
        CollectorSpec(
            key="pinpoint",
            collect=_pinpoint,
            resolve_config=lambda context: _adapter_targets(context, "pinpoint", "pinpoint_boards.json"),
            source_kind="employer_ats",
            description="Configured Pinpoint employer boards",
        ),
        CollectorSpec(
            key="recruitee",
            collect=_recruitee,
            resolve_config=lambda context: _adapter_targets(context, "recruitee", "recruitee_boards.json"),
            source_kind="employer_ats",
            description="Configured Recruitee public careers-site boards",
        ),
        CollectorSpec(
            key="himalayas",
            collect=_single_source("himalayas", "collect_himalayas"),
            source_kind="commercial_aggregator",
            description="Himalayas remote jobs",
        ),
        CollectorSpec(
            key="remotive",
            collect=_single_source("remotive", "collect_remotive"),
            source_kind="commercial_aggregator",
            description="Remotive remote jobs",
        ),
        CollectorSpec(
            key="jobicy",
            collect=_single_source("jobicy", "collect_jobicy"),
            source_kind="commercial_aggregator",
            min_interval_seconds=0.5,
            cache_ttl_seconds=7200,
            description="Jobicy remote jobs",
        ),
        CollectorSpec(
            key="remoteok",
            collect=_single_source("remoteok", "collect_remoteok"),
            source_kind="commercial_aggregator",
            description="Remote OK remote jobs",
        ),
        CollectorSpec(
            key="arbeitnow",
            collect=_single_source("arbeitnow", "collect_arbeitnow"),
            source_kind="commercial_aggregator",
            description="Arbeitnow remote jobs",
        ),
    ]


def collector_manifest() -> list[dict[str, Any]]:
    """Serializable registry metadata for diagnostics and documentation."""
    return [
        {
            "key": spec.key,
            "source_kind": spec.source_kind,
            "schedule_class": spec.schedule_class,
            "freshness_hours": spec.freshness_hours,
            "timeout_seconds": spec.timeout_seconds,
            "min_interval_seconds": spec.min_interval_seconds,
            "cache_ttl_seconds": spec.cache_ttl_seconds,
            "required_env": list(spec.required_env),
            "configured": spec.resolve_config is not None,
            "description": spec.description,
        }
        for spec in default_collector_specs()
    ]
