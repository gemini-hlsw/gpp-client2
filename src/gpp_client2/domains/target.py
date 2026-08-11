"""
Target domain.
"""

from gpp_client2._generated.domains import AsyncTargetOperations, TargetOperations

__all__ = ["AsyncTargetAPI", "TargetAPI"]


class TargetAPI(TargetOperations):
    """
    Target operations.

    All generated operations are inherited; add curated helpers here.
    """


class AsyncTargetAPI(AsyncTargetOperations):
    """
    Target operations (async).

    All generated operations are inherited; add curated helpers here.
    """
