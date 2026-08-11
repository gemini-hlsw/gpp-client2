"""
Live smoke tests against a real deployment.

These run only when a usable profile exists (config file or GPP_* env vars).
They are read-only: no mutations.

Run with: uv run pytest tests/test_live.py -m live
"""

import asyncio
import os

import pytest

from gpp_client2 import AsyncGPPClient, GPPClient
from gpp_client2._generated.models import ProgramEdit
from gpp_client2.config import get_config_path

pytestmark = pytest.mark.live


def has_live_configuration() -> bool:
    return bool(os.environ.get("GPP_TOKEN")) or get_config_path().is_file()


requires_live = pytest.mark.skipif(
    not has_live_configuration(),
    reason="No GPP configuration (config file or GPP_TOKEN) available.",
)


@pytest.fixture
def live_client():
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
async def test_async_client_ping():
    async with AsyncGPPClient(read_only=True) as client:
        ok, reason = await client.ping()
    assert ok, reason


@requires_live
async def test_subscription_handshake():
    """
    The deployment's /ws endpoint accepts our graphql-transport-ws handshake.

    Reaching the event wait proves connect + auth + ack + subscribe were all
    accepted (each failure mode raises a GPP error instead). Silence within
    the window is the expected outcome; an event only arrives if someone
    happens to edit a visible program, and that is fine too.
    """
    async with AsyncGPPClient(read_only=True, timeout=15.0) as client:
        stream = client.programs.watch_edits()
        try:
            event = await asyncio.wait_for(anext(stream), timeout=5)
            assert isinstance(event, ProgramEdit)
        except TimeoutError:
            pass
        finally:
            await stream.aclose()
