"""Defensive text normalisation for inconsistent third-party API payloads.

Public job APIs occasionally change a nominal string field into a list, an
object, or a mixed collection. Collectors should preserve useful text and
never call string methods on untrusted raw values directly.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from html import unescape
from typing import Any

_PREFERRED_KEYS = ("name", "label", "title", "value", "text", "description")


def as_text_list(value: Any) -> list[str]:
    """Return a de-duplicated list of non-empty text fragments.

    Strings remain one item. Lists/tuples/sets are flattened recursively.
    Mappings prefer common display-value keys, then fall back to their scalar
    values. Numbers and booleans are stringified. Unknown objects are ignored
    rather than leaking a Python representation into the public feed.
    """
    if value is None:
        return []
    if isinstance(value, str):
        text = unescape(value).strip()
        return [text] if text else []
    if isinstance(value, Mapping):
        preferred: list[str] = []
        for key in _PREFERRED_KEYS:
            if key in value:
                preferred.extend(as_text_list(value[key]))
        fragments = preferred or [part for raw in value.values() for part in as_text_list(raw)]
    elif isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        fragments = [part for raw in value for part in as_text_list(raw)]
    elif isinstance(value, set):
        fragments = [part for raw in sorted(value, key=str) for part in as_text_list(raw)]
    elif isinstance(value, (int, float, bool)):
        fragments = [str(value)]
    else:
        return []

    result: list[str] = []
    seen: set[str] = set()
    for fragment in fragments:
        normalised = fragment.strip()
        key = normalised.casefold()
        if normalised and key not in seen:
            seen.add(key)
            result.append(normalised)
    return result


def as_text(value: Any, separator: str = ", ") -> str:
    """Coerce a third-party value to safe display/search text."""
    return separator.join(as_text_list(value))
