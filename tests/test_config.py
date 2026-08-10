"""Configuration resolution unit tests."""

import pytest

from gpp_client.config import find_download_token, resolve_config
from gpp_client.environments import Environment
from gpp_client.errors import GPPAuthError, GPPConfigError

SOURCES = ("development", "production")


def write_config(tmp_path, text: str):
    path = tmp_path / "config.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_explicit_arguments_win():
    config = resolve_config(
        environment="development", token="tok", available_sources=SOURCES
    )
    assert config.environment is Environment.DEVELOPMENT
    assert config.schema_source == "development"
    assert config.base_url.startswith("https://")
    assert config.token == "tok"


def test_environment_is_case_insensitive():
    config = resolve_config(
        environment="PRODUCTION", token="tok", available_sources=SOURCES
    )
    assert config.environment is Environment.PRODUCTION
    assert config.schema_source == "production"


def test_env_vars_apply(monkeypatch):
    monkeypatch.setenv("GPP_ENVIRONMENT", "production")
    monkeypatch.setenv("GPP_TOKEN", "env-tok")
    config = resolve_config(available_sources=SOURCES)
    assert config.environment is Environment.PRODUCTION
    assert config.token == "env-tok"


def test_explicit_beats_env_var(monkeypatch):
    monkeypatch.setenv("GPP_ENVIRONMENT", "production")
    config = resolve_config(
        environment="development", token="tok", available_sources=SOURCES
    )
    assert config.environment is Environment.DEVELOPMENT


def test_profile_resolution(tmp_path):
    path = write_config(
        tmp_path,
        """
        default_profile = "dev"

        [profiles.dev]
        environment = "development"
        token = "dev-tok"

        [profiles.prod]
        environment = "production"
        token = "prod-tok"
        """,
    )
    config = resolve_config(available_sources=SOURCES, config_path=path)
    assert config.profile == "dev"
    assert config.token == "dev-tok"

    config = resolve_config(profile="prod", available_sources=SOURCES, config_path=path)
    assert config.environment is Environment.PRODUCTION
    assert config.token == "prod-tok"


def test_profile_env_var_selects_profile(tmp_path, monkeypatch):
    path = write_config(
        tmp_path,
        """
        [profiles.prod]
        environment = "production"
        token = "prod-tok"
        """,
    )
    monkeypatch.setenv("GPP_PROFILE", "prod")
    config = resolve_config(available_sources=SOURCES, config_path=path)
    assert config.profile == "prod"


def test_unknown_profile_names_configured_ones(tmp_path):
    path = write_config(tmp_path, "[profiles.dev]\nenvironment = 'development'\n")
    with pytest.raises(GPPConfigError, match="dev"):
        resolve_config(profile="nope", available_sources=SOURCES, config_path=path)


def test_nothing_configured_is_a_clear_error():
    with pytest.raises(GPPConfigError, match="No GPP environment configured"):
        resolve_config(available_sources=SOURCES)


def test_missing_token_is_auth_error():
    with pytest.raises(GPPAuthError, match="token"):
        resolve_config(environment="development", available_sources=SOURCES)


def test_staging_without_url_is_clear_error():
    with pytest.raises(GPPConfigError, match="staging"):
        resolve_config(environment="staging", token="tok", available_sources=SOURCES)


def test_custom_url_defaults_to_newest_schema():
    config = resolve_config(
        url="http://localhost:8080", token="tok", available_sources=SOURCES
    )
    assert config.environment is None
    assert config.environment_name == "custom"
    assert config.schema_source == "development"


def test_unknown_schema_source_is_rejected():
    with pytest.raises(GPPConfigError, match="schema source"):
        resolve_config(
            url="http://x", schema="nope", token="tok", available_sources=SOURCES
        )


def test_unknown_environment_is_rejected():
    with pytest.raises(GPPConfigError, match="Unknown environment"):
        resolve_config(environment="qa", token="tok", available_sources=SOURCES)


def test_invalid_toml_is_config_error(tmp_path):
    path = write_config(tmp_path, "not [valid toml")
    with pytest.raises(GPPConfigError, match="Invalid config"):
        resolve_config(
            environment="development",
            token="t",
            available_sources=SOURCES,
            config_path=path,
        )


def test_find_download_token_prefers_matching_profile(tmp_path, monkeypatch):
    path = write_config(
        tmp_path,
        """
        [profiles.dev]
        environment = "development"
        token = "dev-tok"
        """,
    )
    monkeypatch.setenv("GPP_CONFIG_FILE", str(path))
    monkeypatch.setenv("GPP_TOKEN", "fallback")
    assert find_download_token("development") == "dev-tok"
    assert find_download_token("production") == "fallback"
