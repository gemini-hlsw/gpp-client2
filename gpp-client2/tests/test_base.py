"""
The model-base shim: GPP names for the vendored runtime bases.

The behavior of the bases themselves (UNSET semantics, unset-vs-null,
input serialization) is pinned in gqlforge's ``tests/test_runtime.py``;
here we pin only that gpp-client2 re-exports the very same objects under
its established names, so isinstance checks and user subclasses keep
working across the package boundary.
"""

from gpp_client2 import UNSET, UnsetType, is_set
from gpp_client2._base import GPPInput, GPPModel
from gpp_client2._generated import _base as vendored


def test_shim_reexports_the_vendored_objects():
    assert GPPModel is vendored.Model
    assert GPPInput is vendored.Input
    assert UNSET is vendored.UNSET
    assert UnsetType is vendored.UnsetType
    assert is_set is vendored.is_set


def test_generated_models_inherit_the_shimmed_bases():
    from gpp_client2._generated.inputs import ProgramPropertiesInput
    from gpp_client2._generated.models import Program

    assert issubclass(Program, GPPModel)
    assert issubclass(ProgramPropertiesInput, GPPInput)


def test_unset_round_trip_through_a_generated_model():
    from gpp_client2._generated.models import Program

    program = Program.model_validate({"id": "p-1", "name": None})
    assert program.id == "p-1"
    assert program.name is None
    assert program.description is UNSET
    assert not is_set(program.description)
