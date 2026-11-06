"""Region parsing and validation.

Region names end up in endpoint hostnames and cache file names, so they are validated
strictly instead of trusted.
"""

from __future__ import annotations

import re

_REGION_RE = re.compile(r"^[a-z]{2}(-[a-z]+)+-\d{1,2}$")


def validate_region(region: str) -> str:
    if not _REGION_RE.fullmatch(region):
        raise ValueError(f"invalid AWS region name: {region!r}")
    return region


def parse_region_list(value: str) -> list[str]:
    """Parse 'us-east-1,eu-west-1' into a de-duplicated, validated list (order kept)."""
    seen: dict[str, None] = {}
    for part in value.split(","):
        part = part.strip()
        if part:
            seen[validate_region(part)] = None
    if not seen:
        raise ValueError("no regions given")
    return list(seen)
