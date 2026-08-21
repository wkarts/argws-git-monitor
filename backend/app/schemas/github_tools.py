from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class BranchCreateRequest(BaseModel):
    branch: str = Field(min_length=1, max_length=255)
    base_branch: str | None = Field(default=None, max_length=255)
    set_default: bool = False


class BranchResult(BaseModel):
    branch: str
    created: bool
    set_default: bool


class TreeItem(BaseModel):
    path: str
    type: str
    mode: str
    sha: str
    size: int | None = None


class FileWriteRequest(BaseModel):
    branch: str = Field(min_length=1, max_length=255)
    path: str = Field(min_length=1, max_length=1000)
    content: str = Field(max_length=2_000_000)
    message: str = Field(default="chore: atualiza arquivo pelo ARGWS Git Monitor", max_length=500)
    overwrite: bool = True


class DeletePathRequest(BaseModel):
    branch: str = Field(min_length=1, max_length=255)
    path: str = Field(min_length=1, max_length=1000)
    confirmation: str = Field(min_length=1, max_length=1000)


class BootstrapRequest(BaseModel):
    branch: str = Field(default="main", min_length=1, max_length=255)
    overwrite: bool = False
    include_dockerfile: bool = False
    include_workflow: bool = True


class ReleaseCreateRequest(BaseModel):
    tag_name: str = Field(min_length=1, max_length=255)
    target_commitish: str = Field(default="main", min_length=1, max_length=255)
    name: str | None = Field(default=None, max_length=500)
    body: str | None = Field(default=None, max_length=100_000)
    prerelease: bool = False


class WorkflowDispatchRequest(BaseModel):
    workflow: str = Field(default="docker-publish.yml", min_length=1, max_length=500)
    ref: str = Field(default="main", min_length=1, max_length=255)
    inputs: dict[str, str] = Field(default_factory=dict)


class PackageVersion(BaseModel):
    id: int
    name: str
    url: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    tags: list[str] = Field(default_factory=list)


class PackageDeleteRequest(BaseModel):
    confirmation: str = Field(min_length=1, max_length=500)


class ToolResult(BaseModel):
    message: str
    data: dict[str, Any] = Field(default_factory=dict)
