"""UNSET sentinel and model base behavior."""

import copy
import pickle

from pydantic import Field

from gpp_client import UNSET, UnsetType, is_set
from gpp_client._base import GPPInput, GPPModel


def test_unset_is_a_falsy_singleton():
    assert UnsetType() is UNSET
    assert not UNSET
    assert repr(UNSET) == "UNSET"


def test_unset_survives_copy_and_pickle():
    assert copy.copy(UNSET) is UNSET
    assert copy.deepcopy({"k": UNSET})["k"] is UNSET
    assert pickle.loads(pickle.dumps(UNSET)) is UNSET


def test_is_set():
    assert is_set(None)
    assert is_set(0)
    assert not is_set(UNSET)


class Sample(GPPModel):
    name: str = UNSET  # type: ignore[assignment]
    nick: str | None = UNSET  # type: ignore[assignment]
    camel_thing: int = Field(default=UNSET, alias="camelThing")  # type: ignore[assignment]


def test_model_distinguishes_unset_from_null():
    parsed = Sample.model_validate({"name": "x", "nick": None})
    assert parsed.name == "x"
    assert parsed.nick is None
    assert parsed.camel_thing is UNSET


def test_model_repr_shows_only_set_fields():
    parsed = Sample.model_validate({"name": "x"})
    assert repr(parsed) == "Sample(name='x')"
    assert str(parsed) == "Sample(name='x')"


def test_model_accepts_alias_and_python_name():
    assert Sample.model_validate({"camelThing": 3}).camel_thing == 3
    assert Sample(camel_thing=4).camel_thing == 4


class SampleInput(GPPInput):
    name: str | None = None
    other: int | None = Field(default=None, alias="otherThing")


def test_input_dump_omits_unset_keeps_null():
    assert SampleInput(name="x").graphql_dump() == {"name": "x"}
    assert SampleInput(name=None).graphql_dump() == {"name": None}
    assert SampleInput().graphql_dump() == {}


def test_input_dump_uses_aliases():
    assert SampleInput(other=1).graphql_dump() == {"otherThing": 1}


def test_input_assignment_counts_as_set():
    value = SampleInput()
    value.name = "later"
    assert value.graphql_dump() == {"name": "later"}
