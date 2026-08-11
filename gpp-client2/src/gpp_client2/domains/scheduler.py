"""
Scheduler domain.

Combines the scheduler's GraphQL queries, its REST file endpoints, and the
curated ``get_all`` that assembles each program's group tree with full
observation data and atom-digest sequences - the shape the Scheduler service
actually consumes.
"""

from __future__ import annotations

import datetime as _dt
import logging
from collections.abc import Sequence
from typing import Any

import httpx

from gpp_client2._executor import AsyncExecutor, SyncExecutor
from gpp_client2._generated.domains import (
    AsyncObservationOperations,
    AsyncSchedulerOperations,
    ObservationOperations,
    SchedulerOperations,
)
from gpp_client2._generated.enums import ObservationWorkflowState
from gpp_client2._generated.inputs import (
    WhereCalculatedObservationWorkflow,
    WhereObservation,
    WhereOptionEqObservingModeType,
    WhereOrderObservationId,
    WhereOrderObservationWorkflowState,
)
from gpp_client2._generated.models import Program
from gpp_client2.rest import (
    VisibilityChange,
    map_transport_error,
    parse_visibility,
    process_text,
    visibility_params,
)

__all__ = ["AsyncSchedulerAPI", "SchedulerAPI"]

logger = logging.getLogger(__name__)

_ATOMS_PATH = "/scheduler/atoms"
_VISIBILITY_PATH = "/scheduler/visibility-changes"

_ATOM_COLUMNS = (
    "atom_idx",
    "atom_id",
    "observe_class",
    "time_estimate",
    "step_types",
    "lamp_types",
    "step_index",
    "step_count",
)


def _parse_atom_digests(text: str) -> dict[str, list[dict[str, str]]]:
    """Parse the atoms TSV into observation id -> ordered atom rows."""
    mapping: dict[str, list[dict[str, str]]] = {}
    for line in text.split("\n"):
        if not line.strip():
            continue
        observation_id, *values = line.split("\t")
        mapping.setdefault(observation_id, []).append(
            dict(zip(_ATOM_COLUMNS, values, strict=True))
        )
    return mapping


def _ready_where(observation_ids: list[str]) -> WhereObservation:
    """Observations in the list that are READY/ONGOING with an observing mode."""
    return WhereObservation(
        id=WhereOrderObservationId(in_=observation_ids),
        workflow=WhereCalculatedObservationWorkflow(
            workflow_state=WhereOrderObservationWorkflowState(
                in_=[
                    ObservationWorkflowState.READY,
                    ObservationWorkflowState.ONGOING,
                ]
            )
        ),
        observing_mode_type=WhereOptionEqObservingModeType(is_null=False),
    )


def _build_roots(programs: list[dict[str, Any]]) -> list[str]:
    """
    Rebuild each program's group tree from its flattened elements.

    Mutates each program dict, adding a ``root`` node, and returns every
    observation id encountered.
    """
    observation_ids: list[str] = []
    for program in programs:
        root: dict[str, Any] = {"name": "root", "elements": []}
        by_id: dict[str, dict[str, Any]] = {}
        children: dict[str, list[dict[str, Any]]] = {}

        for element in program.get("all_group_elements") or []:
            parent_id = element.get("parent_group_id")
            observation = element.get("observation")
            group = element.get("group")
            if parent_id is None:
                root["elements"].append(element)
                node = observation or group
                by_id[node["id"]] = element
                if observation:
                    observation_ids.append(observation["id"])
            else:
                children.setdefault(parent_id, []).append(element)
                if group:
                    by_id[group["id"]] = element
                else:
                    observation_ids.append(observation["id"])

        for parent_id, kids in children.items():
            parent = by_id.get(parent_id)
            if parent is None:
                logger.warning("Parent group %s not found in mapping", parent_id)
                continue
            parent["group"]["elements"] = kids

        program["root"] = root
    return observation_ids


