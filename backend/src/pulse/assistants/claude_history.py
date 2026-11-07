"""Bounded, stdlib-only reader for local Claude Code conversation metadata.

Executed with python3 -c over SSH. Reads transcript JSONL, never credentials.
"""

import json
import os
import re
import sys
from typing import Any, Dict, List, Optional

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


def sessions(root: str) -> List[Dict[str, Any]]:
    projects = os.path.join(root, "projects")
    candidates = []
    try:
        with os.scandir(projects) as entries:
            dirs = []
            for index, entry in enumerate(entries):
                if index >= MAX_PROJECTS:
                    break
                if entry.is_dir(follow_symlinks=False):
                    dirs.append((entry.stat().st_mtime, entry.path))
                if len(dirs) >= MAX_PROJECTS:
                    break
        for _, directory in sorted(dirs, reverse=True):
            with os.scandir(directory) as entries:
                for index, entry in enumerate(entries):
                    if index >= MAX_FILES:
                        break
                    if UUID_FILE.fullmatch(entry.name) and entry.is_file(follow_symlinks=False):
                        candidates.append((entry.stat().st_mtime, entry.path))
                    if len(candidates) >= MAX_FILES:
                        break
            if len(candidates) >= MAX_FILES:
                break
    except OSError:
        pass
    result = []
    for _, path in sorted(candidates, reverse=True):
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
