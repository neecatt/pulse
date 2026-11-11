"""Bounded, stdlib-only reader for local Claude Code conversation metadata.

Executed with python3 -c over SSH. Reads transcript JSONL, never credentials.
"""

import heapq
import json
import os
import re
import sys
from typing import Any, Callable, Dict, List, Optional, Tuple

UUID_FILE = re.compile(r"^[0-9a-fA-F-]{36}\.jsonl$")
MAX_PROJECTS = 128
MAX_FILES = 512
READ_BYTES = 32768
LIMIT = 50


def text_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(str(part.get("text", "")) for part in content if isinstance(part, dict))
    return ""


def read_metadata(path: str) -> Optional[Dict[str, Any]]:
    try:
        with open(path, "rb") as handle:
            head = handle.read(READ_BYTES)
            handle.seek(0, 2)
            size = handle.tell()
            handle.seek(max(0, size - READ_BYTES))
            tail = handle.read(READ_BYTES)
        title, cwd = "", ""
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
            if kind == "custom-title" and record.get("customTitle"):
                title = str(record["customTitle"])
            elif not title and kind == "summary":
                title = str(record.get("summary", ""))
            elif not title and kind == "user":
                title = text_content(record.get("message", {}).get("content", ""))
        if not cwd.startswith("/") or any(ord(char) < 32 for char in cwd):
            return None
        return {
            "id": os.path.basename(path)[:-6],
            "title": (title or "Claude conversation")[:200],
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


if __name__ == "__main__":
    request = json.load(sys.stdin)
    root = request.get("root") or os.path.expanduser("~/.claude")
    if not isinstance(root, str) or not root.startswith("/"):
        raise SystemExit("An absolute Claude configuration directory is required.")
    print(json.dumps({"data": sessions(root), "next_cursor": None}))
