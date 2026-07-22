"""Discovery package — re-exports DiscoveryEngine."""

from core.discovery import DiscoveryEngine, classify_ats, slugify

__all__ = ["DiscoveryEngine", "classify_ats", "slugify"]
