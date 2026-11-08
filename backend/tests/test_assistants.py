"""Real SSH transport against a scripted Codex app-server (no provider calls)."""

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import timedelta
from typing import Any

import asyncssh
import pytest
from httpx import AsyncClient
from sqlalchemy import select

from pulse.models import LoginSession, utcnow
from pulse.services.assistants import CodexConnection
from pulse.services.container import Services
from pulse.slurm.ssh import SshSlurmClient
from tests.conftest import ADMIN
from tests.softauthn import SoftAuthenticator
from tests.test_live import stream_request
from tests.test_passkeys import register

THREAD = {
    "id": "old-chat",
    "name": "Existing training chat",
    "cwd": "/scratch/project",
    "updatedAt": 42,
}


@pytest.fixture
async def cluster(services: Services) -> AsyncIterator[dict[str, Any]]:
    ssh = SshSlurmClient(services.settings)
    services.assistants.ssh = ssh
    services.settings.assistants_enabled = True
    state: dict[str, Any] = {
        "calls": [],
        "signed_in": False,
        "decisions": [],
        "completed": asyncio.Event(),
        "claude_inputs": [],
        "native_commands": [],
    }

    async def handler(process: asyncssh.SSHServerProcess[str]) -> None:
        command = process.command or ""
        if "command -v codex" in command or "command -v claude" in command:
            process.exit(0)
            return
        if "claude auth status" in command:
            process.stdout.write(
                json.dumps(
                    {
                        "loggedIn": True,
                        "authMethod": "claude.ai",
                        "configDirectory": "/home/alice/.claude",
                    }
                )
            )
            process.exit(0)
            return
        if "python3 -c" in command and "read_metadata" in command:
            process.stdout.write(
                json.dumps(
                    {
                        "data": [
                            {
                                "id": "11111111-1111-4111-8111-111111111111",
                                "title": "Claude training chat",
                                "work_dir": "/scratch/project",
                                "updated_at": 42,
                            }
                        ],
                        "next_cursor": None,
                    }
                )
            )
            process.exit(0)
            return
        if "exec claude auth login" in command:
            state["native_commands"].append(command)
            process.stdout.write(
                "https://claude.ai/oauth/authorize?code_challenge=test\n"
                "Paste code here if prompted:\n"
            )
            state["claude_inputs"].append(await process.stdin.readline())
            process.stdout.write("Login successful\n")
            process.exit(0)
            return
        if "claude --remote-control" in command:
            state["native_commands"].append(command)
            process.stdout.write("Trust this project and enable Remote Control? [y/N]\n")
            state["claude_inputs"].append(await process.stdin.read(1))
            process.stdout.write("Open: https://claude.ai/code/session_test\n")
            await process.stdin.read()
            process.exit(0)
            return
        assert "exec codex app-server --listen stdio://" in (process.command or "")

        def emit(value: dict[str, Any]) -> None:
            process.stdout.write(json.dumps(value) + "\n")

        async for line in process.stdin:
            value = json.loads(line)
            if "result" in value or "error" in value:
                state["decisions"].append(value)
                emit(
                    {
                        "method": "item/completed",
                        "params": {
                            "threadId": "old-chat",
                            "item": {
                                "id": "cmd",
                                "type": "commandExecution",
                                "command": "sbatch train.sh",
                                "aggregatedOutput": "Submitted batch job 4242",
                                "status": "completed",
                            },
                        },
                    }
                )
                emit(
                    {
                        "method": "item/agentMessage/delta",
                        "params": {
                            "threadId": "old-chat",
                            "itemId": "answer",
                            "delta": "Submitted job 4242",
                        },
                    }
                )
                emit(
                    {
                        "method": "turn/completed",
                        "params": {
                            "threadId": "old-chat",
                            "turn": {"id": "turn-1", "status": "completed"},
                        },
                    }
                )
                state["completed"].set()
                continue
            method, params = value["method"], value.get("params", {})
            state["calls"].append((method, params))
            result: dict[str, Any] = {}
            if method == "initialized":
                continue
            if method == "account/read":
                result = {
                    "account": {"type": "chatgpt", "email": "researcher@example.test"}
                    if state["signed_in"]
                    else None
                }
            elif method == "account/login/start":
                result = {
                    "type": "chatgptDeviceCode",
                    "verificationUrl": "https://auth.openai.com/codex/device",
                    "userCode": "ABCD-1234",
                    "loginId": "login-1",
                }
            elif method == "thread/list":
                result = {"data": [THREAD], "nextCursor": None}
            elif method == "thread/read":
                result = {
                    "thread": THREAD
                    | {
                        "turns": [
                            {
                                "items": [
                                    {
                                        "id": "earlier",
                                        "type": "agentMessage",
                                        "text": "We prepared the training script.",
                                    }
                                ]
                            }
                        ]
                    }
                }
            elif method in {"thread/start", "thread/resume"}:
                result = {"thread": THREAD}
            elif method == "turn/start":
                result = {"turn": {"id": "turn-1", "status": "inProgress"}}
            emit({"id": value["id"], "result": result})
            if method == "turn/start":
                emit(
                    {
                        "method": "turn/started",
                        "params": {"threadId": "old-chat", "turn": {"id": "turn-1"}},
                    }
                )
                emit(
                    {
                        "method": "item/started",
                        "params": {
                            "threadId": "old-chat",
                            "item": {
                                "id": "cmd",
                                "type": "commandExecution",
                                "command": "sbatch train.sh",
                                "status": "inProgress",
                            },
                        },
                    }
                )
                emit(
                    {
                        "id": "approval-1",
                        "method": "item/commandExecution/requestApproval",
                        "params": {
                            "threadId": "old-chat",
                            "itemId": "cmd",
                            "command": "sbatch train.sh",
                        },
                    }
                )

    server = await asyncssh.listen(
        "127.0.0.1",
        0,
        server_host_keys=[asyncssh.generate_private_key("ssh-ed25519")],
        authorized_client_keys=asyncssh.import_authorized_keys(ssh.public_key_for(1)),
        process_factory=handler,
    )
    state["port"] = server.sockets[0].getsockname()[1]
    try:
        yield state
    finally:
        await services.assistants.close()
        await ssh.close()
        server.close()
        await server.wait_closed()


