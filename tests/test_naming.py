"""Naming convention unit tests."""

import pytest

from codegen.naming import (
    method_name_for_operation,
    python_field_name,
    sanitize,
    split_words,
    to_pascal,
    to_snake,
)


def test_split_words():
    assert split_words("getProgramById") == ["get", "program", "by", "id"]
    assert split_words("GNIRSFragment") == ["gnirs", "fragment"]
    assert split_words("call_for_proposals") == ["call", "for", "proposals"]


def test_to_snake():
    assert to_snake("includeDeleted") == "include_deleted"
    assert to_snake("WHERE") == "where"
    assert to_snake("saveSVCImages") == "save_svc_images"


def test_sanitize_hard_keywords_only():
    assert sanitize("and") == "and_"
    assert sanitize("in") == "in_"
    assert sanitize("type") == "type"  # soft keyword, legal attribute
    assert sanitize("match") == "match"


def test_python_field_name():
    assert python_field_name("AND") == "and_"
    assert python_field_name("includeDeleted") == "include_deleted"


def test_to_pascal():
    assert to_pascal("call_for_proposals") == "CallForProposals"
    assert to_pascal("program") == "Program"


@pytest.mark.parametrize(
    ("operation", "domain", "expected"),
    [
        ("getProgramById", "program", "get_by_id"),
        ("getPrograms", "program", "get_all"),
        ("createProgram", "program", "create"),
        ("updatePrograms", "program", "update_all"),
        ("updateProgramById", "program", "update_by_id"),
        ("deleteProgramById", "program", "delete_by_id"),
        ("restoreProgramById", "program", "restore_by_id"),
        ("cloneObservation", "observation", "clone"),
        ("createTargetByProgramReference", "target", "create_by_program_reference"),
        ("getObservationByReference", "observation", "get_by_reference"),
        ("updateObservations", "observation", "update_all"),
        ("getCallsForProposals", "call_for_proposals", "get_all"),
        ("updateCallsForProposals", "call_for_proposals", "update_all"),
        ("getCallForProposalsById", "call_for_proposals", "get_by_id"),
        ("getSchedulerPrograms", "scheduler", "get_programs"),
        ("getSchedulerProgramIds", "scheduler", "get_program_ids"),
        ("getGoatsObservations", "goats", "get_observations"),
        ("getAttachmentsByProgramId", "attachment", "get_by_program_id"),
        ("setWorkflowStateByObservationId", "workflow_state", "set_by_observation_id"),
    ],
)
def test_method_name_for_operation(operation, domain, expected):
    assert method_name_for_operation(operation, domain) == expected


def test_method_name_rejects_wrong_resource():
    with pytest.raises(ValueError, match="not domain"):
        method_name_for_operation("getProgramById", "observation")


def test_method_name_rejects_verb_only():
    with pytest.raises(ValueError, match="verb"):
        method_name_for_operation("ping", "program")
