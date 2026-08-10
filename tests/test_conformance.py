"""
Conformance: the operations tree, the generated layer, the domain registry,
and the clients stay in lockstep. A coverage gap fails here, not in review.
"""

import inspect
import json

import httpx
import pytest

from codegen import AVAILABILITY_PATH
from codegen.naming import method_name_for_operation
from codegen.operations import load_operations
from gpp_client import AsyncGPPClient, GPPClient
from gpp_client._generated.operations import (
    OPERATION_DOMAIN,
    OPERATION_KIND,
    OPERATION_TEXT,
    SCHEMA_SOURCES,
)
from gpp_client.domains import DOMAIN_REGISTRY


@pytest.fixture(scope="module")
def loaded_operations():
    return load_operations()


def test_every_operation_is_generated(loaded_operations):
    """Every operation in the tree has generated text and metadata."""
    expected = set(loaded_operations.domains)
    assert set(OPERATION_TEXT) == expected
    assert set(OPERATION_KIND) == expected
    assert set(OPERATION_DOMAIN) == expected


def test_operation_domains_match_tree(loaded_operations):
    assert loaded_operations.domains == OPERATION_DOMAIN


def test_every_domain_is_registered():
    """Every domain directory with operations appears in the registry."""
    domains = set(OPERATION_DOMAIN.values())
    assert domains == set(DOMAIN_REGISTRY), (
        "Domain registry out of sync with the operations tree. Add the "
        "missing domain to gpp_client/domains/."
    )


def test_every_operation_reachable_from_domain_api():
    """Each operation's derived method exists on its sync and async API."""
    for operation_name, domain in OPERATION_DOMAIN.items():
        method = method_name_for_operation(operation_name, domain)
        _, sync_cls, async_cls = DOMAIN_REGISTRY[domain]
        for cls in (sync_cls, async_cls):
            assert callable(getattr(cls, method, None)), (
                f"{cls.__name__} is missing '{method}' for {operation_name}"
            )


def _public_methods(cls) -> dict[str, list[str]]:
    return {
        name: [p for p in inspect.signature(member).parameters]
        for name, member in inspect.getmembers(cls, callable)
        if not name.startswith("_")
    }


def test_sync_async_parity():
    """Sync and async APIs expose identical method names and signatures."""
    for _, sync_cls, async_cls in DOMAIN_REGISTRY.values():
        assert _public_methods(sync_cls) == _public_methods(async_cls)


def test_clients_expose_every_domain():
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={}))
    with GPPClient(
        url="http://odb.test", schema="development", token="t", transport=transport
    ) as client:
        for attribute, sync_cls, _ in DOMAIN_REGISTRY.values():
            assert isinstance(getattr(client, attribute), sync_cls)

    async_client = AsyncGPPClient(
        url="http://odb.test", schema="development", token="t"
    )
    for attribute, _, async_cls in DOMAIN_REGISTRY.values():
        assert isinstance(getattr(async_client, attribute), async_cls)


def test_availability_manifest_matches_generated_map():
    """graphql/availability.json agrees with the generated operation map."""
    manifest = json.loads(AVAILABILITY_PATH.read_text(encoding="utf-8"))
    assert tuple(manifest["sources"]) == SCHEMA_SOURCES
    for name, texts in OPERATION_TEXT.items():
        assert sorted(texts) == manifest["operations"][name]


def test_operation_kinds_are_query_or_mutation():
    assert set(OPERATION_KIND.values()) <= {"query", "mutation"}