async def linked(client: AsyncClient, port: int) -> int:
    response = await client.post(
        "/api/accounts", json={"username": "alice", "host": "127.0.0.1", "port": port}
    )
    assert response.status_code == 201, response.text
    return int(response.json()["id"])


async def test_sign_in_history_resume_approval_and_disconnect(
    client: AsyncClient, services: Services, cluster: dict[str, Any]
) -> None:
    account = await linked(client, cluster["port"])
    base = f"/api/assistants/{account}"
    assert (await client.post(base + "/connect")).json()["signed_in"] is False
    login = await client.post(base + "/login")
    assert login.json() == {"url": "https://auth.openai.com/codex/device", "code": "ABCD-1234"}
    conn = services.assistants.get(1, account)
    assert conn is not None
    await conn._message({"method": "account/login/completed", "params": {"success": True}})
    assert (await client.get(base + "/state")).json()["connection"]["signed_in"]
    assert (await client.get(base + "/threads")).json()["data"][0]["id"] == "old-chat"
    assert (
        "prepared" in (await client.get(base + "/threads/old-chat")).json()["messages"][0]["text"]
    )
    # Viewing history never resumes a thread or launches work.
    assert not any(method == "thread/resume" for method, _ in cluster["calls"])
    assert (
        await client.post(base + "/threads/old-chat/turn", json={"prompt": "train"})
    ).status_code == 409
    assert (await client.post(base + "/threads/old-chat/resume")).status_code == 200
    resume = next(params for method, params in cluster["calls"] if method == "thread/resume")
    assert resume["approvalPolicy"] == "untrusted" and resume["sandbox"] == "workspace-write"
    assert resume["approvalsReviewer"] == "user"
    response = await client.post(
        base + "/threads/old-chat/turn", json={"prompt": "train on 4 GPUs"}
    )
    assert response.status_code == 204, response.text
    # Wait for the remote server request, without needing a browser to stay open.
    for _ in range(50):
        if conn.approvals:
            break
        await asyncio.sleep(0.01)
    approval = next(iter(conn.approvals.values())).item
    assert approval.detail == "sbatch train.sh"
    assert cluster["decisions"] == []  # no approval was fabricated
    result = await client.post(base + f"/approvals/{approval.id}", json={"decision": "accept"})
    assert result.status_code == 204, result.text
    await asyncio.wait_for(cluster["completed"].wait(), 2)
    await asyncio.sleep(0.01)
    live = (await client.get(base + "/state")).json()
    assert live["active"] == {} and live["approvals"] == []
    assert any("job 4242" in item["text"] for item in live["messages"]["old-chat"])
    assert cluster["decisions"][-1] == {"id": "approval-1", "result": {"decision": "accept"}}
    assert (
        await client.post(base + f"/approvals/{approval.id}", json={"decision": "accept"})
    ).status_code == 409
    audit = (await client.get("/api/assistants/audit")).json()
    assert any(item["action"] == "approval_accepted" for item in audit)
    assert "train on 4 GPUs" not in json.dumps(audit)
    assert (await client.post(base + "/disconnect")).status_code == 204
    assert services.assistants.get(1, account) is None
    assert not any(method == "account/logout" for method, _ in cluster["calls"])


