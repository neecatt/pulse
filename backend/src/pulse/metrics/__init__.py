"""Training metrics read from the files jobs already write.

Supported without any change to training code:

- TensorBoard event files (``events.out.tfevents.*``), scalar summaries
- JSON-lines metric logs (``*metric*.jsonl``), one record per step
- CSV metric logs (``*metric*.csv``, ``progress.csv``; e.g. Lightning CSVLogger)
- ``key=value`` pairs in the job's stdout
- Hyperparameters from ``hparams.yaml``, ``config.yaml``/``.json``, W&B ``config.yaml``

Parsers are pure functions over bytes and report how much input they consumed,
so files can be read incrementally and a partial trailing record waits for the
next poll.
"""

from pulse.metrics.discovery import CHUNK_BYTES, MetricFileKind, classify
from pulse.metrics.model import ParsedChunk, Point

__all__ = ["CHUNK_BYTES", "MetricFileKind", "ParsedChunk", "Point", "classify"]
