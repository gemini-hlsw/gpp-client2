"""
Name conversions between GraphQL and Python.
"""

import keyword
import re

_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")


def split_words(name: str) -> list[str]:
    """Split a camelCase / PascalCase / snake_case name into lowercase words."""
    parts: list[str] = []
    for chunk in name.split("_"):
        if chunk:
            parts.extend(_CAMEL_BOUNDARY.split(chunk))
    return [p.lower() for p in parts if p]


def to_snake(name: str) -> str:
    """Convert a GraphQL name to snake_case."""
    return "_".join(split_words(name))


def sanitize(name: str) -> str:
    """
    Make a name a valid, non-keyword Python identifier.

    Soft keywords (``type``, ``match``, ...) are legal attribute names and
    stay untouched; only hard keywords gain a trailing underscore.
    """
    if keyword.iskeyword(name):
        return name + "_"
    if name and name[0].isdigit():
        return "_" + name
    return name


def python_field_name(graphql_name: str) -> str:
    """Python attribute name for a GraphQL field, e.g. ``includeDeleted``."""
    return sanitize(to_snake(graphql_name))


def to_pascal(name: str) -> str:
    """Convert a name to PascalCase, e.g. ``call_for_proposals``."""
    return "".join(word.capitalize() for word in split_words(name))


def python_enum_member(value: str) -> str:
    """Python member name for a GraphQL enum value."""
    return sanitize(value)


def _is_plural_of(resource: list[str], singular: list[str]) -> bool:
    """
    Whether ``resource`` is ``singular`` with exactly one word pluralized.

    Handles both ``programs``/``program`` and multi-word resources whose
    head word inflects, e.g. ``calls_for_proposals``/``call_for_proposals``.
    """
    if len(resource) != len(singular):
        return False
    diffs = [(r, s) for r, s in zip(resource, singular, strict=True) if r != s]
    return len(diffs) == 1 and diffs[0][0] == diffs[0][1] + "s"


def method_name_for_operation(operation_name: str, domain: str) -> str:
    """
    Derive the Python method name for an operation within its domain.

    The convention, measured to cover nearly the whole operation set:

    - Split the operation name into ``verb`` + ``resource`` [+ ``by_x``].
    - A resource equal to the domain name is dropped: the namespace carries
      it. Its plural (any one word gaining an ``s``) means "acts on many"
      and derives ``_all`` unless a ``by_x`` qualifier already narrows it.
    - A resource that merely starts with the domain name keeps the
      remainder: ``getSchedulerPrograms`` in ``scheduler`` derives
      ``get_programs``.

    Examples: ``getProgramById`` -> ``get_by_id``; ``getPrograms`` ->
    ``get_all``; ``getCallsForProposals`` -> ``get_all``;
    ``getGoatsObservations`` -> ``get_observations``.

    Raises
    ------
    ValueError
        If the operation name does not embed the domain resource. Rename the
        operation to say what it does, or add an explicit override.
    """
    words = split_words(operation_name)
    domain_words = split_words(domain)

    qualifier: list[str] = []
    if "by" in words:
        cut = words.index("by")
        qualifier = words[cut:]
        words = words[:cut]

    if len(words) < 2:
        raise ValueError(
            f"Operation '{operation_name}' has no verb + resource structure."
        )
    verb, resource = words[0], words[1:]

    parts = [verb]
    if resource == domain_words:
        pass
    elif _is_plural_of(resource, domain_words):
        if not qualifier:
            parts.append("all")
    elif resource[: len(domain_words)] == domain_words:
        parts.extend(resource[len(domain_words) :])
    else:
        raise ValueError(
            f"Operation '{operation_name}' names resource "
            f"'{'_'.join(resource)}', which is not domain '{domain}', its "
            "plural, or a domain-prefixed name. Rename the operation or add "
            "an override in codegen/emit_operations.py."
        )
    parts.extend(qualifier)
    return sanitize("_".join(parts))