async def test_off_by_default_and_unauthenticated(client: AsyncClient, anon: AsyncClient) -> None:
    assert (await anon.get("/api/assistants/access")).status_code == 401
    assert (await client.get("/api/assistants/access")).json()["enabled"] is False
    assert (await client.post("/api/assistants/1/connect")).status_code == 403


async def test_agent_demo_and_other_users_cannot_open_connections(
    client: AsyncClient, anon: AsyncClient, services: Services, cluster: dict[str, Any]
) -> None:
    account = await linked(client, cluster["port"])
    services.settings.allow_signup = True
    assert (
        await anon.post(
            "/api/auth/signup", json={"username": "bob", "password": "another good password"}
        )
    ).status_code == 201
    for suffix in ("connect", "login"):
        assert (await anon.post(f"/api/assistants/{account}/{suffix}")).status_code == 404
    for suffix in ("state", "threads"):
        assert (await anon.get(f"/api/assistants/{account}/{suffix}")).status_code == 404
    agent = (
        await client.post(
            "/api/accounts",
            json={"username": "alice", "host": "agent.example", "connection": "agent"},
        )
    ).json()
    assert (await client.post(f"/api/assistants/{agent['id']}/connect")).status_code == 409
    services.settings.demo = True
    await anon.post("/api/auth/logout")
    assert (await anon.post("/api/auth/demo")).status_code == 201
    assert (await anon.post(f"/api/assistants/{account}/connect")).status_code == 403
    assert services.assistants.keys() == []


async def test_reauthentication_and_absolute_paths(
    client: AsyncClient, services: Services, cluster: dict[str, Any]
) -> None:
    account = await linked(client, cluster["port"])
    async with services.sessions() as db:
        login = await db.scalar(select(LoginSession))
        assert login
        login.created_at = utcnow() - timedelta(hours=1)
        await db.commit()
    assert not (await client.get("/api/assistants/access")).json()["verified"]
    assert (await client.post(f"/api/assistants/{account}/connect")).status_code == 403
    assert (await client.post("/api/auth/reauth", json={"password": "wrong"})).status_code == 403
    assert (
        await client.post("/api/auth/reauth", json={"password": ADMIN["password"]})
    ).status_code == 204
    assert (await client.post(f"/api/assistants/{account}/connect")).status_code == 200
    for path in ("relative/path", "-delete", "/scratch/a\ncommand"):
        assert (
            await client.post(
                f"/api/assistants/{account}/threads", json={"work_dir": path, "confirmed": True}
            )
        ).status_code == 422
    safe = "/scratch/a 'quoted' $(touch /tmp/nope)"
    assert (
        await client.post(
            f"/api/assistants/{account}/threads", json={"work_dir": safe, "confirmed": True}
        )
    ).status_code == 201
    params = next(params for method, params in cluster["calls"] if method == "thread/start")
    assert params["cwd"] == safe  # JSON data, never interpolated into a shell command


async def test_passkey_reauth_single_use_and_session_bound(
    client: AsyncClient, anon: AsyncClient
) -> None:
    phone = SoftAuthenticator("http://test")
    await register(client, phone, "Phone")
    assert (await anon.post("/api/auth/login", json=ADMIN)).status_code == 200
    started = (await client.post("/api/auth/passkeys/reauth/options")).json()
    assert started["options"]["userVerification"] == "required"
    body = {"challenge_id": started["challenge_id"], "credential": phone.get(started["options"])}
    assert (await anon.post("/api/auth/passkeys/reauth/verify", json=body)).status_code == 400
    started = (await client.post("/api/auth/passkeys/reauth/options")).json()
    body = {"challenge_id": started["challenge_id"], "credential": phone.get(started["options"])}
    assert (await client.post("/api/auth/passkeys/reauth/verify", json=body)).status_code == 204
    assert (await client.post("/api/auth/passkeys/reauth/verify", json=body)).status_code == 400


async def test_unknown_requests_fail_closed_and_text_is_bounded(
    client: AsyncClient, services: Services, cluster: dict[str, Any]
) -> None:
    account = await linked(client, cluster["port"])
    assert (await client.post(f"/api/assistants/{account}/connect")).status_code == 200
    conn = services.assistants.get(1, account)
    assert isinstance(conn, CodexConnection)
    await conn._message(
        {
            "id": "unsafe",
            "method": "item/newUnknownTool/requestApproval",
            "params": {"threadId": "old-chat"},
        }
    )
    await asyncio.sleep(0.01)
    assert cluster["decisions"][-1]["error"]["code"] == -32601
    for _ in range(3):
        await conn._message(
            {
                "method": "item/agentMessage/delta",
                "params": {"threadId": "old-chat", "itemId": "long", "delta": "x" * 65536},
            }
        )
    assert len(conn.snapshot().messages["old-chat"][-1].text) == 65536


