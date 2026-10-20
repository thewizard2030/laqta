"""Project request and response schemas."""

from pydantic import BaseModel, Field, field_validator

from app.schemas.media import MediaAssetResponse


class ProjectCreate(BaseModel):
    """Payload to create a new project."""

    name: str = Field(..., min_length=1, max_length=255, description="Project name")

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("Project name must not be empty or whitespace only.")
        return stripped


class ProjectUpdate(BaseModel):
    """Payload to update an existing project."""

    name: str = Field(..., min_length=1, max_length=255, description="Updated project name")

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("Project name must not be empty or whitespace only.")
        return stripped


class ProjectResponse(BaseModel):
    """Project representation response."""

    id: str = Field(..., description="Unique project ID")
    name: str = Field(..., description="Project name")
    created_at: str = Field(..., description="ISO 8601 creation timestamp")
    updated_at: str = Field(..., description="ISO 8601 last update timestamp")
    media_count: int = Field(default=0, description="Total media assets in project")
    media_assets: list[MediaAssetResponse] = Field(
        default_factory=list,
        description="Associated media assets",
    )
