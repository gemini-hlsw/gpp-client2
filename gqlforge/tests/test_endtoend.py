"""End-to-end generation against a minimal single-schema consumer.

Exercises the no-domains layout (operations at the tree root), leading
``#`` comment blocks becoming method docstrings, schema descriptions
becoming model docstrings, and models-only mode (no operations tree).
"""

import pytest

from gqlforge.config import Config
from gqlforge.pipeline import run_generate

SCHEMA = '''
"""A thing the demo API serves."""
type Widget {
  id: ID!
  """Human-readable widget name."""
  name: String
}

type Query {
  """Fetch one widget."""
  widget(id: ID!): Widget
}
'''

OPERATIONS = """\
# This file's header comment is separated by a blank line and must not
# become a docstring.

# Fetch a widget by its identifier.
# Returns UNSET fields for anything not selected.
query getWidgetById($id: ID!) {
  widget(id: $id) {
    id
    name
  }
}

query getWidgetNameById($id: ID!) {
  widget(id: $id) {
    name
  }
}
"""

PYPROJECT = """\
[tool.gqlforge]
schemas = "schemas"
operations = "operations"
output = "out/_generated"
merged_schema = "schemas/merged.graphql"
availability = "availability.json"
source_order = ["main"]
generated_package = "democlient._generated"
runtime_package = "democlient"
model_base = "Model"
input_base = "Input"
"""


@pytest.fixture
def consumer(tmp_path):
    (tmp_path / "pyproject.toml").write_text(PYPROJECT, encoding="utf-8")
    (tmp_path / "schemas").mkdir()
    (tmp_path / "schemas" / "main.graphql").write_text(SCHEMA, encoding="utf-8")
    return tmp_path


def test_flat_single_schema_generation(consumer):
    (consumer / "operations").mkdir()
    (consumer / "operations" / "queries.graphql").write_text(
        OPERATIONS, encoding="utf-8"
    )
    run_generate(Config.load(consumer))

    domains = (consumer / "out" / "_generated" / "domains.py").read_text()
    # Root-level operations form the anonymous domain: plain class names.
    assert "class Operations:" in domains
    assert "class AsyncOperations:" in domains
    # No domain to strip, so the resource stays in the method name.
    assert "def get_widget_by_id(" in domains
    # The leading comment block is the docstring, verbatim and multi-line.
    assert "Fetch a widget by its identifier." in domains
    assert "Returns UNSET fields for anything not selected." in domains
    # The blank-line-separated file header is not attached to anything.
    assert "must not" not in domains
    # Without a comment, the schema root-field description is the summary.
    assert "Fetch one widget." in domains
    # Configured runtime and base names appear in the emitted imports.
    assert "from democlient._executor import AsyncExecutor, SyncExecutor" in domains
    models = (consumer / "out" / "_generated" / "models.py").read_text()
    assert "class Widget(Model):" in models
    assert "A thing the demo API serves." in models
    availability = (consumer / "availability.json").read_text()
    assert '"main"' in availability


def test_models_only_generation(consumer):
    run_generate(Config.load(consumer))

    generated = consumer / "out" / "_generated"
    assert (generated / "models.py").is_file()
    assert (generated / "enums.py").is_file()
    assert not (generated / "domains.py").exists()
    assert not (generated / "operations.py").exists()
    models = (generated / "models.py").read_text()
    assert "class Widget(Model):" in models
