"""Hyperparameters from config files, flattened to ``a.b.c: scalar``."""

import json
from typing import Any

import yaml

from pulse.constants import HPARAM_MAX_DEPTH, HPARAM_MAX_KEYS, HPARAM_MAX_VALUE_LENGTH

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


def flatten(tree: dict[str, Any], prefix: str = "", depth: int = 0) -> dict[str, Scalar]:
    """Nested keys joined with dots. Deeper than HPARAM_MAX_DEPTH is ignored, which
    also stops YAML that refers to itself (``a: &a {b: *a}``) from recursing forever."""
    out: dict[str, Scalar] = {}
    for key, value in tree.items():
        name = f"{prefix}{key}"
        if isinstance(value, dict):
            if depth < HPARAM_MAX_DEPTH:
                out.update(flatten(value, f"{name}.", depth + 1))
        elif isinstance(value, list):
            if all(isinstance(v, str | int | float | bool) for v in value) and len(value) <= 16:
                out[name] = json.dumps(value)[:HPARAM_MAX_VALUE_LENGTH]
        elif isinstance(value, str):
            out[name] = value[:HPARAM_MAX_VALUE_LENGTH]
        elif value is None or isinstance(value, int | float | bool):
            out[name] = value
        if len(out) >= HPARAM_MAX_KEYS:
            break
    return out


def _unwrap_wandb(tree: dict[str, Any]) -> dict[str, Any]:
    """W&B config.yaml stores ``key: {desc: ..., value: x}``; keep just the values."""
    entries = {k: v for k, v in tree.items() if not k.startswith("_")}
    if entries and all(isinstance(v, dict) and "value" in v for v in entries.values()):
        return {k: v["value"] for k, v in entries.items()}
    return tree
