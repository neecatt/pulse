import math
import struct
from pathlib import Path

import numpy as np
import pytest
from tensorboardX import SummaryWriter
from tensorboardX.proto.summary_pb2 import Summary
from tensorboardX.proto.tensor_pb2 import TensorProto
from tensorboardX.proto.types_pb2 import DT_DOUBLE, DT_FLOAT

from pulse.metrics import classify
from pulse.metrics.hparams import parse_config
from pulse.metrics.logs import parse_log_metrics
from pulse.metrics.tabular import parse_csv, parse_jsonl
from pulse.metrics.tfevents import parse_tfevents


def write_events(directory: Path, *, style: str = "simple_value") -> bytes:
    """Event file in PyTorch/tensorboardX style (simple_value) or TF2 style (tensor)."""
    writer = SummaryWriter(str(directory))
    for step in range(5):
        for tag, value in (("train/loss", 1.0 / (step + 1)), ("lr", 3e-4)):
            if style == "simple_value":
                writer.add_scalar(tag, value, step)
            else:
                writer.file_writer.add_summary(_tensor_summary(tag, value, style), step)
    writer.add_histogram("weights", np.arange(10), 0)  # not a scalar: skipped
    writer.close()
    (path,) = directory.glob("events.out.tfevents.*")
    return path.read_bytes()


def _tensor_summary(tag: str, value: float, style: str) -> Summary:
    if style == "tensor_content":
        tensor = TensorProto(dtype=DT_DOUBLE, tensor_content=struct.pack("<d", value))
    else:
        tensor = TensorProto(dtype=DT_FLOAT, float_val=[value])
    return Summary(value=[Summary.Value(tag=tag, tensor=tensor)])


@pytest.mark.parametrize("style", ["simple_value", "float_val", "tensor_content"])
def test_tfevents_scalars(tmp_path: Path, style: str) -> None:
    chunk = parse_tfevents(write_events(tmp_path, style=style))

    loss = [p for p in chunk.points if p.name == "train/loss"]
    assert [p.step for p in loss] == [0, 1, 2, 3, 4]
    assert loss[-1].value == pytest.approx(0.2)
    assert loss[0].wall_time is not None
    assert {p.name for p in chunk.points} == {"train/loss", "lr"}


def test_tfevents_partial_record_waits_for_more(tmp_path: Path) -> None:
    data = write_events(tmp_path)
    whole = parse_tfevents(data)
    assert whole.consumed == len(data)

    cut = parse_tfevents(data[:-7])
    assert cut.consumed < len(data) - 7
    rest = parse_tfevents(data[cut.consumed :])
    assert len(cut.points) + len(rest.points) == len(whole.points)


def test_tfevents_garbage_is_harmless() -> None:
    assert parse_tfevents(b"\x00\x01garbage").points == []


def test_jsonl() -> None:
    data = (
        b'{"hparams": {"lr": 0.001, "model": {"layers": 12}}}\n'
        b'{"step": 10, "train/loss": 1.5, "acc": 0.5, "note": "warmup", "time": 1767268800}\n'
        b"not json\n"
        b'{"step": 20, "train/loss": 1.2, "acc": NaN}\n'
        b'{"step": 30, "train/lo'
    )
    chunk = parse_jsonl(data)

    assert chunk.hparams == {"lr": 0.001, "model.layers": 12}
    assert [(p.name, p.step) for p in chunk.points] == [
        ("train/loss", 10),
        ("acc", 10),
        ("train/loss", 20),
        ("acc", 20),  # NaN is kept: storage drops it, alerts need it
    ]
    assert math.isnan(chunk.points[-1].value)
    assert chunk.points[0].wall_time is not None
    assert chunk.consumed == data.rfind(b"\n") + 1


def test_csv_with_sparse_columns_like_lightning() -> None:
    first, header = parse_csv(b"epoch,step,train_loss,val_loss\n0,49,0.9,\n", None)
    assert header == ["epoch", "step", "train_loss", "val_loss"]
    assert [(p.name, p.step) for p in first.points] == [("epoch", 49), ("train_loss", 49)]

    second, _ = parse_csv(b"0,99,,0.7\n1,149,0.6", header)  # last line incomplete
    assert [(p.name, p.step, p.value) for p in second.points] == [
        ("epoch", 99, 0.0),
        ("val_loss", 99, 0.7),
    ]
    assert second.consumed == len(b"0,99,,0.7\n")


def test_log_metrics_need_a_step() -> None:
    points = parse_log_metrics(
        [
            "[step 1200] epoch 3/10 loss=0.41 acc: 0.87 lr=3e-4",
            "Iter 50 | train/loss: 2.5 | grad_norm=1.2e+00",
            "loss=0.9 without a step",
            "step=7 throughput 4.2k tok/s eta=00:12",
        ]
    )
    assert [(p.name, p.step, p.value) for p in points] == [
        ("loss", 1200, 0.41),
        ("acc", 1200, 0.87),
        ("lr", 1200, 3e-4),
        ("train/loss", 50, 2.5),
        ("grad_norm", 50, 1.2),
    ]


def test_parse_config_formats() -> None:
    assert parse_config(
        "hparams.yaml", b"lr: 0.001\noptim:\n  name: adamw\n  betas: [0.9, 0.95]\n"
    ) == {
        "lr": 0.001,
        "optim.name": "adamw",
        "optim.betas": "[0.9, 0.95]",
    }
    assert parse_config("config.json", b'{"batch_size": 64}') == {"batch_size": 64}
    wandb = b"_wandb:\n  value: {cli_version: 0.17}\nlr:\n  desc: null\n  value: 0.01\n"
    assert parse_config("config.yaml", wandb) == {"lr": 0.01}
    assert parse_config("config.yaml", b": : not yaml [") == {}


@pytest.mark.parametrize(
    ("path", "kind"),
    [
        ("/w/runs/exp1/events.out.tfevents.1767268800.node.123.0", "tfevents"),
        ("/w/metrics.jsonl", "jsonl"),
        ("/w/train_metrics.jsonl", "jsonl"),
        ("/w/lightning_logs/version_0/metrics.csv", "csv"),
        ("/w/progress.csv", "csv"),
        ("/w/lightning_logs/version_0/hparams.yaml", "config"),
        ("/w/wandb/run-1/files/config.yaml", "config"),
        ("/w/data.csv", None),
        ("/w/notes.jsonl", None),
    ],
)
def test_classify(path: str, kind: str | None) -> None:
    assert classify(path) == kind