def _fill_tree(
    node: dict[str, Any],
    observations: dict[str, dict[str, Any]],
    sequences: dict[str, list[dict[str, str]]],
) -> bool:
    """
    Replace observation stubs with full data, trimming empty branches.

    Returns ``True`` when the node still carries observation data after the
    walk.
    """
    observation = node.get("observation")
    group = node.get("group")
    if observation is not None:
        data = observations.get(observation["id"])
        if data is None:
            node["observation"] = None
            return False
        data["sequence"] = sequences.get(observation["id"])
        node["observation"] = data
        return True
    if group is not None:
        group["elements"] = [
            child
            for child in group.get("elements") or []
            if _fill_tree(child, observations, sequences)
        ]
        return bool(group["elements"])
    node["elements"] = [
        child
        for child in node["elements"]
        if _fill_tree(child, observations, sequences)
    ]
    return bool(node["elements"])


def _dump_programs(programs_models: list[Program]) -> list[dict[str, Any]]:
    return [p.model_dump(exclude_unset=True) for p in programs_models]


def _finish(
    programs: list[dict[str, Any]],
    observation_matches: list[Any],
    atoms_text: str | None,
) -> list[dict[str, Any]]:
    """Fill the rebuilt trees with observation data and sequences."""
    observations = {
        o["id"]: o
        for o in (m.model_dump(exclude_unset=True) for m in observation_matches)
    }
    sequences = _parse_atom_digests(atoms_text) if atoms_text else {}
    for program in programs:
        _fill_tree(program["root"], observations, sequences)
        program.pop("all_group_elements", None)
    return programs


class SchedulerAPI(SchedulerOperations):
    """
    Scheduler operations: GraphQL queries, REST file endpoints, and the
    assembled program tree.
    """

    def __init__(self, executor: SyncExecutor, http: httpx.Client) -> None:
        super().__init__(executor)
        self._http = http

    def atom_digests(self, observation_ids: Sequence[str]) -> str:
        """
        Request atom digests for the given observation IDs.

        Parameters
        ----------
        observation_ids : Sequence[str]
            Internal observation IDs to request.

        Returns
        -------
        str
            TSV data, one row per line.
        """
        try:
            response = self._http.post(
                _ATOMS_PATH,
                content="\n".join(observation_ids),
                headers={"Content-Type": "text/plain"},
            )
        except httpx.HTTPError as exc:
            raise map_transport_error(exc, str(self._http.base_url)) from exc
        return process_text(response)

    def visibility_changes(self, since: _dt.datetime) -> list[VisibilityChange]:
        """
        Observations and targets with visibility changes since a time.

        Parameters
        ----------
        since : datetime.datetime
            Return entities whose visibility-relevant inputs changed at or
            after this time. Naive datetimes are assumed to be UTC.

        Returns
        -------
        list[VisibilityChange]
            One entry per changed entity.
        """
        try:
            response = self._http.get(_VISIBILITY_PATH, params=visibility_params(since))
        except httpx.HTTPError as exc:
            raise map_transport_error(exc, str(self._http.base_url)) from exc
        return parse_visibility(process_text(response))

    def get_all_reference_labels(
        self, date: str | None = None
    ) -> list[tuple[str, str]]:
        """
        Reference labels and IDs of every schedulable program.

        Parameters
        ----------
        date : str | None, optional
            Date for the active-interval filter; defaults to today (UTC).

        Returns
        -------
        list[tuple[str, str]]
            ``(reference label, program id)`` pairs.
        """
        today = (
            _dt.date.fromisoformat(date) if date else _dt.datetime.now(_dt.UTC).date()
        )
        programs = self.get_program_ids(today=today)
        return [(p.reference.label, p.id) for p in programs if p.reference]

    def get_all(self, programs_list: list[str] | None = None) -> list[dict[str, Any]]:
        """
        Fetch programs with a complete group tree and observation data.

        Each program dict gains a ``root`` node whose elements nest groups
        and observations; observations carry their atom-digest ``sequence``.
        Branches without any READY/ONGOING observation are trimmed.

        Parameters
        ----------
        programs_list : list[str] | None, optional
            Program IDs to fetch; defaults to every schedulable program.

        Returns
        -------
        list[dict[str, Any]]
            One dict per program.
        """
        if not programs_list:
            programs_list = [p.id for p in self.get_program_ids()]
        programs = _dump_programs(self.get_programs(programs_list=programs_list))
        observation_ids = _build_roots(programs)
        matches: list[Any] = []
        atoms_text = None
        if observation_ids:
            observations_api = ObservationOperations(self._executor)
            matches = observations_api.get_all(
                where=_ready_where(observation_ids), include_deleted=False
            ).matches
            atoms_text = self.atom_digests(observation_ids)
        return _finish(programs, matches, atoms_text)


