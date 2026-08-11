"""
Scaffold a new domain: ``python -m codegen scaffold <domain>``.

Creates the operations directory and the hand-written domain module, then
prints the two wiring steps the conformance tests will enforce.
"""

from codegen import OPERATIONS_DIR, REPO_ROOT, CodegenError
from codegen.naming import to_pascal

DOMAINS_DIR = REPO_ROOT / "src" / "gpp_client2" / "domains"

_DOMAIN_TEMPLATE = '''"""
{title} domain.
"""

from gpp_client2._generated.domains import (
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
# codegen prunes per environment.
"""


def run_scaffold(domain: str) -> None:
    """Create the skeleton for a new domain."""
    domain = domain.strip().lower()
    if not domain.isidentifier():
        raise CodegenError(f"'{domain}' is not a valid domain name.")
    pascal = to_pascal(domain)
    title = domain.replace("_", " ").capitalize()

    operations_dir = OPERATIONS_DIR / domain
    module_path = DOMAINS_DIR / f"{domain}.py"
    if operations_dir.exists() or module_path.exists():
        raise CodegenError(f"Domain '{domain}' already exists.")

    operations_dir.mkdir(parents=True)
    (operations_dir / "queries.graphql").write_text(
        _OPERATIONS_TEMPLATE.format(domain=domain, pascal=pascal), encoding="utf-8"
    )
    module_path.write_text(
        _DOMAIN_TEMPLATE.format(pascal=pascal, title=title), encoding="utf-8"
    )

    print(f"Created {operations_dir.relative_to(REPO_ROOT)}/queries.graphql")
    print(f"Created {module_path.relative_to(REPO_ROOT)}")
    print()
    print("Next steps (the conformance tests enforce these):")
    print(f"  1. Write operations in graphql/operations/{domain}/")
    print("  2. uv run python -m codegen generate")
    print(
        f"  3. Register in src/gpp_client2/domains/__init__.py: "
        f'"{domain}": ("<attribute>", {pascal}API, Async{pascal}API)'
    )
    print("  4. Add the attribute to GPPClient and AsyncGPPClient in client.py")
    print("  5. uv run pytest")
