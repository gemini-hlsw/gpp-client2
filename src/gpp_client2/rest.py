"""
Shared helpers for the ODB's REST endpoints.

The domain classes (scheduler, attachment) own the actual endpoint methods;
this module holds the pieces they share: text-response processing with
defensive gzip handling, transport-error mapping, and the visibility-changes
row format.
"""

from __future__ import annotations

import datetime as _dt
import gzip
from dataclasses import dataclass

import httpx

from gpp_client2.errors import (
    GPPAuthError,
    GPPConnectionError,
    GPPResponseError,
    GPPTimeoutError,
)

__all__ = [
    "VisibilityChange",
    "map_transport_error",
    "parse_visibility",
    "process_text",
    "visibility_params",
]


@dataclass(frozen=True)
class VisibilityChange:
    """
    An entity whose visibility-relevant inputs changed.

    Parameters
    ----------
    gid : str
        The entity's GID (observation or target).
    changed_at : datetime.datetime
        When the change happened, UTC.
    """

    gid: str
    changed_at: _dt.datetime


def process_text(response: httpx.Response) -> str:
    """Map a REST text response onto its body or a typed exception."""
    if response.status_code in (401, 403):
        raise GPPAuthError(
            f"Authentication failed (HTTP {response.status_code}) for "
            f"{response.request.url.path}."
        )
    if response.status_code >= 400:
        raise GPPResponseError(response.status_code, response.text[:500])
    content = response.content
    # Defensive: a proxy may hand us gzip bytes without a Content-Encoding
    # header, bypassing httpx's automatic decompression.
    if content[:2] == b"\x1f\x8b":
        content = gzip.decompress(content)
    return content.decode("utf-8")


def map_transport_error(exc: httpx.HTTPError, url: str) -> Exception:
    """Translate httpx transport errors into client exceptions."""
    if isinstance(exc, httpx.TimeoutException):
        return GPPTimeoutError(f"Request to {url} timed out: {exc}")
    return GPPConnectionError(f"Could not reach {url}: {exc}")


def visibility_params(since: _dt.datetime) -> dict[str, str]:
    """Query parameters for the visibility-changes endpoint."""
    if since.tzinfo is None:
        since = since.replace(tzinfo=_dt.UTC)
    return {"since": since.astimezone(_dt.UTC).isoformat()}


def parse_visibility(text: str) -> list[VisibilityChange]:
    """Parse the visibility-changes TSV body."""
    changes = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        gid, _, timestamp = line.partition("\t")
        changes.append(
            VisibilityChange(
                gid=gid,
                changed_at=_dt.datetime.fromisoformat(timestamp.strip()),
            )
        )
    return changes
