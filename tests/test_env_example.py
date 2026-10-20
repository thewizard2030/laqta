"""`.env.example` must document every environment variable the code reads.

An undocumented variable is a secret nobody can discover or a gate nobody
knows exists. This test compares the two settings classes with the example
file, so the documentation cannot drift away from the code.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_EXAMPLE = REPO_ROOT / ".env.example"

BACKEND_CONFIG = REPO_ROOT / "backend" / "app" / "core" / "config.py"
CORE_CONFIG = REPO_ROOT / "qatta" / "core" / "config.py"

# Documented, but not a settings field: they are read directly from the
# environment by third-party libraries or by the process launcher.
ALLOWED_EXTRA = {
    "QATTA_ARABISH_PROMPT_TEXT",  # covered by the core field
}


def _backend_env_names() -> set[str]:
    source = BACKEND_CONFIG.read_text(encoding="utf-8")
    return {
        f"QATTA_{match.group(1)}"
        for match in re.finditer(r"^    ([A-Z][A-Z0-9_]+):\s", source, re.MULTILINE)
    }


def _core_env_names() -> set[str]:
    source = CORE_CONFIG.read_text(encoding="utf-8")
    return {
        f"QATTA_{match.group(1).upper()}"
        for match in re.finditer(r"^    ([a-z][a-z0-9_]+):\s", source, re.MULTILINE)
    }


def _documented_env_names() -> set[str]:
    source = ENV_EXAMPLE.read_text(encoding="utf-8")
    return set(re.findall(r"^#?\s*(QATTA_[A-Z0-9_]+)\s*=", source, re.MULTILINE))


def test_env_example_exists() -> None:
    assert ENV_EXAMPLE.is_file(), ".env.example is missing"


def test_every_code_variable_is_documented() -> None:
    code = _backend_env_names() | _core_env_names()
    documented = _documented_env_names()

    missing = sorted(code - documented)
    assert not missing, (
        "These environment variables are read by the code but are missing from "
        f".env.example: {', '.join(missing)}"
    )


def test_env_example_documents_nothing_that_does_not_exist() -> None:
    code = _backend_env_names() | _core_env_names()
    documented = _documented_env_names()

    extra = sorted(documented - code - ALLOWED_EXTRA)
    assert not extra, (
        "These variables are documented in .env.example but no settings class "
        f"reads them: {', '.join(extra)}"
    )


def test_secrets_are_commented_out() -> None:
    """A secret must never be active in the example file."""
    secret_name = re.compile(r"_(API_KEY|KEY|TOKEN|SECRET|PASSWORD)$")
    source = ENV_EXAMPLE.read_text(encoding="utf-8")
    for line in source.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        name = stripped.split("=", 1)[0]
        if secret_name.search(name):
            # The keys may be listed, but never with a value.
            assert stripped.split("=", 1)[1] == "", (
                f"{name} looks like a secret and must stay commented out in .env.example"
            )


@pytest.mark.parametrize(
    "variable",
    [
        "QATTA_ALLOW_CLOUD_APIS",
        "QATTA_LLM_HOSTED_OPT_IN",
        "QATTA_LLM_RANKER_ENABLED",
        "QATTA_ENABLE_URL_INGESTION",
    ],
)
def test_cloud_gates_are_documented_and_off_by_default(variable: str) -> None:
    """Every cloud gate must be visible in the example file."""
    source = ENV_EXAMPLE.read_text(encoding="utf-8")
    assert variable in source, f"{variable} is not documented"

    # The shipped code default must be fail-closed for the cloud switches.
    cloud_gates = {
        "QATTA_ALLOW_CLOUD_APIS",
        "QATTA_LLM_HOSTED_OPT_IN",
        "QATTA_LLM_RANKER_ENABLED",
    }
    if variable in cloud_gates:
        backend_source = BACKEND_CONFIG.read_text(encoding="utf-8")
        field = variable.removeprefix("QATTA_")
        match = re.search(rf"^    {field}:\s*bool\s*=\s*(\w+)", backend_source, re.MULTILINE)
        assert match, f"{variable} is not a boolean setting"
        assert match.group(1) == "False", (
            f"{variable} must default to False — the cloud path is opt-in"
        )
