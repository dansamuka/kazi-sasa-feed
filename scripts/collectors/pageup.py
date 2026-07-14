"""Public PageUp institutional career-site collector.

PageUp public vacancy sites expose server-rendered search results and job detail
pages. This adapter reuses the official-page extraction contract while keeping
source governance distinct from generic institutional pages.
"""
from __future__ import annotations

from typing import Iterable

from .official_html import collect_official_html_target


def collect_pageup_target(builder, target: dict, session=None) -> int:
    row = dict(target)
    row["listing_url"] = row.pop("career_site_url")
    row.setdefault("link_patterns", [r"/job/", r"/jobs/", r"/en-us/job/", r"/search/"])
    row.setdefault("exclude_patterns", [r"/jobs/?$", r"/search/?$", r"/filter/?$"])
    row.setdefault("max_jobs", 150)
    row.setdefault("source_name", "PageUp-hosted institutional board")
    return collect_official_html_target(
        builder, row, session=session, source_name=row["source_name"]
    )


def collect_pageup(builder, targets: Iterable[dict], session=None) -> int:
    return sum(collect_pageup_target(builder, target, session=session) for target in targets)
