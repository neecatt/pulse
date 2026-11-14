"""Bounded, stdlib-only reader for local Claude Code conversations.

Executed with python3 -c over SSH: lists recent conversations, or with a session id
returns one conversation's recent messages, trimmed. Reads transcript JSONL, never
credentials. Pulse also uses conversation_record() for live messages.
"""

import heapq
import json
import os
import re
import sys
from typing import Any, Callable, Dict, List, Optional, Tuple

UUID_FILE = re.compile(r"^[0-9a-fA-F-]{36}\.jsonl$")
SESSION = re.compile(r"^[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}$")
MAX_PROJECTS = 128
MAX_FILES = 512
READ_BYTES = 32768
LIMIT = 50
HISTORY_BYTES = 2 * 1024 * 1024
MAX_RECORDS = 300
BLOCK_CHARS = 8000
TITLE_CHARS = 200
# Text Claude Code adds to a user turn (IDE context, reminders, slash commands),
# which isn't what the person typed.
INJECTED = re.compile(
    r"<(ide_[a-z_]+|system-reminder|command-[a-z]+|local-command-[a-z]+|"
    r"user-prompt-submit-hook|bash-[a-z]+|task-notification)>.*?</\1>",
    re.DOTALL,
)


def text_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(str(part.get("text", "")) for part in content if isinstance(part, dict))
    return ""


def prompt_text(record: Dict[str, Any]) -> str:
    """What the person typed in a user turn, or "" for tool results, injected
    context, slash commands and other turns Claude Code writes itself."""
    if record.get("isMeta") or record.get("isSidechain"):
        return ""
    message = record.get("message")
    if not isinstance(message, dict):
        return ""
    text = INJECTED.sub(" ", text_content(message.get("content", "")))
    return " ".join(text.split())


def clip(value: Any, depth: int = 0) -> Any:
    """A tool input with long strings and collections cut down to size."""
    if isinstance(value, str):
        return value[:BLOCK_CHARS]
    if depth > 4:
        return None
    if isinstance(value, dict):
        return {str(k): clip(v, depth + 1) for k, v in list(value.items())[:50]}
    if isinstance(value, list):
        return [clip(v, depth + 1) for v in value[:50]]
    return value


