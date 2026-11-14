import asyncio
import json
import os
import shlex
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from httpx import AsyncClient

from pulse.api.claude import stream
from pulse.assistants import claude_history
from pulse.assistants.claude_history import sessions
from pulse.models import LoginSession, utcnow
from pulse.services.claude import provider_url
from pulse.services.claude_chat import Transcript, chat_command, tool_summary
from pulse.services.container import Services
from tests.conftest import ADMIN
from tests.test_assistants import linked
from tests.test_live import stream_request

pytest_plugins = ["tests.test_assistants"]

SESSION = "11111111-1111-4111-8111-111111111111"


async def wait_phase(client: AsyncClient, base: str, phase: str) -> dict[str, Any]:
    for _ in range(100):
        state = (await client.get(base + "/state")).json()
        if state["phase"] == phase:
            return state  # type: ignore[no-any-return]
        await asyncio.sleep(0.01)
    raise AssertionError(f"Claude never reached {phase}: {state}")


async def test_native_signin(
    client: AsyncClient, services: Services, cluster: dict[str, Any]
) -> None:
    account = await linked(client, cluster["port"])
    base = f"/api/assistants/{account}/claude"
    assert (await client.get(base + "/state")).json()["phase"] == "disconnected"
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
    audit = (await client.get("/api/assistants/audit")).json()
    assert "ONE-TIME#STATE" not in json.dumps(audit)
    assert (await client.post(base + "/stop")).status_code == 204
    assert (1, account) not in services.assistants.sign_ins


async def test_claude_chat_history_prompt_and_approval(
    client: AsyncClient, services: Services, cluster: dict[str, Any]
) -> None:
    account = await linked(client, cluster["port"])
    base = f"/api/assistants/{account}"
    claude = "?provider=claude"
    connected = await client.post(base + "/connect" + claude)
    assert connected.status_code == 200, connected.text
    assert connected.json()["signed_in"] is True
    # Codex is a separate connection on the same cluster.
    assert (await client.get(base + "/state")).json()["connection"]["connected"] is False
    threads = (await client.get(base + "/threads" + claude)).json()["data"]
    assert threads[0]["id"] == SESSION
    history = (await client.get(base + f"/threads/{SESSION}" + claude)).json()
    assert [m["text"] for m in history["messages"]] == ["Prepare the training script", "Prepared."]
    assert cluster["native_commands"] == []  # reading history never starts Claude

    assert (await client.post(base + f"/threads/{SESSION}/resume" + claude)).status_code == 200
    command = cluster["native_commands"][-1]
    assert "cd -- /scratch/project && exec claude -p" in command
    assert f"--resume {SESSION}" in command
    assert "--permission-prompt-tool stdio --permission-mode default" in command
    assert "dangerously" not in command and "bypassPermissions" not in command
    turn = await client.post(
        base + f"/threads/{SESSION}/turn" + claude, json={"prompt": "train on 4 GPUs"}
    )
    assert turn.status_code == 204, turn.text
    conn = services.assistants.get("claude", 1, account)
    assert conn is not None
    for _ in range(100):
        if conn.approvals:
            break
        await asyncio.sleep(0.01)
    approval = next(iter(conn.approvals.values())).item
    assert approval.kind == "command" and approval.detail == "# Submit training\nsbatch train.sh"
    assert cluster["claude_decisions"] == []  # nothing runs until the user decides
    accepted = await client.post(
        base + f"/approvals/{approval.id}" + claude, json={"decision": "accept"}
    )
    assert accepted.status_code == 204, accepted.text
    await asyncio.wait_for(cluster["claude_done"].wait(), 2)
    await asyncio.sleep(0.05)
    decision = cluster["claude_decisions"][-1]
    assert decision["request_id"] == "perm-1"
    assert decision["response"] == {
        "behavior": "allow",
        "updatedInput": {"command": "sbatch train.sh", "description": "Submit training"},
    }
    live = (await client.get(base + "/state" + claude)).json()
    assert live["active"] == {} and live["approvals"] == [] and live["error"] is None
    messages = live["messages"][SESSION]
    prompt = cluster["claude_prompts"][-1]
    # The prompt keeps Pulse's id in Claude's transcript, so history won't duplicate it.
    assert messages[0] == {
        "id": prompt["uuid"],
        "role": "user",
        "kind": "userMessage",
        "text": "train on 4 GPUs",
        "status": None,
    }
    assert [(m["id"], m["text"]) for m in messages[1:2]] == [("msg_1:0", "Submitting the job.")]
    tool = next(m for m in messages if m["id"] == "toolu_1")
    assert tool["status"] == "completed" and "Submitted batch job 4242" in tool["text"]
    assert messages[-1]["text"] == "Job 4242 is queued."
    assert "hidden" not in json.dumps(live)  # thinking is never shown
    audit = json.dumps((await client.get("/api/assistants/audit")).json())
    assert "approval_accepted" in audit and "train on 4 GPUs" not in audit
    assert (await client.post(base + "/disconnect" + claude)).status_code == 204
    assert services.assistants.get("claude", 1, account) is None


