"""
Runtime configuration resolution.

Configuration resolves per field with the following precedence, highest
first:

1. Explicit constructor arguments.
2. ``GPP_*`` environment variables (``GPP_ENVIRONMENT``, ``GPP_URL``,
   ``GPP_TOKEN``, ``GPP_PROFILE``, ``GPP_SCHEMA_SOURCE``).
3. The profile named by ``GPP_PROFILE`` or ``default_profile`` in the config
   file (``~/.gpp-client2/config.toml``).

There is no silent fallback: a client with no resolvable environment or
token raises an error that names the profiles that are configured.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import typer

from gpp_client2.environments import Environment, spec_for
from gpp_client2.errors import AuthError, GPPConfigError

__all__ = [
    "ResolvedConfig",
    "find_download_token",
    "get_config_path",
    "load_profiles",
    "resolve_config",
]

_CONFIG_ENV_VAR = "GPP_CONFIG_FILE"


def get_config_path() -> Path:
    """
    Path of the configuration file.

    ``$GPP_CONFIG_FILE`` overrides. Otherwise ``~/.gpp-client2`` applies on
    every Unix (``force_posix``, so macOS and Linux resolve identically)
    and ``%APPDATA%\\gpp-client2`` on Windows, via
    :func:`typer.get_app_dir`.
    """
    override = os.environ.get(_CONFIG_ENV_VAR)
    if override:
        return Path(override).expanduser()
    return Path(typer.get_app_dir("gpp-client2", force_posix=True)) / "config.toml"


def load_profiles(
    config_path: Path | None = None,
) -> tuple[str | None, dict[str, dict[str, Any]]]:
    """
    Load the profile table from the config file.

    Returns
    -------
    tuple[str | None, dict[str, dict[str, Any]]]
        The ``default_profile`` name (if any) and the profile table. A
        missing file yields ``(None, {})``.
    """
    path = config_path if config_path is not None else get_config_path()
    if not path.is_file():
        return None, {}
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise GPPConfigError(f"Invalid config file at {path}: {exc}") from exc

    profiles = data.get("profiles", {})
    if not isinstance(profiles, dict) or not all(
        isinstance(v, dict) for v in profiles.values()
    ):
        raise GPPConfigError(f"'profiles' must be a table of tables in {path}.")
    return data.get("default_profile"), profiles


@dataclass(frozen=True)
class ResolvedConfig:
    """
    Fully resolved client configuration.

    Parameters
    ----------
    environment : Environment | None
        The resolved environment, or ``None`` for a custom URL without one.
    base_url : str
        Base URL of the deployment to talk to.
    schema_source : str
        Committed schema source whose generated query text is used.
    token : str
        API token.
    profile : str | None
        Name of the profile that contributed values, if any.
    """

    environment: Environment | None
    base_url: str
    schema_source: str
    token: str
    profile: str | None

    @property
    def environment_name(self) -> str:
        """Environment name, or ``"custom"`` for an explicit URL."""
        return self.environment.value if self.environment else "custom"


def resolve_config(
    *,
    environment: Environment | str | None = None,
    profile: str | None = None,
    url: str | None = None,
    schema: str | None = None,
    token: str | None = None,
    available_sources: tuple[str, ...],
    config_path: Path | None = None,
) -> ResolvedConfig:
    """
    Resolve explicit arguments, environment variables, and the config file
    into a complete client configuration.

    Raises
    ------
    GPPConfigError
        If no environment or URL can be resolved, or a profile or schema
        source is unknown.
    AuthError
        If no token can be resolved.
    """
    environment = environment or os.environ.get("GPP_ENVIRONMENT") or None
    url = url or os.environ.get("GPP_URL") or None
    schema = schema or os.environ.get("GPP_SCHEMA_SOURCE") or None
    token = token or os.environ.get("GPP_TOKEN") or None
    profile = profile or os.environ.get("GPP_PROFILE") or None

    default_profile, profiles = load_profiles(config_path)
    profile_name = profile or default_profile
    profile_data: dict[str, Any] = {}
    if profile_name is not None:
        if profile_name not in profiles:
            configured = ", ".join(sorted(profiles)) or "none"
            raise GPPConfigError(
                f"Unknown profile '{profile_name}'. Configured profiles: "
                f"{configured}. Config file: {config_path or get_config_path()}."
            )
        profile_data = profiles[profile_name]

    if environment is None and "environment" in profile_data:
        environment = str(profile_data["environment"])
    if environment is not None:
        try:
            environment = Environment(environment)
        except ValueError:
            valid = ", ".join(e.value for e in Environment)
            raise GPPConfigError(
                f"Unknown environment '{environment}'. Valid environments: {valid}."
            ) from None

    url = url or profile_data.get("url")

    if url is not None:
        base_url = str(url)
    elif environment is not None:
        spec = spec_for(environment)
        if spec.base_url is None:
            raise GPPConfigError(
                f"The {environment.value} environment has no deployment URL "
                "yet. Pass 'url' explicitly or set 'GPP_URL'."
            )
        base_url = spec.base_url
    else:
        configured = ", ".join(sorted(profiles)) or "none"
        raise GPPConfigError(
            "No GPP environment configured. Pass 'environment' or 'url', set "
            "'GPP_ENVIRONMENT', or select a profile (configured profiles: "
            f"{configured}; config file: {config_path or get_config_path()})."
        )

    schema_source = schema or profile_data.get("schema_source")
    if schema_source is None:
        if environment is not None:
            schema_source = spec_for(environment).schema_source
        else:
            # Custom URL with no stated schema: assume the newest, since a
            # local ODB is usually running the latest code.
            schema_source = available_sources[0]
    if schema_source not in available_sources:
        raise GPPConfigError(
            f"Unknown schema source '{schema_source}'. This package has "
            f"generated query text for: {', '.join(available_sources)}."
        )

    token = token or profile_data.get("token")
    if not token:
        target = environment.value if environment else "the configured URL"
        raise AuthError(
            f"A token is required for {target}. Set 'GPP_TOKEN', pass "
            "'token', or add one to your profile."
        )

    return ResolvedConfig(
        environment=environment,
        base_url=base_url.rstrip("/"),
        schema_source=str(schema_source),
        token=str(token),
        profile=profile_name,
    )


def find_download_token(environment_name: str) -> str | None:
    """
    Best token for downloading an environment's schema (used by codegen).

    A profile configured for that environment wins; ``GPP_TOKEN`` is the
    fallback.
    """
    _, profiles = load_profiles()
    for profile_data in profiles.values():
        if str(
            profile_data.get("environment", "")
        ).lower() == environment_name and profile_data.get("token"):
            return str(profile_data["token"])
    return os.environ.get("GPP_TOKEN")
