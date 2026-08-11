"""Environment registry unit tests."""

import pytest

from gpp_client2.environments import ENVIRONMENTS, Environment, spec_for


def test_case_insensitive_construction():
    assert Environment("DEVELOPMENT") is Environment.DEVELOPMENT
    assert Environment(" production ") is Environment.PRODUCTION
    with pytest.raises(ValueError):
        Environment("qa")


def test_every_environment_has_a_spec():
    assert {spec.environment for spec in ENVIRONMENTS} == set(Environment)


def test_ordered_newest_first():
    ranks = [spec.rank for spec in ENVIRONMENTS]
    assert ranks == sorted(ranks, reverse=True)
    assert ENVIRONMENTS[-1].environment is Environment.PRODUCTION
    assert ENVIRONMENTS[-1].rank == 0


def test_spec_for():
    spec = spec_for("development")
    assert spec.environment is Environment.DEVELOPMENT
    assert spec.base_url and spec.base_url.startswith("https://")
    assert spec_for(Environment.PRODUCTION).schema_source == "production"


def test_staging_tracks_production_schema_until_deployed():
    spec = spec_for("staging")
    assert spec.base_url is None
    assert spec.schema_source == "production"
