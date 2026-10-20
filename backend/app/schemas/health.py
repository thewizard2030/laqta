"""Health check schema."""

from datetime import UTC, datetime

from pydantic import BaseModel, Field

from qatta import __version__


class HealthResponse(BaseModel):
    """Health status response."""

    status: str = Field(default="healthy", description="Application health status")
    app: str = Field(default="Laqta", description="Application name")
    version: str = Field(default=__version__, description="Application version")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Current server UTC timestamp",
    )
