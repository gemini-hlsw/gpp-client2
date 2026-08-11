"""
Operation execution, re-exported from the vendored gqlforge runtime.

The GPP-specific executor-core specialization (restricted-field preflight
for raw queries) lives in :mod:`gpp_client2.client`.
"""

from gpp_client2._generated._executor import (
    AsyncExecutor,
    ExecutorCore,
    SyncExecutor,
    serialize_variable,
)

__all__ = ["AsyncExecutor", "ExecutorCore", "SyncExecutor", "serialize_variable"]
