"""Official careers-page collector for Kenya public institutions."""
from __future__ import annotations
from typing import Iterable
from .official_html import collect_official_html_target

def collect_public_institution_html(builder,targets:Iterable[dict],session=None)->int:
    return sum(collect_official_html_target(builder,target,session=session,source_name=target.get('source_name','Kenya public institution official vacancies')) for target in targets)
