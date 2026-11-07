import asyncio
import json
import shlex
from pathlib import Path
from typing import Any

from httpx import AsyncClient

from pulse.assistants.claude_history import sessions
from pulse.services.claude import provider_url, remote_command
from pulse.services.container import Services
from tests.test_assistants import linked

pytest_plugins = ["tests.test_assistants"]

SESSION = "11111111-1111-4111-8111-111111111111"


async def wait_phase(client: AsyncClient, base: str, phase: str) -> dict[str, Any]:
    for _ in range(100):
        state = (await client.get(base + "/state")).json()
        if state["phase"] == phase:
            return state  # type: ignore[no-any-return]
        await asyncio.sleep(0.01)
    raise AssertionError(f"Claude never reached {phase}: {state}")


async def test_native_signin_and_existing_chat_handoff(
    client: AsyncClient, services: Services, cluster: dict[str, Any]
) -> None:
    account = await linked(client, cluster["port"])
    base = f"/api/assistants/{account}/claude"
    assert (await client.get(base + "/state")).json()["phase"] == "disconnected"
    response = await client.get(base + "/threads")
    assert response.status_code == 200, response.text
    assert response.json()["data"][0]["id"] == SESSION
    assert cluster["native_commands"] == []  # listing never launches a model
    assert (await client.post(base + "/login")).status_code == 200
    for _ in range(50):
        state = (await client.get(base + "/state")).json()
        if state["login_url"]:
            break
        await asyncio.sleep(0.01)
    assert state["login_url"].startswith("https://claude.ai/oauth/authorize")
    assert cluster["claude_inputs"] == []
    assert (
        await client.post(base + "/setup", json={"action": "code", "code": "ONE-TIME#STATE"})
    ).status_code == 204
    await wait_phase(client, base, "authorized")
    assert cluster["claude_inputs"] == ["ONE-TIME#STATE\n"]
    response = await client.post(
        base + "/start",
        json={"work_dir": "/scratch/project", "session_id": SESSION, "confirmed": True},
    )
    assert response.status_code == 200, response.text
    assert "--resume " + SESSION in cluster["native_commands"][-1]
    assert "--permission-mode manual" in cluster["native_commands"][-1]
    assert "--dangerously-skip-permissions" not in cluster["native_commands"][-1]
    # No trust or Remote Control confirmation is answered automatically.
    assert cluster["claude_inputs"] == ["ONE-TIME#STATE\n"]
    assert (await client.post(base + "/setup", json={"action": "yes"})).status_code == 204
    ready = await wait_phase(client, base, "ready")
    assert ready["remote_url"] == "https://claude.ai/code/session_test"
    assert ready["setup_text"] == ""  # don't retain a second copy of native tool output
    audit = (await client.get("/api/assistants/audit")).json()
    assert "ONE-TIME#STATE" not in json.dumps(audit)
    assert any(item["action"] == "claude_remote_started" for item in audit)
    assert (await client.post(base + "/stop")).status_code == 204
    assert (1, account) not in services.assistants.claude


async def test_claude_owner_only_and_requires_confirmation(
    client: AsyncClient, anon: AsyncClient, services: Services, cluster: dict[str, Any]
) -> None:
    account = await linked(client, cluster["port"])
    base = f"/api/assistants/{account}/claude"
    services.settings.allow_signup = True
    await anon.post(
        "/api/auth/signup", json={"username": "claude-bob", "password": "a long password"}
    )
    assert (await anon.get(base + "/state")).status_code == 404
    assert (await anon.get(base + "/threads")).status_code == 404
    assert (await anon.post(base + "/login")).status_code == 404
    assert (await anon.post(base + "/stop")).status_code == 404
    assert (
        await client.post(base + "/start", json={"work_dir": "/scratch/project"})
    ).status_code == 422
    assert (
        await client.post(base + "/start", json={"work_dir": "relative", "confirmed": True})
    ).status_code == 422
    services.settings.assistants_enabled = False
    assert (await client.post(base + "/login")).status_code == 403
    assert cluster["native_commands"] == []


def test_history_metadata_never_reads_credentials_or_symlinks(tmp_path: Path) -> None:
    project = tmp_path / "projects" / "-scratch-project"
    project.mkdir(parents=True)
    (tmp_path / ".credentials.json").write_text('{"accessToken":"secret-test-token"}')
    transcript = project / (SESSION + ".jsonl")
    transcript.write_text(
        "\n".join(
            json.dumps(item)
            for item in [
                {
                    "type": "user",
                    "cwd": "/scratch/project",
                    "message": {"content": "Prepare training"},
                },
                {"type": "custom-title", "customTitle": "Learning rate sweep"},
            ]
        )
    )
    (project / "22222222-2222-4222-8222-222222222222.jsonl").symlink_to(
        tmp_path / ".credentials.json"
    )
    result = sessions(str(tmp_path))
    assert len(result) == 1 and result[0]["id"] == SESSION
    assert result[0]["title"] == "Learning rate sweep"
    assert "secret-test-token" not in json.dumps(result)


def test_remote_command_quotes_paths_and_provider_links_are_allowlisted() -> None:
    path = "/scratch/a 'quote' $(touch /tmp/do-not-run)"
    command = remote_command(path, SESSION)
    assert shlex.split(command)[2] == path
    assert provider_url("https://claude.ai/code/session_test", remote=True)
    for url in [
        "https://claude.ai.evil.example/code/x",
        "https://user:password@claude.ai/code/x",
        "https://claude.ai:evil/code/x",
        "javascript:alert(1)",
        "https://claude.ai/settings",
    ]:
        assert provider_url(url, remote=True) is None
