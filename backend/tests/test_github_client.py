from __future__ import annotations

import httpx
import pytest

from app.services.github_client import GitHubAPIError, GitHubClient


@pytest.mark.asyncio
async def test_paginate_collects_multiple_pages_and_captures_rate_limit():
    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params.get("page", "1"))
        if page == 1:
            return httpx.Response(
                200,
                json=[{"id": 1}, {"id": 2}],
                headers={
                    "link": '<https://api.github.com/user/repos?page=2>; rel="next"',
                    "x-ratelimit-remaining": "4998",
                    "x-ratelimit-reset": "1893456000",
                },
            )
        return httpx.Response(
            200,
            json=[{"id": 3}],
            headers={"x-ratelimit-remaining": "4997"},
        )

    client = GitHubClient("github_pat_test")
    await client._client.aclose()
    client._client = httpx.AsyncClient(
        base_url="https://api.github.com",
        transport=httpx.MockTransport(handler),
    )
    try:
        items = await client.paginate("/user/repos", limit=3)
    finally:
        await client.close()

    assert [item["id"] for item in items] == [1, 2, 3]
    assert client.rate_limit_remaining == 4997
    assert client.rate_limit_reset_at is not None


@pytest.mark.asyncio
async def test_github_error_is_normalized():
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"message": "Bad credentials"})

    client = GitHubClient("invalid")
    await client._client.aclose()
    client._client = httpx.AsyncClient(
        base_url="https://api.github.com",
        transport=httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(GitHubAPIError, match="Bad credentials") as caught:
            await client.get_authenticated_user()
    finally:
        await client.close()

    assert caught.value.status_code == 401
