"""
Program domain.
"""

from gpp_client2._generated.domains import AsyncProgramOperations, ProgramOperations

__all__ = ["AsyncProgramAPI", "ProgramAPI"]


class ProgramAPI(ProgramOperations):
    """
    Program operations.

    All generated operations are inherited; add curated helpers here.
    """


class AsyncProgramAPI(AsyncProgramOperations):
    """
    Program operations (async).

    All generated operations are inherited; add curated helpers here.
    """
