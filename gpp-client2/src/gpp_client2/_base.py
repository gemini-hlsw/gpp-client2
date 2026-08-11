"""
Model-base machinery, re-exported from the vendored gqlforge runtime.

``GPPModel`` and ``GPPInput`` are the GPP-branded names for the vendored
``Model`` and ``Input`` base classes - the same class objects, so
``isinstance`` checks and subclassing behave identically either way.
"""

from gpp_client2._generated._base import (
    UNSET,
    UnsetType,
    is_set,
)
from gpp_client2._generated._base import (
    Input as GPPInput,
)
from gpp_client2._generated._base import (
    Model as GPPModel,
)

__all__ = ["UNSET", "GPPInput", "GPPModel", "UnsetType", "is_set"]
