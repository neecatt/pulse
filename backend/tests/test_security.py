"""Regression tests for the security review (request limits, SSRF, isolation)."""

from collections.abc import AsyncIterator

from httpx import AsyncClient

from pulse import constants


async def test_oversized_body_is_refused_before_it_is_read(client: AsyncClient) -> None:
    huge = b"x" * (constants.MAX_REQUEST_BYTES + 1)
    response = await client.post(
        "/api/auth/login", content=huge, headers={"content-type": "application/json"}
    )
    assert response.status_code == 413


async def test_oversized_chunked_body_is_cut_off(client: AsyncClient) -> None:
    async def chunks() -> AsyncIterator[bytes]:  # no Content-Length: counted as it arrives
        for _ in range(constants.MAX_REQUEST_BYTES // 65536 + 2):
            yield b"x" * 65536

    response = await client.post(
        "/api/auth/login", content=chunks(), headers={"content-type": "application/json"}
    )
    assert response.status_code == 413


async def test_agent_reports_get_a_larger_limit(client: AsyncClient) -> None:
    body = b"x" * (constants.MAX_REQUEST_BYTES * 2)
    response = await client.post(
        constants.AGENT_REPORT_PATH, content=body, headers={"content-type": "application/json"}
    )
    assert response.status_code != 413  # read in full; rejected for other reasons

    too_big = b"x" * (constants.MAX_AGENT_REPORT_BYTES + 1)
    response = await client.post(
        constants.AGENT_REPORT_PATH, content=too_big, headers={"content-type": "application/json"}
    )
    assert response.status_code == 413


async def test_setup_info_needs_sign_in(anon: AsyncClient) -> None:
    # It carries the signed-in user's own SSH public key.
    assert (await anon.get("/api/setup")).status_code == 401
