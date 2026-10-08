"""Bounded external DjVu text extraction, using only the standard library."""

from __future__ import annotations

import math
import subprocess
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import BinaryIO

from opendoc_formats.errors import InvalidDocumentError, OperationCancelledError, ResourceLimitError
from opendoc_formats.types import Block, BlockType, DocFormat, Text


def extract_djvu_text(
    path: str | Path, *, timeout: float, max_output_bytes: int,
    cancelled: Callable[[], bool] | None,
) -> Text:
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("timeout must be a positive finite number")
    if type(max_output_bytes) is not int or max_output_bytes < 1:
        raise ValueError("max_output_bytes must be a positive integer")
    if cancelled is not None and not callable(cancelled):
        raise ValueError("cancelled must be callable")
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(source)

    def checkpoint() -> None:
        if cancelled and cancelled():
            raise OperationCancelledError("DjVu text extraction cancelled")

    def failure(message: str) -> Text:
        return Text(source_format=DocFormat.DJVU, engine="djvutxt", warnings=[message])

    checkpoint()
    try:
        process = subprocess.Popen(
            ["djvutxt", str(source.resolve())], stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, stdin=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        return failure("djvutxt not found in PATH")
    output = bytearray()
    overflow = threading.Event()
    lock = threading.Lock()
    total = 0

    def drain(stream: BinaryIO, keep: bool) -> None:
        nonlocal total
        while chunk := stream.read(4096):
            with lock:
                total += len(chunk)
                if total > max_output_bytes:
                    overflow.set()
                    return
                if keep:
                    output.extend(chunk)

    assert process.stdout is not None and process.stderr is not None
    threads = [
        threading.Thread(target=drain, args=(process.stdout, True), daemon=True),
        threading.Thread(target=drain, args=(process.stderr, False), daemon=True),
    ]
    deadline = time.monotonic() + timeout
    try:
        for thread in threads:
            thread.start()
        while process.poll() is None or any(thread.is_alive() for thread in threads):
            checkpoint()
            if overflow.is_set():
                raise ResourceLimitError("DjVu stdout/stderr exceed max_output_bytes")
            if time.monotonic() >= deadline:
                return failure("djvutxt timeout")
            time.sleep(0.02)
        checkpoint()
        if overflow.is_set():
            raise ResourceLimitError("DjVu stdout/stderr exceed max_output_bytes")
        if process.returncode != 0:
            return failure(f"djvutxt rc={process.returncode}")
        try:
            text = output.decode("utf-8", errors="strict")
        except UnicodeDecodeError as error:
            raise InvalidDocumentError("djvutxt returned invalid UTF-8") from error
        if not text.strip():
            return failure("DjVu has no nonempty hidden text layer")
        return Text(
            blocks=[Block(type=BlockType.PARAGRAPH, text=text)], plain=text,
            source_format=DocFormat.DJVU, engine="djvutxt",
        )
    finally:
        if process.poll() is None:
            process.kill()
        process.wait()
        for thread in threads:
            if thread.ident is not None:
                thread.join()
        process.stdout.close()
        process.stderr.close()
