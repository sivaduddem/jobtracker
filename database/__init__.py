"""Re-export storage for `from database import Storage` convenience."""

from database.sqlite import Storage

__all__ = ["Storage"]
