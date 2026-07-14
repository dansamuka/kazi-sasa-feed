"""Controlled official career-page collector for Phase 11 multinationals."""
from __future__ import annotations
from typing import Iterable
from .official_html import collect_official_html_target

def collect_multinational_html(builder,targets:Iterable[dict],session=None)->int:
    return sum(collect_official_html_target(builder,target,session=session,source_name=target.get('source_name','Multinational employer official careers')) for target in targets)
