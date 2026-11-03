"""Текстовый ридер с цепочкой fallback-движков.

Стратегия:
  pdfplumber → pypdf → pymupdf (geometry → semantics)

Каждый движок возвращает ``Text`` с заполненным ``engine``. Если движок
бросил исключение, пробуем следующий. Если все упали — ``Text(warnings=[...])``
с пустым содержимым, чтобы пайплайн мог корректно зафиксировать «не смогли».
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

from opendoc_model import ArtifactLimitError, DiagnosticIssue, IssueSeverity, PreservationRecord, Provenance

from opendoc_formats.errors import OperationCancelledError, ResourceLimitError
from opendoc_formats.readers.pdf_geometry import PdfGeometryDocument, extract_pdf_geometry
from opendoc_formats.readers.pdf_semantic import analyze_pdf_geometry
from opendoc_formats.support.backends import missing_backends
from opendoc_formats.support.cancellation import (
    cancellable_items,
    cancellation_requested,
    cancellation_scope,
    checkpoint,
)
from opendoc_formats.support.text_diagnostics import append_text_warning, ledger, offset_records
from opendoc_formats.types import Block, BlockType, DocFormat, Text

logger = logging.getLogger(__name__)


def _safe_call(name: str, fn: Callable[[], Text], *, path: str | None = None) -> Text:
    try:
        return fn()
    except (OperationCancelledError, ArtifactLimitError, ResourceLimitError):
        raise
    except Exception as e:  # noqa: BLE001
        logger.warning("PDF engine %s failed: %s", name, e)
        result = Text(source_format=DocFormat.PDF, engine=name)
        append_text_warning(result, DiagnosticIssue(
            'pdf.text-backend-failed', IssueSeverity.LOSS, f'{name}: {type(e).__name__}: {e}',
            f'{path or "pdf"}#text-backend={name}', {'backend': name}, 'pdf-text-backend-failed',
        ), Provenance('pdf', path, object_id=f'text-backend-{name}'))
        return result


def _with_pdfplumber(path: str) -> Text:
    import pdfplumber

    blocks: list[Block] = []
    pages = 0
    plain_parts: list[str] = []
    with pdfplumber.open(path) as pdf:
        pages = len(pdf.pages)
        for i, page in enumerate(pdf.pages, start=1):
            checkpoint()
            text = page.extract_text() or ""
            checkpoint()
            if text:
                blocks.append(Block(type=BlockType.PARAGRAPH, text=text, page=i))
                plain_parts.append(text)
            for tbl in cancellable_items(page.extract_tables() or []):
                rows = [[(c if c is not None else "") for c in cancellable_items(row)] for row in cancellable_items(tbl)]

                blocks.append(Block(type=BlockType.TABLE, page=i, meta={"rows": rows}))

    return Text(
        blocks=blocks,
        plain="\n".join(plain_parts),
        source_format=DocFormat.PDF,
        engine="pdfplumber",
        pages=pages,
    )


def _with_pypdf(path: str) -> Text:
    from pypdf import PdfReader

    reader = PdfReader(path)
    checkpoint()
    plain_parts: list[str] = []
    result = Text(source_format=DocFormat.PDF, engine='pypdf', pages=len(reader.pages))
    for i, page in enumerate(reader.pages, start=1):
        checkpoint()
        try:
            t = page.extract_text() or ""
        except (OperationCancelledError, ArtifactLimitError, ResourceLimitError):
            raise
        except Exception as error:  # noqa: BLE001
            append_text_warning(result, DiagnosticIssue(
                'pdf.text-page-failed', IssueSeverity.LOSS, f'pypdf page {i}: {type(error).__name__}: {error}',
                f'{path}#page={i}/text', {'backend': 'pypdf'}, 'pdf-text-page-extraction-failed',
            ), Provenance('pdf', path, page=i, object_id='text-extraction'))
            t = ""
        checkpoint()
        if t:
            plain_parts.append(t)
    plain = "\n".join(plain_parts)
    if plain.count("\x00") > len(plain) * 0.1:
        append_text_warning(result, DiagnosticIssue(
            'pdf.text-decoding-cleanup', IssueSeverity.LOSS, 'pypdf text contained excessive NUL characters; cleaned text',
            f'{path}#text', {'nul_count': plain.count('\x00'), 'replacement_count': plain.count('\ufffd')},
            'pdf-text-decoding-unassessed',
        ), Provenance('pdf', path, object_id='text-decoding'))
        plain = plain.replace("\x00", "").replace("\ufffd", "")
    result.blocks = [Block(type=BlockType.PARAGRAPH, text=plain)] if plain else []
    result.plain = plain
    return result


def _with_pymupdf(path: str) -> Text:
    return analyze_pdf_geometry(extract_pdf_geometry(path, cancelled=cancellation_requested), cancelled=cancellation_requested)


def read_pdf_geometry(path: str | Path, *, cancelled: Callable[[], bool] | None = None) -> PdfGeometryDocument:
    """Публичный геометрический импорт PDF без семантических эвристик."""

    return extract_pdf_geometry(path, cancelled=cancelled)


def read_pdf(path: str, *, cancelled: Callable[[], bool] | None = None) -> Text:
    """Достать текст из PDF: pdfplumber → pypdf → pymupdf.

    Возвращает первый успешный (ненулевой) результат; предупреждения всех
    упавших движков притаскиваются в ``warnings`` итогового ``Text``.
    """
    with cancellation_scope(cancelled, 'PDF text import'):
        return _read_pdf(path)


def _read_pdf(path: str) -> Text:
    engines: list[tuple[str, Callable[[str], Text]]] = [
        ("pdfplumber", _with_pdfplumber),
        ("pypdf", _with_pypdf),
        ("pymupdf", _with_pymupdf),
    ]
    warnings: list[str] = []
    records: list[PreservationRecord] = []
    available = 0
    pages = 0
    for name, fn in engines:
        checkpoint()
        if missing_backends((name,)):
            continue
        available += 1
        result = _safe_call(name, lambda: fn(path), path=path)
        checkpoint()
        records.extend(offset_records(result.diagnostics, len(warnings)))
        pages = max(pages, result.pages)
        if result:
            result.warnings = warnings + result.warnings
            result.diagnostics = ledger(tuple(records)) if records else None
            return result
        warnings.extend(result.warnings)
    result = Text(source_format=DocFormat.PDF, engine='none', warnings=warnings, pages=pages,
                  diagnostics=ledger(tuple(records)) if records else None)
    if not warnings:
        append_text_warning(result, DiagnosticIssue(
            'pdf.text-no-content' if available else 'pdf.text-backend-unavailable', IssueSeverity.LOSS,
            'no PDF engine succeeded', f'{path}#text', {'available_backends': available},
            'pdf-text-no-content-returned' if available else 'pdf-text-no-backend',
        ), Provenance('pdf', path, object_id='text-extraction'))
    return result


def get_pdf_info(path: str) -> dict[str, str]:
    """Извлечь title/author/subject уже установленным PDF-движком."""
    info = {"title": "", "author": "", "subject": ""}
    try:
        from opendoc_formats.support.pdf_probe import probe_pdf

        _, info = probe_pdf(path, metadata=True)
    except Exception:  # noqa: BLE001
        pass
    return info


__all__ = ["get_pdf_info", "read_pdf", "read_pdf_geometry"]
