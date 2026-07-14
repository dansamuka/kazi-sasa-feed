"""Public SAP SuccessFactors Career Site Builder collector.

SuccessFactors career sites render public job links server-side even though
permissioned Recruiting APIs require tenant credentials. This adapter collects
those official public links and delegates detail extraction to the shared DFI
career-page parser.
"""
from __future__ import annotations

from typing import Iterable

from .official_html import collect_official_html_target


def collect_successfactors_target(builder, target: dict, session=None) -> int:
    target = dict(target)
    target["listing_url"] = target.pop("career_site_url")
    target.setdefault("link_patterns", [r"/job/", r"/jobdetails/", r"/jobdetail/"])
    target.setdefault("exclude_patterns", [r"/search/?$", r"/viewalljobs/?$"])
    target.setdefault("max_jobs", 100)
    return collect_official_html_target(builder, target, session=session, source_name="SuccessFactors-hosted institutional board")


def collect_successfactors(builder, targets: Iterable[dict], session=None) -> int:
    return sum(collect_successfactors_target(builder, target, session=session) for target in targets)
