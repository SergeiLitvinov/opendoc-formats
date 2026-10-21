"""Cooperative checkpoints for native format work; never interrupt a backend call."""

from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import TypeVar

from opendoc_formats.errors import OperationCancelledError

_Scope = tuple[Callable[[], bool] | None, str]
_scope: ContextVar[_Scope] = ContextVar('formats_native_import_cancellation', default=(None, 'Native import'))
_Item = TypeVar('_Item')


def check_cancelled(cancelled: Callable[[], bool] | None, operation: str) -> None:
    if cancelled is not None and not callable(cancelled):
        raise ValueError('cancelled must be callable or None')
    if cancelled is not None and cancelled():
        raise OperationCancelledError(operation+' cancelled')


@contextmanager
def cancellation_scope(cancelled: Callable[[], bool] | None, operation: str) -> Iterator[None]:
    """Bind a callback to one synchronous native import, restoring nested/concurrent state.

    Native helpers share this context rather than storing runtime state in Model
    objects. Only explicitly scoped readers activate implicit checkpoints.
    """
    check_cancelled(cancelled, operation)
    token = _scope.set((cancelled, operation))
    try:
        yield
        check_cancelled(cancelled, operation)
    finally:
        _scope.reset(token)


def checkpoint() -> None:
    """Check the active native import, or do nothing outside a reader scope."""
    cancelled, operation = _scope.get()
    check_cancelled(cancelled, operation)


def cancellable_items(items: Iterable[_Item]) -> Iterator[_Item]:
    """Keep comprehension traversal cancellable without changing order or values."""
    for item in items:
        checkpoint()
        yield item
