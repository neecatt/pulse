from datetime import UTC, datetime, timedelta

import pytest

from pulse.domain import EventKind, JobState
from pulse.metrics.model import Point
from pulse.metrics.summary import update_summaries
from pulse.services.events import MetricLatches, metric_alerts
from pulse.slurm.base import SlurmJob
from pulse.slurm.parsing import array_id

NOW = datetime(2026, 1, 1, 12, tzinfo=UTC)
JOB = SlurmJob(slurm_id="7", name="train", partition="gpu", state=JobState.RUNNING)


def summarise(values: list[float], start: datetime = NOW, every: timedelta = timedelta(minutes=1)):
    points = [Point("loss", v, step=i, wall_time=start + i * every) for i, v in enumerate(values)]
    return update_summaries({}, points, NOW)


def kinds(summaries, non_finite=(), latches=None, now=NOW, **kw) -> list[EventKind]:
    events = metric_alerts(
        JOB,
        "loss",
        summaries,
        non_finite,
        latches or MetricLatches(),
        now,
        diverge_percent=kw.get("diverge_percent", 50),
        plateau_minutes=kw.get("plateau_minutes", 60),
    )
    return [e.kind for e in events]


def test_summary_tracks_last_min_max_and_best_time() -> None:
    s = summarise([3.0, 2.0, 2.5, 1.0])["loss"]
    assert (s["first"], s["last"], s["min"], s["max"], s["n"]) == (3.0, 1.0, 1.0, 3.0, 4)
    assert s["best_at"] == (NOW + timedelta(minutes=3)).isoformat()
    assert s["step"] == 3


def test_summary_ignores_reread_steps_and_non_finite() -> None:
    first = summarise([3.0, 2.0])
    again = update_summaries(
        first,
        [
            Point("loss", 2.0, step=1),
            Point("loss", float("nan"), step=2),
            Point("loss", 1.5, step=3),
        ],
        NOW,
    )
    assert again["loss"]["n"] == 3
    assert again["loss"]["last"] == 1.5
    assert first["loss"]["n"] == 2  # input not mutated


def test_nan_loss_alerts_once() -> None:
    latches = MetricLatches()
    assert kinds({}, ["train/loss"], latches) == [EventKind.JOB_NAN]
    assert kinds({}, ["train/loss"], latches) == []
    assert kinds({}, ["accuracy"], MetricLatches()) == []  # only losses


def test_healthy_curve_is_quiet() -> None:
    values = [2.0 * 0.97**i for i in range(40)]
    assert kinds(summarise(values), now=NOW + timedelta(minutes=40)) == []


def test_divergence() -> None:
    values = [1.0 - 0.01 * i for i in range(30)] + [0.71 * 1.25**i for i in range(15)]
    latches = MetricLatches()
    assert EventKind.JOB_DIVERGING in kinds(summarise(values), latches=latches)
    assert latches.divergence
    assert EventKind.JOB_DIVERGING not in kinds(summarise(values), latches=latches)


def test_divergence_threshold_is_configurable() -> None:
    values = [1.0 - 0.01 * i for i in range(30)] + [0.71 * 1.05**i for i in range(15)]
    assert EventKind.JOB_DIVERGING in kinds(summarise(values), diverge_percent=20)
    assert EventKind.JOB_DIVERGING not in kinds(summarise(values), diverge_percent=200)


def test_sudden_improvement_is_not_divergence() -> None:
    values = [1.0] * 30 + [0.4]  # one great batch: the smoothed curve lags above it
    assert EventKind.JOB_DIVERGING not in kinds(summarise(values))


def test_plateau_after_configured_time_and_reset_on_improvement() -> None:
    values = [1.0 - 0.01 * i for i in range(20)] + [0.81] * 20  # best at minute 19
    summaries = summarise(values)
    latches = MetricLatches()
    assert kinds(summaries, latches=latches, now=NOW + timedelta(minutes=70)) == []
    assert kinds(summaries, latches=latches, now=NOW + timedelta(minutes=80)) == [
        EventKind.JOB_PLATEAU
    ]
    assert kinds(summaries, latches=latches, now=NOW + timedelta(minutes=90)) == []

    improved = update_summaries(
        summaries, [Point("loss", 0.5, step=99, wall_time=NOW + timedelta(minutes=90))], NOW
    )
    assert kinds(improved, latches=latches, now=NOW + timedelta(minutes=91)) == []
    assert latches.plateau is False


def test_too_few_points_are_not_judged() -> None:
    assert kinds(summarise([1.0, 5.0, 9.0]), now=NOW + timedelta(days=1)) == []


@pytest.mark.parametrize(
    ("slurm_id", "expected"),
    [("123_4", "123"), ("123_[5-9%2]", "123"), ("123", None), ("123+0", None), ("x_1", None)],
)
def test_array_id(slurm_id: str, expected: str | None) -> None:
    assert array_id(slurm_id) == expected