async def test_claude_models_and_thinking_level_restart_the_same_conversation(
    client: AsyncClient, services: Services, cluster: dict[str, Any]
) -> None:
    account = await linked(client, cluster["port"])
    base = f"/api/assistants/{account}"
    claude = "?provider=claude"
    assert (await client.post(base + "/connect" + claude)).status_code == 200
    models = (await client.get(base + "/models" + claude)).json()
    assert [(m["id"], m["efforts"], m["is_default"]) for m in models] == [
        ("default", ["low", "medium", "high"], True),
        ("sonnet", ["low", "high"], False),
        ("haiku", [], False),
    ]
    probe = cluster["native_commands"][-1]
    assert "--session-id" not in probe and "--resume" not in probe  # starts nothing
    resumed = await client.post(base + f"/threads/{SESSION}/resume" + claude)
    assert resumed.status_code == 200, resumed.text
    assert "--model" not in cluster["native_commands"][-1]
    refused = await client.post(
        base + f"/threads/{SESSION}/turn" + claude,
        json={"prompt": "go", "model": "haiku", "effort": "low"},
    )
    assert refused.status_code == 400  # Haiku has no thinking levels here
    sent = await client.post(
        base + f"/threads/{SESSION}/turn" + claude,
        json={"prompt": "go", "model": "sonnet", "effort": "low"},
    )
    assert sent.status_code == 204, sent.text
    command = cluster["native_commands"][-1]
    assert f"--resume {SESSION}" in command and "--model sonnet --effort low" in command
    assert cluster["claude_prompts"][-1]["message"]["content"] == "go"
    # Back to the defaults: the next prompt restarts the CLI without the flags.
    conn = services.assistants.get("claude", 1, account)
    assert conn is not None
    for _ in range(100):
        if conn.approvals:
            break
        await asyncio.sleep(0.01)
    approval = next(iter(conn.approvals))
    await client.post(base + f"/approvals/{approval}" + claude, json={"decision": "decline"})
    await asyncio.wait_for(cluster["claude_done"].wait(), 2)
    await asyncio.sleep(0.05)
    again = await client.post(
        base + f"/threads/{SESSION}/turn" + claude, json={"prompt": "again", "model": "default"}
    )
    assert again.status_code == 204, again.text
    command = cluster["native_commands"][-1]
    assert f"--resume {SESSION}" in command and "--model" not in command
    assert "--effort" not in command


async def test_claude_owner_only_and_requires_confirmation(
    client: AsyncClient, anon: AsyncClient, services: Services, cluster: dict[str, Any]
) -> None:
    account = await linked(client, cluster["port"])
    base = f"/api/assistants/{account}/claude"
    services.settings.allow_signup = True
    await anon.post(
        "/api/auth/signup", json={"username": "claude-bob", "password": "a long password"}
    )
    chat = f"/api/assistants/{account}"
    assert (await anon.get(base + "/state")).status_code == 404
    assert (await anon.post(base + "/login")).status_code == 404
    assert (await anon.post(base + "/stop")).status_code == 404
    assert (await anon.post(chat + "/connect?provider=claude")).status_code == 404
    assert (await anon.get(chat + "/threads?provider=claude")).status_code == 404
    assert (await client.post(chat + "/connect?provider=claude")).status_code == 200
    assert (
        await client.post(chat + "/threads?provider=claude", json={"work_dir": "/scratch/project"})
    ).status_code == 422
    assert (
        await client.post(
            chat + "/threads?provider=claude", json={"work_dir": "relative", "confirmed": True}
        )
    ).status_code == 422
    assert (await client.get(chat + "/threads/not-a-session?provider=claude")).status_code == 400
    assert (await client.get(chat + "/state?provider=other")).status_code == 422
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


