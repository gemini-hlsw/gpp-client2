"""
Observation workflow state domain.

The curated ``update_by_observation_id`` methods wrap the raw mutation with
the guard rails users otherwise reimplement: wait for the background
calculation, short-circuit when the state is already set, and validate the
requested transition against ``validTransitions`` before touching the server.
"""

from __future__ import annotations

import asyncio
import logging
import time

from gpp_client2._base import is_set
from gpp_client2._generated.domains import (
    AsyncWorkflowStateOperations,
    WorkflowStateOperations,
)
from gpp_client2._generated.enums import CalculationState, ObservationWorkflowState
from gpp_client2._generated.models import (
    CalculatedObservationWorkflow,
    Observation,
    ObservationWorkflow,
)
from gpp_client2.errors import ClientError, GPPRetryableError, GPPValidationError

__all__ = ["AsyncWorkflowStateAPI", "WorkflowStateAPI"]

logger = logging.getLogger(__name__)


def _workflow_of(
    observation: Observation | None, observation_id: str
) -> CalculatedObservationWorkflow:
    if (
        observation is None
        or not is_set(observation.workflow)
        or observation.workflow is None
    ):
        raise ClientError(f"Observation '{observation_id}' has no workflow data.")
    return observation.workflow


def _check_ready(workflow: CalculatedObservationWorkflow) -> None:
    """Raise GPPRetryableError while the background calculation is running."""
    if workflow.state is not CalculationState.READY:
        raise GPPRetryableError(
            "Observation calculation is not READY (current state: "
            f"{workflow.state}). Retry after background processing completes."
        )


def _check_transition(
    workflow: CalculatedObservationWorkflow, state: ObservationWorkflowState
) -> ObservationWorkflow | None:
    """
    Validate a requested transition.

    Returns the current workflow when the state is already set (nothing to
    do), ``None`` when the transition should proceed, and raises when it is
    not allowed.
    """
    if workflow.value.state is state:
        return workflow.value
    valid = (
        workflow.value.valid_transitions
        if is_set(workflow.value.valid_transitions)
        else []
    )
    if state not in (valid or []):
        rendered = ", ".join(t.value for t in valid or []) or "none"
        raise GPPValidationError(
            f"Cannot transition to '{state.value}'. Valid transitions: {rendered}."
        )
    return None


class WorkflowStateAPI(WorkflowStateOperations):
    """
    Observation workflow state operations.
    """

    def update_by_observation_id(
        self,
        observation_id: str,
        *,
        state: ObservationWorkflowState,
    ) -> ObservationWorkflow:
        """
        Set an observation's workflow state, validating the transition first.

        Parameters
        ----------
        observation_id : str
            The observation ID.
        state : ObservationWorkflowState
            The desired workflow state.

        Returns
        -------
        ObservationWorkflow
            The workflow after the operation (unchanged when the state was
            already set).

        Raises
        ------
        GPPRetryableError
            If the observation calculation is not READY yet.
        GPPValidationError
            If the requested transition is not allowed.
        """
        observation = self.get_by_observation_id(observation_id)
        workflow = _workflow_of(observation, observation_id)
        _check_ready(workflow)
        current = _check_transition(workflow, state)
        if current is not None:
            logger.debug(
                "Workflow state for %s already %s; no update needed.",
                observation_id,
                state.value,
            )
            return current
        updated = self.set_by_observation_id(observation_id, state=state)
        if updated is None:
            raise ClientError("setObservationWorkflowState returned no payload.")
        return updated

    def update_by_observation_id_with_retry(
        self,
        observation_id: str,
        *,
        state: ObservationWorkflowState,
        max_attempts: int = 10,
        initial_delay: float = 0.0,
        retry_delay: float = 1.0,
    ) -> ObservationWorkflow:
        """
        Set an observation's workflow state, retrying while the background
        calculation is not READY.

        Parameters
        ----------
        observation_id : str
            The observation ID.
        state : ObservationWorkflowState
            The desired workflow state.
        max_attempts : int, default=10
            Maximum number of attempts.
        initial_delay : float, default=0.0
            Seconds to wait before the first attempt.
        retry_delay : float, default=1.0
            Seconds between attempts.

        Returns
        -------
        ObservationWorkflow
            The workflow after the operation.

        Raises
        ------
        GPPRetryableError
            If the calculation is still not READY after every attempt.
        GPPValidationError
            If the requested transition is not allowed.
        """
        time.sleep(initial_delay)
        for attempt in range(1, max_attempts + 1):
            try:
                return self.update_by_observation_id(observation_id, state=state)
            except GPPRetryableError:
                logger.debug(
                    "Attempt %d/%d: calculation not ready for %s.",
                    attempt,
                    max_attempts,
                    observation_id,
                )
                if attempt < max_attempts:
                    time.sleep(retry_delay)
        raise GPPRetryableError(
            f"Observation '{observation_id}' calculation was not READY after "
            f"{max_attempts} attempt(s)."
        )


class AsyncWorkflowStateAPI(AsyncWorkflowStateOperations):
    """
    Observation workflow state operations (async).
    """

    async def update_by_observation_id(
        self,
        observation_id: str,
        *,
        state: ObservationWorkflowState,
    ) -> ObservationWorkflow:
        """
        Set an observation's workflow state, validating the transition first.

        Parameters
        ----------
        observation_id : str
            The observation ID.
        state : ObservationWorkflowState
            The desired workflow state.

        Returns
        -------
        ObservationWorkflow
            The workflow after the operation (unchanged when the state was
            already set).

        Raises
        ------
        GPPRetryableError
            If the observation calculation is not READY yet.
        GPPValidationError
            If the requested transition is not allowed.
        """
        observation = await self.get_by_observation_id(observation_id)
        workflow = _workflow_of(observation, observation_id)
        _check_ready(workflow)
        current = _check_transition(workflow, state)
        if current is not None:
            logger.debug(
                "Workflow state for %s already %s; no update needed.",
                observation_id,
                state.value,
            )
            return current
        updated = await self.set_by_observation_id(observation_id, state=state)
        if updated is None:
            raise ClientError("setObservationWorkflowState returned no payload.")
        return updated

    async def update_by_observation_id_with_retry(
        self,
        observation_id: str,
        *,
        state: ObservationWorkflowState,
        max_attempts: int = 10,
        initial_delay: float = 0.0,
        retry_delay: float = 1.0,
    ) -> ObservationWorkflow:
        """
        Set an observation's workflow state, retrying while the background
        calculation is not READY.

        Parameters
        ----------
        observation_id : str
            The observation ID.
        state : ObservationWorkflowState
            The desired workflow state.
        max_attempts : int, default=10
            Maximum number of attempts.
        initial_delay : float, default=0.0
            Seconds to wait before the first attempt.
        retry_delay : float, default=1.0
            Seconds between attempts.

        Returns
        -------
        ObservationWorkflow
            The workflow after the operation.

        Raises
        ------
        GPPRetryableError
            If the calculation is still not READY after every attempt.
        GPPValidationError
            If the requested transition is not allowed.
        """
        await asyncio.sleep(initial_delay)
        for attempt in range(1, max_attempts + 1):
            try:
                return await self.update_by_observation_id(observation_id, state=state)
            except GPPRetryableError:
                logger.debug(
                    "Attempt %d/%d: calculation not ready for %s.",
                    attempt,
                    max_attempts,
                    observation_id,
                )
                if attempt < max_attempts:
                    await asyncio.sleep(retry_delay)
        raise GPPRetryableError(
            f"Observation '{observation_id}' calculation was not READY after "
            f"{max_attempts} attempt(s)."
        )
