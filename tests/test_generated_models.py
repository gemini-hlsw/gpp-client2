"""Generated model behavior against realistic response shapes."""

from gpp_client2 import UNSET
from gpp_client2._generated.enums import Existence, ObsStatus
from gpp_client2._generated.models import (
    Observation,
    TimingWindowEndAfter,
    TimingWindowEndAt,
)


def test_nested_observation_parses():
    observation = Observation.model_validate(
        {
            "id": "o-1",
            "existence": "PRESENT",
            "title": "A target",
            "reference": {"label": "G-2025A-0001-Q-0001"},
            "observingMode": {
                "instrument": "GMOS_NORTH",
                "mode": "GMOS_NORTH_LONG_SLIT",
                "gmosNorthLongSlit": {
                    "grating": "B1200_G5301",
                    "centralWavelength": {"nanometers": 500.0},
                },
            },
            "timingWindows": [
                {
                    "inclusion": "INCLUDE",
                    "startUtc": "2025-08-10T00:00:00Z",
                    "end": {
                        "__typename": "TimingWindowEndAt",
                        "atUtc": "2025-08-11T00:00:00Z",
                    },
                },
                {
                    "inclusion": "EXCLUDE",
                    "end": {
                        "__typename": "TimingWindowEndAfter",
                        "after": {"seconds": 3600.0},
                    },
                },
            ],
        }
    )
    assert observation.existence is Existence.PRESENT
    assert observation.reference.label == "G-2025A-0001-Q-0001"
    mode = observation.observing_mode
    assert mode.gmos_north_long_slit.central_wavelength.nanometers == 500.0
    assert mode.gmos_south_long_slit is UNSET

    first, second = observation.timing_windows
    assert isinstance(first.end, TimingWindowEndAt)
    assert isinstance(second.end, TimingWindowEndAfter)
    assert second.end.after.seconds == 3600.0


def test_enums_are_string_enums():
    assert Existence.PRESENT == "PRESENT"
    assert ObsStatus is not None