async def test_another_login_cannot_use_an_open_assistant_without_connecting(
    client: AsyncClient, anon: AsyncClient, services: Services, cluster: dict[str, Any]
) -> None:
    assert (await anon.post("/api/auth/login", json=ADMIN)).status_code == 200
    logins = (await anon.get("/api/auth/sessions")).json()
    other_id = next(login["id"] for login in logins if login["current"])
    async with services.sessions() as db:
        login = await db.get(LoginSession, other_id)
        assert login is not None
        login.created_at = utcnow() - timedelta(days=1)
        other_hash = login.token_hash
        await db.commit()

    account = await linked(client, cluster["port"])
    base = f"/api/assistants/{account}"
    assert (await client.post(base + "/connect")).status_code == 200
    assert (await client.post(base + "/threads/old-chat/resume")).status_code == 200
    assert (
        await client.post(base + "/threads/old-chat/turn", json={"prompt": "Prepare a job"})
    ).status_code == 204
    conn = services.assistants.get(1, account)
    assert conn is not None
    for _ in range(100):
        if conn.approvals:
            break
        await asyncio.sleep(0.01)
    approval = next(iter(conn.approvals))

    for confirmed in (False, True):
        # Reauth alone does not inherit another browser's assistant grant.
        if confirmed:
            assert (
                await anon.post("/api/auth/reauth", json={"password": ADMIN["password"]})
            ).status_code == 204
        state = (await anon.get(base + "/state")).json()
        assert state["connection"]["connected"] is False
        assert state["messages"] == {} and state["approvals"] == []
        for suffix in ("threads", "threads/old-chat", "stream"):
            assert (await anon.get(base + "/" + suffix)).status_code == 403
        assert (
            await anon.post(base + "/threads/old-chat/turn", json={"prompt": "Run it"})
        ).status_code == 403
        assert (await anon.post(base + "/threads/old-chat/interrupt")).status_code == 403
        assert (await anon.post(base + "/disconnect")).status_code == 403
        assert (
            await anon.post(base + "/approvals/" + approval, json={"decision": "accept"})
        ).status_code == 403
        assert cluster["decisions"] == []
        assert other_hash not in conn.authorized_logins

    # Explicitly connecting this confirmed browser grants access to the same transport.
    assert (await anon.post(base + "/connect")).status_code == 200
    assert other_hash in conn.authorized_logins
    assert (await anon.get(base + "/threads/old-chat")).status_code == 200
    assert (
        await anon.post(base + "/approvals/" + approval, json={"decision": "accept"})
    ).status_code == 204
    await asyncio.wait_for(cluster["completed"].wait(), 2)


async def test_assistant_stream_drops_queued_updates_after_logout(
    client: AsyncClient, services: Services, cluster: dict[str, Any]
) -> None:
    from pulse.api.assistants import stream

    account = await linked(client, cluster["port"])
    assert (await client.post(f"/api/assistants/{account}/connect")).status_code == 200
    login_id = (await client.get("/api/auth/sessions")).json()[0]["id"]
    response = await stream(account, await stream_request(services, login_id), 1, services)
    iterator = response.body_iterator
    try:
        assert '"connected":true' in await anext(iterator)
        assert (await client.post("/api/auth/logout")).status_code == 204
        conn = services.assistants.get(1, account)
        assert conn is not None
        conn.changed()
        with pytest.raises(StopAsyncIteration):
            await asyncio.wait_for(anext(iterator), 1)
    finally:
        await iterator.aclose()


async def test_reused_login_id_does_not_inherit_assistant_access(
    client: AsyncClient, anon: AsyncClient, services: Services, cluster: dict[str, Any]
) -> None:
    account = await linked(client, cluster["port"])
    base = f"/api/assistants/{account}"
    assert (await client.post(base + "/connect")).status_code == 200
    original_id = (await client.get("/api/auth/sessions")).json()[0]["id"]
    assert (await client.post("/api/auth/logout")).status_code == 204
    assert (await anon.post("/api/auth/login", json=ADMIN)).status_code == 200
    assert (await anon.get("/api/auth/sessions")).json()[0]["id"] == original_id
    assert (await anon.get(base + "/state")).json()["connection"]["connected"] is False
    assert (await anon.get(base + "/threads")).status_code == 403
    assert (await anon.post(base + "/disconnect")).status_code == 403
