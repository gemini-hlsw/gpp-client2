"""
Live write round-trip tests: create -> read -> update -> delete, against the
deployment resolved from the default profile.

Safety rules, encoded below and enforced at runtime:

- Hard creation budget: at most 2 items per domain, at most 50 total
  (authorized 2026-08-10).
- Every created item is recorded by exact ID in a ledger file before anything
  else happens; deletion only ever targets recorded IDs, never name matches.
- A leftover ledger from a crashed run is cleaned up first, so runs are
  repeatable.
- Item names are neutral dummy values with a per-run nonce.

Double opt-in: these run only with ``-m live`` AND ``GPP_LIVE_WRITE=1``:

    GPP_LIVE_WRITE=1 uv run pytest tests/test_live_roundtrip.py -m live
"""

import asyncio
import datetime as dt
import json
import os
import threading
import time
import uuid
from pathlib import Path

import pytest

from gpp_client2 import AsyncGPPClient, GPPClient, is_set
from gpp_client2._generated.enums import EditType, Existence, TimingWindowInclusion
from gpp_client2._generated.inputs import (
    BandBrightnessIntegratedInput,
    BandNormalizedIntegratedInput,
    CreateObservationInput,
    ObservationPropertiesInput,
    ProgramPropertiesInput,
    SchedulingConstraintsInput,
    SiderealInput,
    SourceProfileInput,
    SpectralDefinitionIntegratedInput,
    TargetEnvironmentInput,
    TargetPropertiesInput,
    TimingWindowInput,
    UnnormalizedSedInput,
)
from tests.test_live import has_live_configuration

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        os.environ.get("GPP_LIVE_WRITE") != "1",
        reason="Write tests require explicit opt-in via GPP_LIVE_WRITE=1.",
    ),
    pytest.mark.skipif(
        not has_live_configuration(),
        reason="No GPP configuration (config file or GPP_TOKEN) available.",
    ),
]

MAX_PER_DOMAIN = 2
MAX_TOTAL = 50
LEDGER_PATH = Path(__file__).resolve().parent.parent / ".live-test-ledger.json"

NONCE = uuid.uuid4().hex[:8]


class ArtifactTracker:
    """
    Records every created item and is the only authority for deletion.

    The ledger is written to disk immediately after each create so a crashed
    run leaves an exact record; the next run deletes those leftovers first.
    """

    def __init__(self, client: GPPClient):
        self.client = client
        self.created: list[dict[str, str]] = []

    def _api_for(self, domain: str):
        return {
            "program": self.client.programs,
            "observation": self.client.observations,
            "target": self.client.targets,
        }[domain]

    def check_budget(self, domain: str) -> None:
        """Fail BEFORE a create that would exceed the authorized budget."""
        per_domain = sum(1 for e in self.created if e["domain"] == domain)
        assert per_domain < MAX_PER_DOMAIN, f"budget: {MAX_PER_DOMAIN}/{domain}"
        assert len(self.created) < MAX_TOTAL, f"budget: {MAX_TOTAL} total"

    def register(self, domain: str, item_id: str, name: str) -> None:
        self.created.append({"domain": domain, "id": item_id, "name": name})
        self._save()

    def delete(self, entry: dict[str, str]):
        """Delete a tracked item and return the mutation result."""
        result = self._api_for(entry["domain"]).delete_by_id(entry["id"])
        self.created = [e for e in self.created if e is not entry]
        self._save()
        return result

    def cleanup(self) -> None:
        """Delete every remaining tracked item, newest first."""
        for entry in reversed(list(self.created)):
            try:
                self.delete(entry)
            except Exception as exc:  # keep going; report at the end
                print(f"CLEANUP FAILURE for {entry}: {exc}")
        self._save()

    def _save(self) -> None:
        if self.created:
            LEDGER_PATH.write_text(
                json.dumps({"created": self.created}, indent=2), encoding="utf-8"
            )
        elif LEDGER_PATH.exists():
            LEDGER_PATH.unlink()

    def heal_previous_run(self) -> None:
        """Delete exact-ID leftovers a crashed earlier run recorded."""
        if not LEDGER_PATH.exists():
            return
        leftovers = json.loads(LEDGER_PATH.read_text(encoding="utf-8")).get(
            "created", []
        )
        for entry in reversed(leftovers):
            try:
                self._api_for(entry["domain"]).delete_by_id(entry["id"])
                print(f"healed leftover {entry['domain']} {entry['id']}")
            except Exception as exc:
                print(f"could not heal leftover {entry}: {exc}")
        LEDGER_PATH.unlink()


