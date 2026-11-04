"""Which files in a job's working directory carry metrics or hyperparameters.

The agent (pulse/agent/pulse_agent.py) has its own copy of these rules, since
it must stay standalone; a test keeps the two in agreement.
"""

import posixpath
from typing import Literal

MetricFileKind = Literal["tfevents", "jsonl", "csv", "config"]

CHUNK_BYTES = 256 * 1024  # max new bytes read per file per poll
CONFIG_MAX_BYTES = 64 * 1024
MAX_METRIC_FILES = 8  # newest first, per job
MAX_CONFIG_FILES = 4
SEARCH_DEPTH = 4
PRUNE_DIRS = (".git", "node_modules", "__pycache__", ".venv", "venv", ".cache")
CONFIG_NAMES = (
    "hparams.yaml",
    "hparams.json",
    "config.yaml",
    "config.yml",
    "config.json",
    "params.json",
    "args.json",
)


def classify(path: str) -> MetricFileKind | None:
    name = posixpath.basename(path).lower()
    if name.startswith("events.out.tfevents."):
        return "tfevents"
    if name.endswith(".jsonl") and "metric" in name:
        return "jsonl"
    if name.endswith(".csv") and ("metric" in name or name == "progress.csv"):
        return "csv"
    if name in CONFIG_NAMES:
        return "config"
    return None
