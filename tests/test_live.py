"""
Live smoke tests against a real deployment.

These run only when a usable profile exists (config file or GPP_* env vars).
They are read-only: no mutations.

Run with: uv run pytest tests/test_live.py -m live
"""

import os
from pathlib import Path

import pytest

from gpp_client import AsyncGPPClient, GPPClient

pytestmark = pytest.mark.live


def _default_config() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg).expanduser() if xdg else Path.home() / ".config"
    return base / "gpp-client" / "config.toml"


def has_live_configuration() -> bool:
    return bool(os.environ.get("GPP_TOKEN")) or _default_config().is_file()


requires_live = pytest.mark.skipif(
    not has_live_configuration(),
    reason="No GPP configuration (config file or GPP_TOKEN) available.",
)


@pytest.fixture
def live_client(monkeypatch):
    # Undo the test-suite isolation: live tests want the real config.
    monkeypatch.delenv("GPP_CONFIG_FILE", raising=False)
    with GPPClient(read_only=True) as client:
        yield client


@requires_live
def test_ping(live_client):
    ok, reason = live_client.ping()
    assert ok, reason


@requires_live
def test_programs_get_all(live_client):
    result = live_client.programs.get_all(limit=1)
    assert result.matches is not None


@requires_live
def test_observations_get_all(live_client):
    result = live_client.observations.get_all(limit=1)
    assert result.matches is not None


@requires_live
def test_targets_get_all(live_client):
    result = live_client.targets.get_all(limit=1)
    assert result.matches is not None


@requires_live
def test_calls_for_proposals_get_all(live_client):
    result = live_client.calls_for_proposals.get_all(limit=1)
    assert result.matches is not None


@requires_live
def test_goats_get_programs(live_client):
    result = live_client.goats.get_programs()
    assert result.matches is not None


@requires_live
def test_scheduler_get_program_ids(live_client):
    programs = live_client.scheduler.get_program_ids()
    assert isinstance(programs, list)


@requires_live
async def test_async_client_ping(monkeypatch):
    monkeypatch.delenv("GPP_CONFIG_FILE", raising=False)
    async with AsyncGPPClient(read_only=True) as client:
        ok, reason = await client.ping()
    assert ok, reason