@pytest.fixture(scope="module")
def tracker():
    client = GPPClient()
    tracker = ArtifactTracker(client)
    tracker.heal_previous_run()
    yield tracker
    tracker.cleanup()
    client.close()


@pytest.fixture(scope="module")
def live_program(tracker):
    tracker.check_budget("program")
    program = tracker.client.programs.create(
        properties=ProgramPropertiesInput(
            name=f"Test program {NONCE}",
            description="Temporary engineering test entry",
        )
    )
    assert program is not None and is_set(program.id)
    tracker.register("program", program.id, program.name)
    return program


@pytest.fixture(scope="module")
def live_target(tracker, live_program):
    tracker.check_budget("target")
    target = tracker.client.targets.create_by_program_id(
        live_program.id,
        properties=TargetPropertiesInput(
            name=f"Test target {NONCE}",
            sidereal=SiderealInput(
                ra={"hms": "05:35:17.3"},
                dec={"dms": "-05:23:28.0"},
                epoch="J2000.000",
            ),
            source_profile=SourceProfileInput(
                point=SpectralDefinitionIntegratedInput(
                    band_normalized=BandNormalizedIntegratedInput(
                        sed=UnnormalizedSedInput(stellar_library="O5_V"),
                        brightnesses=[
                            BandBrightnessIntegratedInput(
                                band="R", value=15.0, units="VEGA_MAGNITUDE"
                            )
                        ],
                    )
                )
            ),
        ),
    )
    assert target is not None and is_set(target.id)
    tracker.register("target", target.id, target.name)
    return target


@pytest.fixture(scope="module")
def live_observation(tracker, live_program, live_target):
    tracker.check_budget("observation")
    observation = tracker.client.observations.create(
        input=CreateObservationInput(
            program_id=live_program.id,
            set=ObservationPropertiesInput(
                subtitle=f"Test observation {NONCE}",
                target_environment=TargetEnvironmentInput(
                    asterism=[live_target.id],
                ),
            ),
        )
    )
    assert observation is not None and is_set(observation.id)
    tracker.register("observation", observation.id, f"Test observation {NONCE}")
    return observation


class TestProgramRoundTrip:
    def test_create_shape(self, live_program):
        assert live_program.name == f"Test program {NONCE}"
        assert live_program.existence is Existence.PRESENT

    def test_update_and_refetch(self, tracker, live_program):
        result = tracker.client.programs.update_by_id(
            live_program.id,
            properties=ProgramPropertiesInput(description=f"updated {NONCE}"),
        )
        assert result.programs[0].description == f"updated {NONCE}"
        fetched = tracker.client.programs.get_by_id(live_program.id)
        assert fetched.description == f"updated {NONCE}"


class TestTargetRoundTrip:
    def test_create_shape(self, live_target):
        assert live_target.name == f"Test target {NONCE}"
        sidereal = live_target.sidereal
        assert is_set(sidereal) and sidereal is not None
        assert abs(sidereal.ra.hours - 5.5881) < 0.01

    def test_update_and_refetch(self, tracker, live_target):
        result = tracker.client.targets.update_by_id(
            live_target.id,
            properties=TargetPropertiesInput(name=f"Test target {NONCE} v2"),
        )
        assert result.targets[0].name == f"Test target {NONCE} v2"

    def test_restore_cycle(self, tracker, live_target):
        deleted = tracker.client.targets.delete_by_id(live_target.id)
        assert deleted.targets[0].existence is Existence.DELETED
        restored = tracker.client.targets.restore_by_id(live_target.id)
        assert restored.targets[0].existence is Existence.PRESENT


