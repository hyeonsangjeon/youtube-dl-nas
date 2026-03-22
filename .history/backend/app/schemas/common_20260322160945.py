"""Common Pydantic schemas shared across the application."""

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Response schema for the /api/health endpoint."""

    status: str
    version: str
