"""
The GPP deployment environments.

Which environment a client talks to is a runtime choice. Adding an
environment is one entry in :data:`ENVIRONMENTS` plus a committed schema.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

__all__ = ["ENVIRONMENTS", "Environment", "EnvironmentSpec", "spec_for"]


class Environment(StrEnum):
    """A GPP deployment environment. Accepts any case on construction."""

    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"

    @classmethod
    def _missing_(cls, value: object) -> Environment | None:
        if isinstance(value, str):
            normalized = value.strip().lower()
            for member in cls:
                if member.value == normalized:
                    return member
        return None


@dataclass(frozen=True)
class EnvironmentSpec:
    """
    Static metadata describing a GPP environment.

    Parameters
    ----------
    environment : Environment
        The environment this spec describes.
    base_url : str | None
        Base URL of the deployment, or ``None`` if not yet deployed.
    schema_source : str
        Committed schema whose generated query text this environment uses
        (a file stem under ``graphql/schemas/``).
    rank : int
        Distance ahead of production; production is 0. Orders the schema
        chain in tooling and reports.
    """

    environment: Environment
    base_url: str | None
    schema_source: str
    rank: int

    @property
    def name(self) -> str:
        """The environment's name, e.g. ``"development"``."""
        return self.environment.value


ENVIRONMENTS: tuple[EnvironmentSpec, ...] = (
    EnvironmentSpec(
        environment=Environment.DEVELOPMENT,
        base_url="https://lucuma-postgres-odb-dev.herokuapp.com",
        schema_source="development",
        rank=2,
    ),
    EnvironmentSpec(
        environment=Environment.STAGING,
        # No staging deployment exists yet. When one appears: set its URL,
        # commit graphql/schemas/staging.graphql, and flip schema_source.
        base_url=None,
        schema_source="production",
        rank=1,
    ),
    EnvironmentSpec(
        environment=Environment.PRODUCTION,
        base_url="https://lucuma-postgres-odb-production.herokuapp.com",
        schema_source="production",
        rank=0,
    ),
)
"""All known environments, newest first."""


def spec_for(environment: Environment | str) -> EnvironmentSpec:
    """Return the spec for an environment."""
    env = Environment(environment)
    for spec in ENVIRONMENTS:
        if spec.environment is env:
            return spec
    raise KeyError(env)  # unreachable while ENVIRONMENTS covers the enum
