"""
Observation domain.
"""

from gpp_client._generated.domains import (
    AsyncObservationOperations,
    ObservationOperations,
)

__all__ = ["AsyncObservationAPI", "ObservationAPI"]


class ObservationAPI(ObservationOperations):
    """
    Observation operations.

    All generated operations are inherited; add curated helpers here.
    """


class AsyncObservationAPI(AsyncObservationOperations):
    """
    Observation operations (async).

    All generated operations are inherited; add curated helpers here.
    """
