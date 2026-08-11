"""The agent skill must name every config key and CLI subcommand."""

from pathlib import Path

from gqlforge.config import _REQUIRED

SKILL_PATH = (
    Path(__file__).resolve().parents[2] / ".claude" / "skills" / "gqlforge" / "SKILL.md"
)

OPTIONAL_KEYS = (
    "model_base",
    "input_base",
    "domains_dir",
    "environments",
    "download_token",
    "token_env",
)

SUBCOMMANDS = ("generate", "check", "readiness", "download", "scaffold")


def test_skill_documents_every_config_key():
    text = SKILL_PATH.read_text(encoding="utf-8")
    for key in (*_REQUIRED, *OPTIONAL_KEYS):
        assert key in text, f"[tool.gqlforge] key '{key}' missing from the skill"


def test_skill_documents_every_subcommand():
    text = SKILL_PATH.read_text(encoding="utf-8")
    for command in SUBCOMMANDS:
        assert f"gqlforge {command}" in text, (
            f"subcommand '{command}' missing from the skill"
        )