class AsyncSchedulerAPI(AsyncSchedulerOperations):
    """
    Scheduler operations (async): GraphQL queries, REST file endpoints, and
    the assembled program tree.
    """

    def __init__(self, executor: AsyncExecutor, http: httpx.AsyncClient) -> None:
        super().__init__(executor)
        self._http = http

    async def atom_digests(self, observation_ids: Sequence[str]) -> str:
        """
        Request atom digests for the given observation IDs.

        Parameters
        ----------
        observation_ids : Sequence[str]
            Internal observation IDs to request.

        Returns
        -------
        str
            TSV data, one row per line.
        """
        try:
            response = await self._http.post(
                _ATOMS_PATH,
                content="\n".join(observation_ids),
                headers={"Content-Type": "text/plain"},
            )
        except httpx.HTTPError as exc:
            raise map_transport_error(exc, str(self._http.base_url)) from exc
        return process_text(response)

    async def visibility_changes(self, since: _dt.datetime) -> list[VisibilityChange]:
        """
        Observations and targets with visibility changes since a time.

        Parameters
        ----------
        since : datetime.datetime
            Return entities whose visibility-relevant inputs changed at or
            after this time. Naive datetimes are assumed to be UTC.

        Returns
        -------
        list[VisibilityChange]
            One entry per changed entity.
        """
        try:
            response = await self._http.get(
                _VISIBILITY_PATH, params=visibility_params(since)
            )
        except httpx.HTTPError as exc:
            raise map_transport_error(exc, str(self._http.base_url)) from exc
        return parse_visibility(process_text(response))

    async def get_all_reference_labels(
        self, date: str | None = None
    ) -> list[tuple[str, str]]:
        """
        Reference labels and IDs of every schedulable program.

        Parameters
        ----------
        date : str | None, optional
            Date for the active-interval filter; defaults to today (UTC).

        Returns
        -------
        list[tuple[str, str]]
            ``(reference label, program id)`` pairs.
        """
        today = (
            _dt.date.fromisoformat(date) if date else _dt.datetime.now(_dt.UTC).date()
        )
        programs = await self.get_program_ids(today=today)
        return [(p.reference.label, p.id) for p in programs if p.reference]

    async def get_all(
        self, programs_list: list[str] | None = None
    ) -> list[dict[str, Any]]:
        """
        Fetch programs with a complete group tree and observation data.

        Each program dict gains a ``root`` node whose elements nest groups
        and observations; observations carry their atom-digest ``sequence``.
        Branches without any READY/ONGOING observation are trimmed.

        Parameters
        ----------
        programs_list : list[str] | None, optional
            Program IDs to fetch; defaults to every schedulable program.

        Returns
        -------
        list[dict[str, Any]]
            One dict per program.
        """
        if not programs_list:
            programs_list = [p.id for p in await self.get_program_ids()]
        programs = _dump_programs(await self.get_programs(programs_list=programs_list))
        observation_ids = _build_roots(programs)
        matches: list[Any] = []
        atoms_text = None
        if observation_ids:
            observations_api = AsyncObservationOperations(self._executor)
            result = await observations_api.get_all(
                where=_ready_where(observation_ids), include_deleted=False
            )
            matches = result.matches
            atoms_text = await self.atom_digests(observation_ids)
        return _finish(programs, matches, atoms_text)