def test_chat_command_quotes_paths_and_sign_in_links_are_allowlisted() -> None:
    path = "/scratch/a 'quote' $(touch /tmp/do-not-run)"
    command = chat_command(path, SESSION, resume=False)
    assert shlex.split(command)[2] == path
    assert shlex.split(command)[shlex.split(command).index("--session-id") + 1] == SESSION
    assert provider_url("https://claude.ai/oauth/authorize?code=x")
    for url in [
        "https://claude.ai.evil.example/oauth",
        "https://user:password@claude.ai/oauth",
        "https://claude.ai:evil/oauth",
        "javascript:alert(1)",
        "http://claude.ai/oauth",
    ]:
        assert provider_url(url) is None


def test_transcript_items_match_between_live_and_saved_history() -> None:
    records: list[dict[str, Any]] = [
        {"type": "user", "uuid": "u-1", "prompt": "Fix the loader"},
        {"type": "assistant", "id": "m", "blocks": [{"type": "text", "text": "First."}]},
        {
            "type": "assistant",
            "id": "m",
            "blocks": [
                {
                    "type": "tool_use",
                    "id": "t",
                    "name": "Edit",
                    "input": {"file_path": "/p/a.py", "old_string": "x = 1", "new_string": "x = 2"},
                }
            ],
        },
        {"type": "user", "results": [{"tool_use_id": "t", "text": "", "is_error": True}]},
        {"type": "assistant", "id": "m", "blocks": [{"type": "text", "text": "Second."}]},
    ]
    transcript = Transcript()
    found: dict[str, Any] = {}
    for record in records:
        for item in transcript.items(record, found.get):
            found[item.id] = item
    assert list(found) == ["u-1", "m:0", "t", "m:1"]
    assert found["t"].kind == "fileChange" and found["t"].status == "failed"
    assert found["t"].text == "/p/a.py\n- x = 1\n+ x = 2"
    # Streaming numbers a message's text blocks the same way.
    live = Transcript()
    assert [live.streamed_id("m"), live.streamed_id("m")] == ["m:0", "m:1"]
    assert tool_summary("Read", {"file_path": "/p/a.py"})[0] == "toolCall"


async def test_claude_state_setup_and_stream_are_bound_to_the_opening_login(
    client: AsyncClient, anon: AsyncClient, services: Services, cluster: dict[str, Any]
) -> None:
    assert (await anon.post("/api/auth/login", json=ADMIN)).status_code == 200
    other_id = next(
        row["id"] for row in (await anon.get("/api/auth/sessions")).json() if row["current"]
    )
    async with services.sessions() as db:
        login = await db.get(LoginSession, other_id)
        assert login is not None
        login.created_at = utcnow() - timedelta(days=1)
        await db.commit()
    account = await linked(client, cluster["port"])
    base = f"/api/assistants/{account}/claude"
    assert (await client.post(base + "/login")).status_code == 200
    native = services.assistants.sign_ins[(1, account)]
    for _ in range(100):
        if native.state.login_url:
            break
        await asyncio.sleep(0.01)
    assert native.state.login_url

    for confirmed in (False, True):
        if confirmed:
            assert (
                await anon.post("/api/auth/reauth", json={"password": ADMIN["password"]})
            ).status_code == 204
        state = (await anon.get(base + "/state")).json()
        assert state["phase"] == "disconnected" and state["login_url"] is None
        assert state["setup_text"] == ""
        assert (await anon.get(base + "/stream")).status_code == 403
        assert (await anon.post(base + "/stop")).status_code == 403
        assert (
            await anon.post(base + "/setup", json={"action": "code", "code": "ATTACKER"})
        ).status_code == 403
        assert cluster["claude_inputs"] == []

    login_id = next(
        row["id"] for row in (await client.get("/api/auth/sessions")).json() if row["current"]
    )
    response = await stream(account, await stream_request(services, login_id), 1, services)
    iterator = response.body_iterator
    try:
        assert "https://claude.ai/oauth/authorize" in await anext(iterator)
        assert (await client.post("/api/auth/logout")).status_code == 204
        native.changed()
        with pytest.raises(StopAsyncIteration):
            await asyncio.wait_for(anext(iterator), 1)
    finally:
        await iterator.aclose()


