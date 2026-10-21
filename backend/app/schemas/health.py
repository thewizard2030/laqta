"""Health check schema."""

from datetime import UTC, datetime

from pydantic import BaseModel, Field

from qatta import __version__


class HealthResponse(BaseModel):
    """Health status response."""

    status: str = Field(
        default="healthy",
        description=(
            "'healthy' only when the API *and* the background job worker "
            "are running; 'degraded' when the worker is stopped (jobs would "
            "never run)."
        ),
    )
    app: str = Field(default="Laqta", description="Application name")
    version: str = Field(default=__version__, description="Application version")
    worker: str = Field(
        default="unknown",
        description="Background job worker state: running | stopped",
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Current server UTC timestamp",
    )
