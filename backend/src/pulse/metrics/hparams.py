"""Hyperparameters from config files, flattened to ``a.b.c: scalar``."""

import json
from typing import Any

import yaml

MAX_KEYS = 200
MAX_VALUE_LENGTH = 200

Scalar = str | int | float | bool | None


def parse_config(path: str, data: bytes) -> dict[str, Scalar]:
    text = data.decode("utf-8", "replace")
    try:
        loaded = json.loads(text) if path.lower().endswith(".json") else yaml.safe_load(text)
    except (ValueError, yaml.YAMLError):
        return {}
    if not isinstance(loaded, dict):
        return {}
    return flatten(_unwrap_wandb(loaded))


def flatten(tree: dict[str, Any], prefix: str = "") -> dict[str, Scalar]:
    out: dict[str, Scalar] = {}
    for key, value in tree.items():
        name = f"{prefix}{key}"
        if isinstance(value, dict):
            out.update(flatten(value, f"{name}."))
        elif isinstance(value, list):
            if all(isinstance(v, str | int | float | bool) for v in value) and len(value) <= 16:
                out[name] = json.dumps(value)[:MAX_VALUE_LENGTH]
        elif isinstance(value, str):
            out[name] = value[:MAX_VALUE_LENGTH]
        elif value is None or isinstance(value, int | float | bool):
            out[name] = value
        if len(out) >= MAX_KEYS:
            break
    return out


def _unwrap_wandb(tree: dict[str, Any]) -> dict[str, Any]:
    """W&B config.yaml stores ``key: {desc: ..., value: x}``; keep just the values."""
    entries = {k: v for k, v in tree.items() if not k.startswith("_")}
    if entries and all(isinstance(v, dict) and "value" in v for v in entries.values()):
        return {k: v["value"] for k, v in entries.items()}
    return tree
