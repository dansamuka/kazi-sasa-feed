"""Public Workable apply-site collector."""
from __future__ import annotations

import sys
from typing import Iterable

from .employer_common import employer_opportunity


def _rows(payload):
    if isinstance(payload, list): return payload
    if not isinstance(payload, dict): return []
    for key in ('results','jobs','data'):
        value=payload.get(key)
        if isinstance(value,list): return value
        if isinstance(value,dict):
            for nested in ('results','jobs','data'):
                if isinstance(value.get(nested),list): return value[nested]
    return []


def collect_workable_target(builder, target: dict, session=None) -> int:
    import requests
    client=session or requests
    account=target.get('account_slug') or target.get('identifier')
    endpoint=f"https://apply.workable.com/api/v3/accounts/{account}/jobs"
    try:
        response=client.get(endpoint,headers={'Accept':'application/json'},timeout=40)
        response.raise_for_status(); payload=response.json()
    except Exception as exc:  # noqa: BLE001
        print(f"WARN workable[{target.get('organisation_id')}]: fetch failed - {exc}",file=sys.stderr)
        return 0
    added=0; seen=set()
    for row in _rows(payload)[:int(target.get('max_jobs',200))]:
        if not isinstance(row,dict): continue
        loc=row.get('location') or row.get('locations') or row.get('location_str')
        if isinstance(loc,list): loc=', '.join(str(x.get('name') if isinstance(x,dict) else x) for x in loc)
        if isinstance(loc,dict): loc=', '.join(str(loc.get(k)) for k in ('city','region','country','name') if loc.get(k))
        shortcode=row.get('shortcode') or row.get('id') or row.get('slug')
        apply_url=row.get('url') or row.get('application_url') or f"https://apply.workable.com/{account}/j/{shortcode}/"
        opportunity=employer_opportunity(
            builder,target,prefix='workable',external_id=shortcode,title=row.get('title') or row.get('name'),
            apply_url=apply_url,raw_location=loc,description=row.get('description') or row.get('description_text'),
            posted_at=row.get('published') or row.get('created_at'),employment_type=row.get('employment_type') or row.get('type'),
            source_name=target.get('source_name','Workable-hosted employer board'),
            source_url=f"https://apply.workable.com/{account}/",reference=row.get('code'),
        )
        if opportunity and opportunity['id'] not in seen:
            builder.add(opportunity); seen.add(opportunity['id']); added+=1
    return added


def collect_workable(builder,targets:Iterable[dict],session=None)->int:
    return sum(collect_workable_target(builder,target,session=session) for target in targets)
