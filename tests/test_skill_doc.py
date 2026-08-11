"""
The usage skill must stay in lockstep with the public API.

Any client attribute, public domain method, or exported error type missing
from .claude/skills/gpp-client2/SKILL.md fails here - the same philosophy as
the conformance tests: documentation gaps break CI, not users.
"""

import inspect
from pathlib import Path

import pytest

import gpp_client2
from gpp_client2.domains import DOMAIN_REGISTRY

SKILL_PATH = (
    Path(__file__).resolve().parent.parent
    / ".claude"
    / "skills"
    / "gpp-client2"
    / "SKILL.md"
)


@pytest.fixture(scope="module")
def skill_text() -> str:
    assert SKILL_PATH.is_file(), f"Missing usage skill at {SKILL_PATH}"
    return SKILL_PATH.read_text(encoding="utf-8")


def test_every_client_attribute_documented(skill_text):
    for attribute, _, _ in DOMAIN_REGISTRY.values():
        assert f"client.{attribute}" in skill_text, (
            f"SKILL.md does not mention client.{attribute}; update the skill "
            "alongside the API change."
        )


def test_every_public_method_documented(skill_text):
    for attribute, sync_cls, _ in DOMAIN_REGISTRY.values():
        for name, _member in inspect.getmembers(sync_cls, callable):
            if name.startswith("_"):
                continue
            assert f"`{name}" in skill_text or f"{name}(" in skill_text, (
                f"SKILL.md does not mention {attribute}.{name}; update the "
                "skill alongside the API change."
            )


def test_every_error_documented(skill_text):
    for name in gpp_client2.__all__:
        if name.startswith("GPP") and name.endswith("Error"):
            assert name in skill_text, (
                f"SKILL.md does not mention {name}; update the skill "
                "alongside the API change."
            )


def test_core_exports_documented(skill_text):
    for name in ("GPPClient", "AsyncGPPClient", "UNSET", "is_set", "supports"):
        assert name in skill_text


def test_gotchas_section_present(skill_text):
    assert "## Gotchas" in skill_text, (
        "The gotcha section captures observed failure modes; do not drop it."
    )
