"""Scheduler curated tree assembly and REST endpoints over a mock transport."""

import datetime as dt

import httpx

from gpp_client.rest import VisibilityChange
from tests.conftest import graphql_response


def scheduler_programs_response():
    """One program: root group g-1 containing o-2, plus top-level o-1."""
    return graphql_response(
        {
            "programs": {
                "matches": [
                    {
                        "id": "p-1",
                        "name": "P",
                        "allGroupElements": [
                            {
                                "parentGroupId": None,
                                "observation": {"id": "o-1", "groupId": None},
                                "group": None,
                            },
                            {
                                "parentGroupId": None,
                                "observation": None,
                                "group": {"id": "g-1", "name": "G"},
                            },
                            {
                                "parentGroupId": "g-1",
                                "observation": {"id": "o-2", "groupId": "g-1"},
                                "group": None,
                            },
                        ],
                    }
                ]
            }
        }
    )


def observations_response(ids):
    return graphql_response(
        {
            "observations": {
                "hasMore": False,
                "matches": [{"id": i, "title": f"T {i}"} for i in ids],
            }
        }
    )


ATOMS_TSV = (
    "o-1\t0\ta-1\tSCIENCE\t120.0\tSCIENCE\t\t0\t2\n"
    "o-1\t1\ta-2\tSCIENCE\t60.0\tSCIENCE\t\t1\t2\n"
)


def test_get_all_assembles_tree(make_client):
    client, handler = make_client(
        scheduler_programs_response(),
        observations_response(["o-1", "o-2"]),
        httpx.Response(200, text=ATOMS_TSV),
    )
    programs = client.scheduler.get_all(programs_list=["p-1"])

    assert len(programs) == 1
    program = programs[0]
    assert "all_group_elements" not in program
    root = program["root"]
    top_ids = []
    for element in root["elements"]:
        if element.get("observation"):
            top_ids.append(element["observation"]["id"])
        else:
            top_ids.append(element["group"]["id"])
    assert top_ids == ["o-1", "g-1"]

    top_obs = root["elements"][0]["observation"]
    assert top_obs["title"] == "T o-1"
    assert [a["atom_id"] for a in top_obs["sequence"]] == ["a-1", "a-2"]

    nested = root["elements"][1]["group"]["elements"][0]["observation"]
    assert nested["id"] == "o-2"
    assert nested["sequence"] is None  # no atoms returned for o-2

    # The observation query filtered to the ids found in the tree.
    where = handler.requests[1].content
    assert b"o-1" in where and b"o-2" in where
    # Atoms were requested for both observations.
    assert handler.requests[2].content == b"o-1\no-2"


def test_get_all_trims_branches_without_ready_observations(make_client):
    client, _ = make_client(
        scheduler_programs_response(),
        observations_response(["o-1"]),  # o-2 is not READY/ONGOING
        httpx.Response(200, text=""),
    )
    programs = client.scheduler.get_all(programs_list=["p-1"])
    root = programs[0]["root"]
    assert len(root["elements"]) == 1  # empty group g-1 was trimmed
    assert root["elements"][0]["observation"]["id"] == "o-1"


def test_get_all_defaults_to_schedulable_programs(make_client):
    client, handler = make_client(
        graphql_response(
            {
                "programs": {
                    "matches": [
                        {
                            "id": "p-1",
                            "reference": {
                                "__typename": "ScienceProgramReference",
                                "label": "R-1",
                            },
                        }
                    ]
                }
            }
        ),
        scheduler_programs_response(),
        observations_response([]),
        httpx.Response(200, text=""),
    )
    client.scheduler.get_all()
    import json

    programs_body = json.loads(handler.requests[1].content)
    assert programs_body["variables"] == {"programsList": ["p-1"]}


def test_get_all_reference_labels(make_client):
    client, handler = make_client(
        graphql_response(
            {
                "programs": {
                    "matches": [
                        {
                            "id": "p-1",
                            "reference": {
                                "__typename": "ScienceProgramReference",
                                "label": "G-2025A-0001",
                            },
                        },
                        {"id": "p-2", "reference": None},
                    ]
                }
            }
        )
    )
    labels = client.scheduler.get_all_reference_labels(date="2025-08-10")
    assert labels == [("G-2025A-0001", "p-1")]
    assert handler.last_body["variables"] == {"today": "2025-08-10"}


def test_rest_endpoints_still_reachable(make_client):
    client, handler = make_client(
        httpx.Response(200, text="o-1\tabc\n"),
        httpx.Response(200, text="o-1\t2025-08-10T12:00:00Z\n"),
    )
    assert client.scheduler.atom_digests(["o-1"]) == "o-1\tabc\n"
    changes = client.scheduler.visibility_changes(dt.datetime(2025, 8, 10))
    assert changes == [
        VisibilityChange("o-1", dt.datetime(2025, 8, 10, 12, tzinfo=dt.UTC))
    ]
    assert handler.requests[0].url.path == "/scheduler/atoms"
    assert handler.requests[1].url.path == "/scheduler/visibility-changes"


async def test_async_get_all_mirrors_sync(make_async_client):
    client, _ = make_async_client(
        scheduler_programs_response(),
        observations_response(["o-1", "o-2"]),
        httpx.Response(200, text=ATOMS_TSV),
    )
    async with client:
        programs = await client.scheduler.get_all(programs_list=["p-1"])
    assert programs[0]["root"]["elements"][0]["observation"]["id"] == "o-1"
