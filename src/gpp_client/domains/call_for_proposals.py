"""
Call for Proposals domain.
"""

from gpp_client._generated.domains import (
    AsyncCallForProposalsOperations,
    CallForProposalsOperations,
)

__all__ = ["AsyncCallForProposalsAPI", "CallForProposalsAPI"]


class CallForProposalsAPI(CallForProposalsOperations):
    """
    Call for Proposals operations.

    All generated operations are inherited; add curated helpers here.
    """


class AsyncCallForProposalsAPI(AsyncCallForProposalsOperations):
    """
    Call for Proposals operations (async).

    All generated operations are inherited; add curated helpers here.
    """
