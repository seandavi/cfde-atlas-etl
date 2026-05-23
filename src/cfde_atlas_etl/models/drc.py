"""Source models for the DRC asset manifests.

extra="allow" because the manifest schemas are informal — DRC team can add
columns without us pinning them.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class DrcDccAsset(BaseModel):
    model_config = ConfigDict(extra="allow")

    link: str = Field(..., description="Asset URL or linkout template")
    dcc_id: str | None = Field(None, description="DRC-side DCC UUID")
    lastmodified: str | None = None
    current: str | None = None
    creator: str | None = None
    drcapproved: str | None = None
    dccapproved: str | None = None
    deleted: str | None = None
    created: str | None = None


class DrcFileAsset(BaseModel):
    model_config = ConfigDict(extra="allow")

    link: str = Field(..., description="Download URL")
    filetype: str | None = None
    filename: str | None = None
    size: str | None = Field(None, description="Bytes as string; coerced in the view")
    sha256checksum: str | None = None


class DrcCodeAsset(BaseModel):
    model_config = ConfigDict(extra="allow")

    link: str = Field(..., description="Code / API URL")
    type: str | None = None
    name: str | None = None
    description: str | None = None
    openAPISpec: str | None = None
    smartAPISpec: str | None = None
    smartAPIURL: str | None = None
    entityPageExample: str | None = None
