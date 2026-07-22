"""Duplicate detection — never notify twice for the same posting."""

from __future__ import annotations

from core.models import Internship


def is_duplicate(existing_keys: set[str], internship: Internship) -> bool:
    """True if we've already seen this job (by dedupe_key or url_hash)."""
    return internship.dedupe_key in existing_keys or internship.url_hash in existing_keys


def keys_for(internship: Internship) -> set[str]:
    return {internship.dedupe_key, internship.url_hash}
