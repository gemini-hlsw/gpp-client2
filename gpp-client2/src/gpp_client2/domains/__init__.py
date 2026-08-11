"""
The hand-written domain layer.

Each domain subclasses its generated base, inheriting complete operation
coverage, and is the place for curated helpers with real logic. The registry
maps an operations-tree directory to the client attribute exposing it; a
conformance test keeps registry, client, and operations tree in lockstep.
"""

from gpp_client2.domains.attachment import AsyncAttachmentAPI, AttachmentAPI
from gpp_client2.domains.call_for_proposals import (
    AsyncCallForProposalsAPI,
    CallForProposalsAPI,
)
from gpp_client2.domains.goats import AsyncGoatsAPI, GoatsAPI
from gpp_client2.domains.observation import AsyncObservationAPI, ObservationAPI
from gpp_client2.domains.program import AsyncProgramAPI, ProgramAPI
from gpp_client2.domains.scheduler import AsyncSchedulerAPI, SchedulerAPI
from gpp_client2.domains.target import AsyncTargetAPI, TargetAPI
from gpp_client2.domains.workflow_state import (
    AsyncWorkflowStateAPI,
    WorkflowStateAPI,
)

__all__ = [
    "DOMAIN_REGISTRY",
    "AsyncAttachmentAPI",
    "AsyncCallForProposalsAPI",
    "AsyncGoatsAPI",
    "AsyncObservationAPI",
    "AsyncProgramAPI",
    "AsyncSchedulerAPI",
    "AsyncTargetAPI",
    "AsyncWorkflowStateAPI",
    "AttachmentAPI",
    "CallForProposalsAPI",
    "GoatsAPI",
    "ObservationAPI",
    "ProgramAPI",
    "SchedulerAPI",
    "TargetAPI",
    "WorkflowStateAPI",
]

DOMAIN_REGISTRY: dict[str, tuple[str, type, type]] = {
    "program": ("programs", ProgramAPI, AsyncProgramAPI),
    "observation": ("observations", ObservationAPI, AsyncObservationAPI),
    "target": ("targets", TargetAPI, AsyncTargetAPI),
    "attachment": ("attachments", AttachmentAPI, AsyncAttachmentAPI),
    "call_for_proposals": (
        "calls_for_proposals",
        CallForProposalsAPI,
        AsyncCallForProposalsAPI,
    ),
    "goats": ("goats", GoatsAPI, AsyncGoatsAPI),
    "scheduler": ("scheduler", SchedulerAPI, AsyncSchedulerAPI),
    "workflow_state": ("workflow_state", WorkflowStateAPI, AsyncWorkflowStateAPI),
}
"""Operations-tree directory -> (client attribute, sync API, async API)."""