def test_history_titles_skip_injected_context(tmp_path: Path) -> None:
    project = tmp_path / "projects" / "-scratch-project"
    project.mkdir(parents=True)

    def write(name: str, records: list[dict[str, object]]) -> None:
        (project / f"{name}{SESSION[1:]}.jsonl").write_text(
            "\n".join(json.dumps({"cwd": "/scratch/project", **item}) for item in records)
        )

    def user(content: object, **extra: object) -> dict[str, object]:
        return {"type": "user", "message": {"content": content}, **extra}

    write(
        "1",
        [
            user("<command-name>/mcp</command-name>\n<command-message>mcp</command-message>"),
            user("<system-reminder>context</system-reminder>", isMeta=True),
            user([{"type": "tool_result", "content": "ok"}]),
            user(
                [
                    {
                        "type": "text",
                        "text": "<ide_opened_file>The user opened a.py</ide_opened_file>",
                    },
                    {"type": "text", "text": "Fix   the\nloader"},
                ]
            ),
        ],
    )
    write(
        "2",
        [
            user("Long prompt"),
            {"type": "ai-title", "aiTitle": "Old"},
            {"type": "ai-title", "aiTitle": "Loader fix"},
        ],
    )
    write("3", [user("Earlier half"), {"type": "continued-in", "continuedInSessionId": SESSION}])
    titles = {item["id"][0]: item["title"] for item in sessions(str(tmp_path))}
    assert titles == {"1": "Fix the loader", "2": "Loader fix"}


def test_history_lists_the_newest_conversations_beyond_the_scan_limits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(claude_history, "MAX_PROJECTS", 1)
    monkeypatch.setattr(claude_history, "MAX_FILES", 1)
    for age, name in enumerate(["new", "old", "older"]):
        project = tmp_path / "projects" / f"-scratch-{name}"
        project.mkdir(parents=True)
        for minutes in (0, 1):
            transcript = project / f"{age}{minutes}{SESSION[2:]}.jsonl"
            transcript.write_text(json.dumps({"type": "user", "cwd": f"/scratch/{name}"}))
            stamp = 1_000_000 - age * 1000 - minutes * 60
            os.utime(transcript, (stamp, stamp))
        os.utime(project, (1_000_000 - age * 1000,) * 2)
    result = sessions(str(tmp_path))
    assert [item["id"] for item in result] == ["00" + SESSION[2:]]


def test_history_reads_one_conversation_without_thinking_or_subagents(tmp_path: Path) -> None:
    project = tmp_path / "projects" / "-scratch-project"
    project.mkdir(parents=True)
    records = [
        {"type": "user", "uuid": "u-1", "cwd": "/scratch/project", "message": {"content": "Go"}},
        {
            "type": "assistant",
            "message": {
                "id": "m",
                "content": [
                    {"type": "thinking", "thinking": "secret plan"},
                    {"type": "tool_use", "id": "t", "name": "Bash", "input": {"command": "ls"}},
                ],
            },
        },
        {"type": "assistant", "isSidechain": True, "message": {"id": "s", "content": "sub"}},
        {"type": "ai-title", "aiTitle": "Listing files"},
    ]
    (project / f"{SESSION}.jsonl").write_text("\n".join(json.dumps(r) for r in records))
    result = claude_history.conversation(str(tmp_path), SESSION)
    assert result["thread"]["title"] == "Listing files"
    assert result["records"] == [
        {"type": "user", "uuid": "u-1", "prompt": "Go"},
        {
            "type": "assistant",
            "id": "m",
            "blocks": [{"type": "tool_use", "id": "t", "name": "Bash", "input": {"command": "ls"}}],
        },
    ]
    assert claude_history.conversation(str(tmp_path), "../../etc/passwd")["thread"] is None
