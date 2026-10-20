"""Cooperative checkpoints for native format work; never interrupt a backend call."""

from collections.abc import Callable

from opendoc_formats.errors import OperationCancelledError


def check_cancelled(cancelled: Callable[[], bool] | None, operation: str) -> None:
    if cancelled is not None and not callable(cancelled):
        raise ValueError('cancelled must be callable or None')
    if cancelled is not None and cancelled():
        raise OperationCancelledError(operation+' cancelled')
