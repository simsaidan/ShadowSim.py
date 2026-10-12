"""Run independent simulator time points on a process pool."""

from collections.abc import Callable, Sequence
from concurrent.futures import Future, ProcessPoolExecutor, as_completed
from typing import Any

ProgressCallback = Callable[[int, int], None]
TimeCall = tuple[Callable[..., Any], tuple[Any, ...], dict[str, Any]]


def map_time_points(
    workers: int,
    calls: Sequence[TimeCall],
    *,
    progress: ProgressCallback | None = None,
    on_result: Callable[[int, Any], Any] | None = None,
) -> list[Any]:
    """Run one picklable call per time index and return results in call order.

    Each item of ``calls`` is ``(function, args, kwargs)``. The function must
    be importable in a spawned process. ``on_result(index, value)`` and
    ``progress(index, total)`` run in this process when that call finishes, so
    neither has to be pickled. A failure cancels calls that have not started
    and raises; no result list is returned.

    Args:
        workers: Process-pool size. Must be at least 1.
        calls: One call per time index, already carrying that index's arguments.
        progress: Optional ``(index, total)`` callback, in completion order.
        on_result: Optional parent-process hook. Its return value is stored.

    Returns:
        One result per call, in the same order as ``calls``.

    Raises:
        Exception: Whatever a call or ``on_result`` raised. Pending calls are
            cancelled first.
    """
    total = len(calls)
    executor = ProcessPoolExecutor(max_workers=workers)
    ordered: list[Any] = [None] * total
    try:
        futures: dict[Future[Any], int] = {
            executor.submit(function, *args, **kwargs): index for index, (function, args, kwargs) in enumerate(calls)
        }
        for future in as_completed(futures):
            index = futures[future]
            value = future.result()
            if on_result is not None:
                value = on_result(index, value)
            ordered[index] = value
            if progress is not None:
                progress(index, total)
        return ordered
    finally:
        executor.shutdown(wait=True, cancel_futures=True)
