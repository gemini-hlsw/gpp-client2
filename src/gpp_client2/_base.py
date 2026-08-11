"""
Base machinery shared by generated models: the UNSET sentinel and the
pydantic base classes for output models and inputs.
"""

from __future__ import annotations

from typing import Any, Final, Literal, TypeGuard, TypeVar

from pydantic import BaseModel, ConfigDict

_T = TypeVar("_T")

__all__ = ["UNSET", "GPPInput", "GPPModel", "UnsetType", "is_set"]


class UnsetType:
    """
    Sentinel for "this field was not selected by the operation".

    Distinct from ``None``, which means the server returned null. Falsy, so
    ``if observation.title:`` behaves sensibly either way.
    """

    _instance: UnsetType | None = None

    def __new__(cls) -> UnsetType:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __bool__(self) -> Literal[False]:
        return False

    def __repr__(self) -> str:
        return "UNSET"

    def __copy__(self) -> UnsetType:
        return self

    def __deepcopy__(self, memo: dict[int, Any]) -> UnsetType:
        return self

    def __reduce__(self) -> tuple[type[UnsetType], tuple[()]]:
        return (UnsetType, ())


UNSET: Final[UnsetType] = UnsetType()
"""The singleton UnsetType instance."""


def is_set(value: _T | UnsetType) -> TypeGuard[_T]:
    """Report whether a model field value was actually selected/returned."""
    return not isinstance(value, UnsetType)


class GPPModel(BaseModel):
    """
    Base for generated output models.

    Every field defaults to ``UNSET``; a parsed response sets only the fields
    the operation selected. ``repr`` shows set fields only.
    """

    model_config = ConfigDict(populate_by_name=True)

    def __repr__(self) -> str:
        parts = ", ".join(
            f"{name}={getattr(self, name)!r}"
            for name in type(self).model_fields
            if name in self.model_fields_set
        )
        return f"{type(self).__name__}({parts})"

    def __str__(self) -> str:
        return self.__repr__()


class GPPInput(BaseModel):
    """
    Base for generated input models.

    Serialization sends only fields that were explicitly set, so "omitted"
    and "explicitly null" stay distinct - exactly GraphQL's semantics.
    """

    model_config = ConfigDict(populate_by_name=True)

    def graphql_dump(self) -> dict[str, Any]:
        """Serialize for use inside GraphQL variables."""
        return self.model_dump(mode="json", by_alias=True, exclude_unset=True)
