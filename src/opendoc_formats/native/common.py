"""Bounded inputs, cooperative cancellation and atomic publication."""

from __future__ import annotations

import importlib
import math
import os
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from uuid import uuid4

from opendoc_formats.errors import BackendUnavailableError, InvalidDocumentError, OperationCancelledError, ResourceLimitError

Cancellation = Callable[[], bool]
Source = str | Path | bytes


def check_cancel(cancelled: Cancellation | None) -> None:
    if cancelled is not None and cancelled():
        raise OperationCancelledError("Operation cancelled at a checkpoint")


def positive_int(value: int, name: str, *, zero: bool = False) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < (0 if zero else 1):
        raise ValueError(f"{name} must be {'non-negative' if zero else 'positive'} integer")


def positive_number(value: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be a finite positive number")
    return float(value)


def backend(module: str, extra: str) -> ModuleType:
    try:
        return importlib.import_module(module)
    except ImportError as error:
        raise BackendUnavailableError(f"Install opendoc-formats[{extra}]; unavailable backend: {module}") from error


def read_source(source: Source, maximum: int, cancelled: Cancellation | None) -> bytes:
    check_cancel(cancelled)
    if isinstance(source, bytes):
        data = source
    elif isinstance(source, (str, Path)):
        try:
            with Path(source).open("rb") as stream:
                data = stream.read(maximum + 1)
        except OSError as error:
            raise InvalidDocumentError(f"Cannot read document: {error}") from error
    else:
        raise TypeError("source must be a path or bytes")
    if len(data) > maximum:
        raise ResourceLimitError(f"Input exceeds {maximum} bytes")
    check_cancel(cancelled)
    return data


def publish(data: bytes, output: str | Path, maximum: int, cancelled: Cancellation | None) -> Path:
    if len(data) > maximum:
        raise ResourceLimitError(f"Output exceeds {maximum} bytes")
    check_cancel(cancelled)
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(f".{target.name}.{uuid4().hex}.partial")
    try:
        partial.write_bytes(data)
        check_cancel(cancelled)
        os.replace(partial, target)
    finally:
        partial.unlink(missing_ok=True)
    return target