class TestObservationRoundTrip:
    def test_create_shape(self, tracker, live_observation, live_target):
        fetched = tracker.client.observations.get_by_id(live_observation.id)
        assert fetched.subtitle == f"Test observation {NONCE}"
        asterism = fetched.target_environment.asterism
        assert [t.name for t in asterism] == [f"Test target {NONCE} v2"]

    def test_timestamp_round_trip(self, tracker, live_observation):
        # The one serialization choice live reads could not verify: Timestamp
        # inputs are sent as ISO-8601 UTC with a Z suffix.
        instant = dt.datetime(2026, 9, 1, 12, 30, 45, tzinfo=dt.UTC)
        result = tracker.client.observations.update_by_id(
            live_observation.id,
            properties=ObservationPropertiesInput(
                scheduling_constraints=SchedulingConstraintsInput(
                    timing_windows=[
                        TimingWindowInput(
                            inclusion=TimingWindowInclusion.INCLUDE,
                            start_utc=instant,
                        )
                    ]
                )
            ),
        )
        windows = result.observations[0].timing_windows
        assert len(windows) == 1
        returned = windows[0].start_utc
        if returned.tzinfo is None:
            returned = returned.replace(tzinfo=dt.UTC)
        assert returned == instant


class TestSubscriptionRoundTrip:
    """
    A real event round-trip: watch the test program while updating it.

    Only updates to the already-tracked program - no additional creates.
    The updater pokes repeatedly because subscribing and updating race:
    the first poke can land before the subscription is active, but a later
    one is guaranteed to land after it.
    """

    def _poke(self, tracker, program_id: str, sequence: int) -> None:
        tracker.client.programs.update_by_id(
            program_id,
            properties=ProgramPropertiesInput(
                description=f"subscription poke {NONCE} {sequence}"
            ),
        )

    def test_sync_watch_receives_update_event(self, tracker, live_program):
        received: dict[str, object] = {}

        def consume():
            stream = tracker.client.programs.watch_edits(program_id=live_program.id)
            for event in stream:
                if event.edit_type is EditType.UPDATED:
                    received["event"] = event
                    break

        watcher = threading.Thread(target=consume, daemon=True)
        watcher.start()
        deadline = time.monotonic() + 30
        sequence = 0
        while watcher.is_alive() and time.monotonic() < deadline:
            sequence += 1
            self._poke(tracker, live_program.id, sequence)
            watcher.join(timeout=3)
        assert "event" in received, "no subscription event arrived within 30s"
        event = received["event"]
        assert event.value.id == live_program.id

    async def test_async_watch_receives_update_event(self, tracker, live_program):
        async with AsyncGPPClient() as watcher_client:
            stream = watcher_client.programs.watch_edits(program_id=live_program.id)

            async def consume():
                async for event in stream:
                    if event.edit_type is EditType.UPDATED:
                        return event
                return None

            task = asyncio.create_task(consume())
            event = None
            try:
                for sequence in range(10):
                    self._poke(tracker, live_program.id, 100 + sequence)
                    done, _ = await asyncio.wait({task}, timeout=3)
                    if done:
                        event = task.result()
                        break
            finally:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
                await stream.aclose()
            assert event is not None, "no subscription event arrived"
            assert event.value.id == live_program.id


class TestDeletion:
    """Explicit delete verification; the tracker teardown is the backstop."""

    def test_delete_all_created(
        self, tracker, live_program, live_target, live_observation
    ):
        order = {"observation": 0, "target": 1, "program": 2}
        entries = sorted(list(tracker.created), key=lambda e: order[e["domain"]])
        assert len(entries) == 3
        for entry in entries:
            result = tracker.delete(entry)
            items = getattr(result, entry["domain"] + "s")
            assert items[0].existence is Existence.DELETED, entry

    def test_ledger_is_clean(self, tracker):
        assert tracker.created == []
        assert not LEDGER_PATH.exists()
