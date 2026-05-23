"""Source models for GitHub REST + GraphQL responses.

All models use extra="allow" — we pin only the fields that drive sink-side
keying and a few obviously stable fields. The rest survive in the source jsonb.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class GithubRepo(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: int = Field(..., description="GitHub repo id; PK")
    name: str
    full_name: str
    owner: dict[str, object]
    description: str | None = None
    pushed_at: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    default_branch: str | None = None
    stargazers_count: int | None = None
    forks_count: int | None = None
    subscribers_count: int | None = None
    open_issues_count: int | None = None
    topics: list[str] = Field(default_factory=list)
    license: dict[str, object] | None = None


class GithubStar(BaseModel):
    model_config = ConfigDict(extra="allow")

    starred_at: str
    user: dict[str, object]


class GithubFork(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: int
    created_at: str | None = None
    full_name: str | None = None


class GithubCommit(BaseModel):
    model_config = ConfigDict(extra="allow")

    sha: str
    commit: dict[str, object]
    author: dict[str, object] | None = None


class GithubIssue(BaseModel):
    model_config = ConfigDict(extra="allow")

    number: int
    state: str | None = None
    state_reason: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    closed_at: str | None = None
    pull_request: dict[str, object] | None = None
    labels: list[object] = Field(default_factory=list)


class GithubContributor(BaseModel):
    model_config = ConfigDict(extra="allow")

    login: str | None = None
    id: int | None = None
    contributions: int = 0


class GithubRelease(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: int
    tag_name: str
    name: str | None = None
    published_at: str | None = None
    draft: bool = False
    prerelease: bool = False
