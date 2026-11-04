from collections.abc import Sequence


def downsample[T](points: Sequence[T], limit: int) -> list[T]:
    """Evenly spaced subset of at most ``limit`` points, always keeping the last."""
    if len(points) <= limit:
        return list(points)
    stride = len(points) / (limit - 1)
    picked = [points[int(i * stride)] for i in range(limit - 1)]
    return [*picked, points[-1]]
