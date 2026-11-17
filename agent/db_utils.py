"""Dates communes à l'agent et à l'API (UTC, ISO 8601)."""

from datetime import datetime, timezone


def maintenant() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def iso(moment: datetime) -> str:
    return moment.isoformat()


def maintenant_iso() -> str:
    return iso(maintenant())
