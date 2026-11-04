"""Which files in a job's working directory carry metrics or hyperparameters.

The agent (pulse/agent/pulse_agent.py) has its own copy of these rules, since
it must stay standalone; a test keeps the two in agreement.
"""

import posixpath
from typing import Literal

from pulse.constants import CONFIG_NAMES

MetricFileKind = Literal["tfevents", "jsonl", "csv", "config"]


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
