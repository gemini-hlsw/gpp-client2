"""
GOATS domain: bulk queries tailored to the GOATS follow-up tool.
"""

from gpp_client._generated.domains import AsyncGoatsOperations, GoatsOperations

__all__ = ["AsyncGoatsAPI", "GoatsAPI"]


class GoatsAPI(GoatsOperations):
    """
    GOATS operations.

    All generated operations are inherited; add curated helpers here.
    """


class AsyncGoatsAPI(AsyncGoatsOperations):
    """
    GOATS operations (async).

    All generated operations are inherited; add curated helpers here.
    """
