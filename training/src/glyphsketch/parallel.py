"""Worker pools that leave the machine usable.

Each spawned worker would otherwise start one BLAS/OpenMP thread per core, so N workers
ran N × cores threads and swamped the laptop. Workers get one thread each, and by default
there are half as many workers as cores.
"""

import multiprocessing
import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from multiprocessing.pool import Pool
from typing import Any

THREAD_VARIABLES = (
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
)


def default_workers(tasks: int | None = None) -> int:
    """Half the cores (``GLYPHSKETCH_WORKERS`` overrides), never more than the task count."""
    configured = os.environ.get("GLYPHSKETCH_WORKERS")
    workers = int(configured) if configured else max(1, (os.cpu_count() or 2) // 2)
    return max(1, min(workers, tasks)) if tasks is not None else workers


@contextmanager
def single_threaded_pool(
    workers: int,
    initializer: Callable[..., None] | None = None,
    initargs: tuple[Any, ...] = (),
) -> Iterator[Pool]:
    """A spawn pool whose workers inherit one-thread settings for every numeric library."""
    saved = {name: os.environ.get(name) for name in THREAD_VARIABLES}
    os.environ.update({name: "1" for name in THREAD_VARIABLES})
    try:
        pool = multiprocessing.get_context("spawn").Pool(
            workers, initializer=initializer, initargs=initargs
        )
    finally:
        for name, value in saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
    with pool:
        yield pool
