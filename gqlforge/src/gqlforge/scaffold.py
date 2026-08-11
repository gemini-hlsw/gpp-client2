"""
Scaffold a new domain: ``gqlforge scaffold <domain>``.

Creates the operations directory and the hand-written domain module, then
prints the two wiring steps the conformance tests will enforce.
"""

from gqlforge import GqlforgeError
from gqlforge.config import Config
from gqlforge.naming import to_pascal

_DOMAIN_TEMPLATE = '''"""
{title} domain.
"""

from {generated_package}.domains import (
    Async{pascal}Operations,
    {pascal}Operations,
)

__all__ = ["Async{pascal}API", "{pascal}API"]


class {pascal}API({pascal}Operations):
    """
    {title} operations.

    All generated operations are inherited; add curated helpers here.
    """


class Async{pascal}API(Async{pascal}Operations):
    """
    {title} operations (async).

    All generated operations are inherited; add curated helpers here.
    """
'''

_OPERATIONS_TEMPLATE = """\
# Operations for the {domain} domain. Name them <verb><Resource>[By<Key>]
# (e.g. get{pascal}ById, get{pascal}s, create{pascal}) so method names derive
# automatically. Write the union of selections across all environments;
# gqlforge prunes per environment.
"""


def run_scaffold(config: Config, domain: str) -> None:
    """Create the skeleton for a new domain."""
    if config.domains_dir is None:
        raise GqlforgeError(
            "Scaffolding needs [tool.gqlforge] domains_dir - the directory "
            "for hand-written domain modules."
        )
    domain = domain.strip().lower()
    if not domain.isidentifier():
        raise GqlforgeError(f"'{domain}' is not a valid domain name.")
    pascal = to_pascal(domain)
    title = domain.replace("_", " ").capitalize()

    operations_dir = config.operations_dir / domain
    module_path = config.domains_dir / f"{domain}.py"
    if operations_dir.exists() or module_path.exists():
        raise GqlforgeError(f"Domain '{domain}' already exists.")

    operations_dir.mkdir(parents=True)
    (operations_dir / "queries.graphql").write_text(
        _OPERATIONS_TEMPLATE.format(domain=domain, pascal=pascal), encoding="utf-8"
    )
    module_path.write_text(
        _DOMAIN_TEMPLATE.format(
            pascal=pascal, title=title, generated_package=config.generated_package
        ),
        encoding="utf-8",
    )

    root = config.root
    print(f"Created {operations_dir.relative_to(root)}/queries.graphql")
    print(f"Created {module_path.relative_to(root)}")
    print()
    print("Next steps (the conformance tests enforce these):")
    print(f"  1. Write operations in {operations_dir.relative_to(root)}/")
    print("  2. uv run gqlforge generate")
    print(
        f"  3. Register in {config.domains_dir.relative_to(root)}/__init__.py: "
        f'"{domain}": ("<attribute>", {pascal}API, Async{pascal}API)'
    )
    print("  4. Add the attribute to your sync and async client classes")
    print("  5. Run your test suite")
