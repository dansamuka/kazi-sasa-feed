"""Public SmartRecruiters company postings collector."""
from __future__ import annotations

import sys
from typing import Iterable

from .employer_common import employer_opportunity


def collect_smartrecruiters_target(builder, target: dict, session=None) -> int:
    import requests
    client = session or requests
    company = target.get('company_identifier') or target.get('identifier')
    endpoint = f"https://api.smartrecruiters.com/v1/companies/{company}/postings"
    offset = 0
    limit = int(target.get('page_size', 100))
    max_jobs = int(target.get('max_jobs', 300))
    added = 0
    seen: set[str] = set()
    while offset < max_jobs:
        try:
            response = client.get(endpoint, params={'limit':limit,'offset':offset}, headers={'Accept':'application/json'}, timeout=40)
            response.raise_for_status(); payload = response.json()
        except Exception as exc:  # noqa: BLE001
            print(f"WARN smartrecruiters[{target.get('organisation_id')}]: fetch failed - {exc}", file=sys.stderr)
            break
        rows = payload.get('content') or payload.get('postings') or payload.get('jobs') or []
        if not isinstance(rows, list) or not rows:
            break
        for row in rows:
            if not isinstance(row, dict): continue
            loc = row.get('location') or {}
            raw_location = ', '.join(str(loc.get(k)) for k in ('city','region','country') if loc.get(k)) if isinstance(loc,dict) else loc
            apply_url = row.get('ref') or row.get('url') or f"https://jobs.smartrecruiters.com/{company}/{row.get('id','')}"
            opportunity = employer_opportunity(
                builder,target,prefix='smartrecruiters',external_id=row.get('id'),title=row.get('name') or row.get('title'),
                apply_url=apply_url,raw_location=raw_location,description=row.get('jobAd') or row.get('description'),
                posted_at=row.get('releasedDate') or row.get('createdOn'),employment_type=row.get('typeOfEmployment'),
                source_name=target.get('source_name','SmartRecruiters-hosted employer board'),
                source_url=f"https://jobs.smartrecruiters.com/{company}",reference=row.get('refNumber'),
            )
            if opportunity and opportunity['id'] not in seen:
                builder.add(opportunity); seen.add(opportunity['id']); added += 1
        offset += len(rows)
        total = payload.get('totalFound') or payload.get('total') or offset
        if len(rows) < limit or offset >= int(total or 0): break
    return added


def collect_smartrecruiters(builder, targets: Iterable[dict], session=None) -> int:
    return sum(collect_smartrecruiters_target(builder,target,session=session) for target in targets)
