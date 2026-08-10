"""Workflow-state curated logic over a mock transport."""

import pytest

from gpp_client._generated.enums import ObservationWorkflowState
from gpp_client._generated.models import ObservationWorkflow
from gpp_client.errors import GPPRetryableError, GPPValidationError
from tests.conftest import graphql_response


def observation_payload(
    calculation_state="READY", state="DEFINED", valid_transitions=("INACTIVE",)
):
    return graphql_response(
        {
            "observation": {
                "id": "o-1",
                "workflow": {
                    "state": calculation_state,
                    "value": {
                        "state": state,
                        "validTransitions": list(valid_transitions),
                        "validationErrors": [],
                    },
                },
            }
        }
    )


def test_update_executes_valid_transition(make_client):
    client, handler = make_client(
        observation_payload(valid_transitions=("INACTIVE", "READY")),
        graphql_response(
            {
                "setObservationWorkflowState": {
                    "state": "INACTIVE",
                    "validTransitions": ["DEFINED"],
                }
            }
        ),
    )
    workflow = client.workflow_state.update_by_observation_id(
        "o-1", state=ObservationWorkflowState.INACTIVE
    )
    assert isinstance(workflow, ObservationWorkflow)
    assert workflow.state is ObservationWorkflowState.INACTIVE
    assert handler.last_body["operationName"] == "setWorkflowStateByObservationId"
    assert handler.last_body["variables"] == {
        "observationId": "o-1",
        "state": "INACTIVE",
    }


def test_update_short_circuits_when_already_set(make_client):
    client, handler = make_client(observation_payload(state="INACTIVE"))
    workflow = client.workflow_state.update_by_observation_id(
        "o-1", state=ObservationWorkflowState.INACTIVE
    )
    assert workflow.state is ObservationWorkflowState.INACTIVE
    assert len(handler.requests) == 1  # only the read; no mutation sent


def test_update_raises_retryable_while_calculating(make_client):
    client, _ = make_client(observation_payload(calculation_state="CALCULATING"))
    with pytest.raises(GPPRetryableError, match="not READY"):
        client.workflow_state.update_by_observation_id(
            "o-1", state=ObservationWorkflowState.INACTIVE
        )


def test_update_rejects_invalid_transition(make_client):
    client, handler = make_client(observation_payload(valid_transitions=("READY",)))
    with pytest.raises(GPPValidationError, match="Valid transitions: READY"):
        client.workflow_state.update_by_observation_id(
            "o-1", state=ObservationWorkflowState.INACTIVE
        )
    assert len(handler.requests) == 1


def test_retry_loop_until_ready(make_client):
    client, handler = make_client(
        observation_payload(calculation_state="CALCULATING"),
        observation_payload(valid_transitions=("INACTIVE",)),
        graphql_response({"setObservationWorkflowState": {"state": "INACTIVE"}}),
    )
    workflow = client.workflow_state.update_by_observation_id_with_retry(
        "o-1",
        state=ObservationWorkflowState.INACTIVE,
        max_attempts=3,
        retry_delay=0.0,
    )
    assert workflow.state is ObservationWorkflowState.INACTIVE
    assert len(handler.requests) == 3


def test_retry_exhaustion_raises(make_client):
    client, _ = make_client(
        *[observation_payload(calculation_state="CALCULATING") for _ in range(2)]
    )
    with pytest.raises(GPPRetryableError, match="after 2 attempt"):
        client.workflow_state.update_by_observation_id_with_retry(
            "o-1",
            state=ObservationWorkflowState.INACTIVE,
            max_attempts=2,
            retry_delay=0.0,
        )


async def test_async_update_mirrors_sync(make_async_client):
    client, _ = make_async_client(
        observation_payload(valid_transitions=("INACTIVE",)),
        graphql_response({"setObservationWorkflowState": {"state": "INACTIVE"}}),
    )
    async with client:
        workflow = await client.workflow_state.update_by_observation_id(
            "o-1", state=ObservationWorkflowState.INACTIVE
        )
    assert workflow.state is ObservationWorkflowState.INACTIVE


def test_workflow_query_shape(make_client):
    client, handler = make_client(observation_payload())
    observation = client.workflow_state.get_by_observation_id("o-1")
    assert observation.workflow.value.state is ObservationWorkflowState.DEFINED
    assert handler.last_body["operationName"] == "getWorkflowStateByObservationId"


def test_read_only_blocks_set(make_client):
    client, handler = make_client(read_only=True)
    with pytest.raises(Exception, match="read-only"):
        client.workflow_state.set_by_observation_id(
            "o-1", state=ObservationWorkflowState.INACTIVE
        )
    assert handler.requests == []