def conversation_record(record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """A transcript or stream message reduced to what a chat shows: what the person
    typed, Claude's text, tool calls and tool results. Thinking is left out."""
    kind = record.get("type")
    message = record.get("message")
    if kind not in ("user", "assistant") or not isinstance(message, dict):
        return None
    if record.get("isSidechain") or record.get("isMeta"):
        return None
    content = message.get("content")
    blocks = [b for b in content if isinstance(b, dict)] if isinstance(content, list) else []
    if kind == "user":
        results = [
            {
                "tool_use_id": str(b.get("tool_use_id", "")),
                "text": text_content(b.get("content"))[-BLOCK_CHARS:],
                "is_error": bool(b.get("is_error")),
            }
            for b in blocks
            if b.get("type") == "tool_result"
        ]
        if results:
            return {"type": "user", "results": results}
        prompt = prompt_text(record)
        if not prompt:
            return None
        return {"type": "user", "uuid": str(record.get("uuid", "")), "prompt": prompt[:BLOCK_CHARS]}
    kept = []  # type: List[Dict[str, Any]]
    for b in blocks:
        if b.get("type") == "text" and b.get("text"):
            kept.append({"type": "text", "text": str(b["text"])[:BLOCK_CHARS]})
        elif b.get("type") == "tool_use":
            kept.append(
                {
                    "type": "tool_use",
                    "id": str(b.get("id", "")),
                    "name": str(b.get("name", "")),
                    "input": clip(b.get("input")) if isinstance(b.get("input"), dict) else {},
                }
            )
    if not kept:
        return None
    return {"type": "assistant", "id": str(message.get("id", "")), "blocks": kept}


def read_metadata(path: str, listing: bool = True) -> Optional[Dict[str, Any]]:
    try:
        with open(path, "rb") as handle:
            head = handle.read(READ_BYTES)
            handle.seek(0, 2)
            size = handle.tell()
            handle.seek(max(0, size - READ_BYTES))
            tail = handle.read(READ_BYTES)
        # Newest wins for titles Claude Code rewrites; a rename beats its own title.
        titles = {}  # type: Dict[str, str]
        cwd = ""
        for line in (head + b"\n" + tail).splitlines():
            try:
                record = json.loads(line)
            except (ValueError, UnicodeError):
                continue
            if not isinstance(record, dict):
                continue
            if not cwd and isinstance(record.get("cwd"), str):
                cwd = record["cwd"]
            kind = record.get("type")
            if kind == "continued-in" and listing:
                return None  # resumed into a newer transcript, which is listed instead
            if kind == "custom-title" and record.get("customTitle"):
                titles["custom"] = str(record["customTitle"])
            elif kind == "ai-title" and record.get("aiTitle"):
                titles["ai"] = str(record["aiTitle"])
            elif kind == "summary" and record.get("summary"):
                titles.setdefault("summary", str(record["summary"]))
            elif kind == "user" and "prompt" not in titles:
                prompt = prompt_text(record)
                if prompt:
                    titles["prompt"] = prompt
        if not cwd.startswith("/") or any(ord(char) < 32 for char in cwd):
            return None
        title = next(
            (titles[k] for k in ("custom", "ai", "summary", "prompt") if titles.get(k)), ""
        )
        return {
            "id": os.path.basename(path)[:-6],
            "title": " ".join(title.split())[:TITLE_CHARS] or "Claude conversation",
            "work_dir": cwd,
            "updated_at": int(os.stat(path).st_mtime),
        }
    except (OSError, ValueError, TypeError, AttributeError):
        return None


def newest(directory: str, limit: int, keep: Callable[[Any], bool]) -> List[Tuple[float, str]]:
    """The ``limit`` most recently modified entries of ``directory`` that ``keep`` accepts."""
    found = []  # type: List[Tuple[float, str]]
    try:
        with os.scandir(directory) as entries:
            for entry in entries:
                try:
                    if keep(entry):
                        item = (entry.stat(follow_symlinks=False).st_mtime, entry.path)
                        if len(found) < limit:
                            heapq.heappush(found, item)
                        else:
                            heapq.heappushpop(found, item)
                except OSError:
                    continue
    except OSError:
        return []
    return sorted(found, reverse=True)


def is_transcript(entry: Any) -> bool:
    return bool(UUID_FILE.fullmatch(entry.name)) and entry.is_file(follow_symlinks=False)


def sessions(root: str) -> List[Dict[str, Any]]:
    directories = newest(
        os.path.join(root, "projects"), MAX_PROJECTS, lambda e: e.is_dir(follow_symlinks=False)
    )
    candidates = heapq.nlargest(
        MAX_FILES,
        (item for _, path in directories for item in newest(path, MAX_FILES, is_transcript)),
    )
    result = []
    for _, path in candidates:
        item = read_metadata(path)
        if item:
            result.append(item)
        if len(result) >= LIMIT:
            break
    return result


def find_transcript(root: str, session: str) -> Optional[str]:
    if not SESSION.match(session):
        return None
    try:
        with os.scandir(os.path.join(root, "projects")) as entries:
            for entry in entries:
                if not entry.is_dir(follow_symlinks=False):
                    continue
                path = os.path.join(entry.path, session + ".jsonl")
                if os.path.isfile(path) and not os.path.islink(path):
                    return path
    except OSError:
        return None
    return None


def conversation(root: str, session: str) -> Dict[str, Any]:
    path = find_transcript(root, session)
    thread = read_metadata(path, listing=False) if path else None
    if path is None or thread is None:
        return {"thread": None, "records": []}
    with open(path, "rb") as handle:
        handle.seek(0, 2)
        start = max(0, handle.tell() - HISTORY_BYTES)
        handle.seek(start)
        data = handle.read()
    lines = data.splitlines()[1 if start else 0 :]  # the first line may be cut
    records = []  # type: List[Dict[str, Any]]
    for line in lines:
        try:
            record = json.loads(line)
        except (ValueError, UnicodeError):
            continue
        reduced = conversation_record(record) if isinstance(record, dict) else None
        if reduced is not None:
            records.append(reduced)
    return {"thread": thread, "records": records[-MAX_RECORDS:]}


if __name__ == "__main__":
    request = json.load(sys.stdin)
    root = request.get("root") or os.path.expanduser("~/.claude")
    if not isinstance(root, str) or not root.startswith("/"):
        raise SystemExit("An absolute Claude configuration directory is required.")
    session = request.get("session")
    if isinstance(session, str):
        print(json.dumps(conversation(root, session)))
    else:
        print(json.dumps({"data": sessions(root), "next_cursor": None}))
