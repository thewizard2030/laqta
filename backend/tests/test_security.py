"""Security and isolation tests for Laqta backend."""

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, settings


def test_default_host_binding() -> None:
    """Security rule: bind to 127.0.0.1 by default."""
    assert settings.HOST == "127.0.0.1"


def test_wildcard_cors_rejected() -> None:
    """Security rule: wildcard CORS origins must be rejected."""
    with pytest.raises(ValueError, match="Wildcard"):
        Settings(CORS_ORIGINS=["*"])

    with pytest.raises(ValueError, match="Wildcard"):
        Settings(CORS_ORIGINS="http://localhost:5173, *")


def test_cors_disallows_untrusted_origins(client: TestClient) -> None:
    """Ensure untrusted origins do not receive permissive CORS headers."""
    response = client.get(
        "/api/health",
        headers={"Origin": "https://malicious-external-site.com"},
    )
    # When an untrusted origin requests with CORS, Access-Control-Allow-Origin
    # should NOT be the malicious origin or '*'
    allow_origin = response.headers.get("access-control-allow-origin")
    assert allow_origin != "*"
    assert allow_origin != "https://malicious-external-site.com"


def test_cors_allows_configured_local_origin(client: TestClient) -> None:
    """Ensure configured local frontend origin is allowed."""
    response = client.get(
        "/api/health",
        headers={"Origin": "http://127.0.0.1:5173"},
    )
    assert response.headers.get("access-control-allow-origin") == "http://127.0.0.1:5173"
