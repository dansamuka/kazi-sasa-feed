"""Public Workday Candidate Experience collector for Phase 11 employers."""
from __future__ import annotations

import sys
from typing import Iterable
from urllib.parse import urlparse, urljoin

from .employer_common import employer_opportunity


def _context(target: dict) -> tuple[str, str, str]:
    parsed = urlparse(target['career_site_url'])
    host = parsed.netloc
    path = [part for part in parsed.path.split('/') if part]
    tenant = target.get('tenant') or host.split('.', 1)[0]
    site = target.get('site') or (path[-1] if path else '')
    if not host or not tenant or not site:
        raise ValueError('career_site_url, tenant and site are required')
    return host, tenant, site


def collect_workday_target(builder, target: dict, session=None) -> int:
    import requests
    client = session or requests
    try:
        host, tenant, site = _context(target)
    except ValueError as exc:
        print(f"WARN workday[{target.get('organisation_id')}]: {exc}", file=sys.stderr)
        return 0
    endpoint = f"https://{host}/wday/cxs/{tenant}/{site}/jobs"
    offset = 0
    limit = int(target.get('page_size', 50))
    max_jobs = int(target.get('max_jobs', 200))
    added = 0
    seen: set[str] = set()
    while offset < max_jobs:
        try:
            response = client.post(
                endpoint,
                headers={'Accept':'application/json','Content-Type':'application/json'},
                json={'appliedFacets':{},'limit':limit,'offset':offset,'searchText':target.get('search_text','')},
                timeout=40,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:  # noqa: BLE001
            print(f"WARN workday[{target.get('organisation_id')}]: search failed - {exc}", file=sys.stderr)
            break
        rows = payload.get('jobPostings') or payload.get('items') or []
        if not isinstance(rows, list) or not rows:
            break
        for row in rows:
            if not isinstance(row, dict):
                continue
            external_path = row.get('externalPath') or row.get('url') or ''
            apply_url = urljoin(target['career_site_url'].rstrip('/')+'/', str(external_path).lstrip('/'))
            description = row.get('description') or row.get('shortDescription') or ' '.join(row.get('bulletFields') or [])
            opportunity = employer_opportunity(
                builder, target, prefix='workday', external_id=row.get('id') or external_path,
                title=row.get('title'), apply_url=apply_url,
                raw_location=row.get('locationsText') or row.get('location'),
                description=description, posted_at=row.get('postedOn') or row.get('postedDate'),
                employment_type=row.get('timeType') or row.get('jobType'),
                source_name=target.get('source_name','Workday-hosted employer career site'),
                source_url=target['career_site_url'], reference=row.get('jobReqId'),
            )
            if opportunity and opportunity['id'] not in seen:
                builder.add(opportunity); seen.add(opportunity['id']); added += 1
        total = payload.get('total') or payload.get('totalResults') or len(rows)
        offset += len(rows)
        if len(rows) < limit or offset >= int(total or 0):
            break
    return added


def collect_workday(builder, targets: Iterable[dict], session=None) -> int:
    return sum(collect_workday_target(builder, target, session=session) for target in targets)
