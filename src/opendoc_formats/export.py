"""Extensible model export with validation and atomic publication."""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass, field
from importlib import import_module
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import cast

from opendoc import ArtifactLimitError, ConversionReport, DocumentLimits, DocumentModel, IssueSeverity

from opendoc_formats.support.backends import missing_backends


@dataclass(frozen=True)
class ExportOptions:
    document_limits: DocumentLimits = field(default_factory=DocumentLimits)
    cancelled: Callable[[], bool] | None = None
    verify_output: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.document_limits, DocumentLimits):
            raise ValueError("document_limits must be DocumentLimits")
        if self.cancelled is not None and not callable(self.cancelled):
            raise ValueError("cancelled must be callable")
        if type(self.verify_output) is not bool:
            raise ValueError("verify_output must be bool")


Writer = Callable[[DocumentModel, Path], ConversionReport]
OutputValidator = Callable[[Path], None]


@dataclass(frozen=True)
class ExporterSpec:
    id: str
    extensions: tuple[str, ...]
    writer: Writer
    requirements: tuple[str, ...] = ()
    validator: OutputValidator | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id or not callable(self.writer) or not self.extensions:
            raise ValueError("exporter requires ID, writer and extensions")
        if any(
            not isinstance(suffix, str) or len(suffix) < 2 or not suffix.startswith(".") or suffix != suffix.lower()
            for suffix in self.extensions
        ):
            raise ValueError("extensions must be lowercase dotted suffixes")
        if len(set(self.extensions)) != len(self.extensions):
            raise ValueError("duplicate extensions in exporter")
        if any(not isinstance(name, str) or not name for name in self.requirements):
            raise ValueError("requirements must be nonempty module names")
        if self.validator is not None and not callable(self.validator):
            raise ValueError("validator must be callable")


class ExporterRegistry:
    def __init__(self) -> None:
        self._exporters: dict[str, ExporterSpec] = {}
        self._suffixes: dict[str, str] = {}

    def register(self, exporter: ExporterSpec) -> None:
        if not isinstance(exporter, ExporterSpec):
            raise ValueError("expected ExporterSpec")
        if exporter.id in self._exporters or any(suffix in self._suffixes for suffix in exporter.extensions):
            raise ValueError("duplicate exporter ID or extension")
        self._exporters[exporter.id] = exporter
        self._suffixes.update(dict.fromkeys(exporter.extensions, exporter.id))

    def exporters(self) -> tuple[ExporterSpec, ...]:
        return tuple(self._exporters.values())

    def write(
        self, document: DocumentModel, path: str | Path, *, format_id: str | None = None, options: ExportOptions | None = None
    ) -> ConversionReport:
        output = Path(path)
        options = ExportOptions() if options is None else options
        if not isinstance(options, ExportOptions):
            raise ValueError("options must be ExportOptions")
        report = ConversionReport(output)
        identifier = format_id or self._suffixes.get(output.suffix.lower(), "")
        exporter = self._exporters.get(identifier)

        def fail(code: str, message: str) -> ConversionReport:
            report.add(IssueSeverity.ERROR, code, message)
            return report

        if exporter is None:
            return fail("export.unsupported-format", "No registered writer for the requested format")
        if options.cancelled and options.cancelled():
            return fail("export.cancelled", "Export cancelled before writing")
        if not isinstance(document, DocumentModel):
            return fail("export.invalid-model", "Expected an OpenDoc DocumentModel")
        try:
            errors = document.validate(limits=options.document_limits)
        except ArtifactLimitError as error:
            return fail("export.document-limit", str(error))
        if errors:
            return fail("export.invalid-model", "; ".join(errors))
        missing = missing_backends(exporter.requirements)
        if missing:
            return fail("export.backend-unavailable", "Missing optional backends: " + ", ".join(missing))
        output.parent.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(prefix=".opendoc-formats-export-", dir=output.parent) as directory:
            staged = Path(directory) / output.name
            written = exporter.writer(document, staged)
            if not isinstance(written, ConversionReport):
                return fail("export.invalid-result", "Writer did not return an OpenDoc ConversionReport")
            report = written
            report.output_path = output
            if not report.success:
                return report
            if options.cancelled and options.cancelled():
                return fail("export.cancelled", "Export cancelled; staged result discarded")
            if not staged.is_file():
                return fail("export.missing-output", "Writer did not produce a file")
            if options.verify_output and exporter.validator is not None:
                try:
                    exporter.validator(staged)
                except Exception as error:  # noqa: BLE001 - third-party validators are a diagnostic boundary
                    return fail("export.invalid-output", str(error))
                report.metrics["output_verified"] = True
            if options.cancelled and options.cancelled():
                return fail("export.cancelled", "Export cancelled before publication")
            os.replace(staged, output)
        return report


def _writer(module: str, name: str) -> Writer:
    def write(document: DocumentModel, path: Path) -> ConversionReport:
        writer = cast(Writer, getattr(import_module("opendoc_formats.writers." + module), name))
        return writer(document, path)

    return write


def _json(document: DocumentModel, path: Path) -> ConversionReport:
    from opendoc import save_document

    save_document(document, path)
    return ConversionReport(path)


def _validator(identifier: str) -> OutputValidator:
    def verify(path: Path) -> None:
        from opendoc_formats.support.output_validation import validate_output

        validate_output(path, identifier)

    return verify


def default_exporter_registry() -> ExporterRegistry:
    registry = ExporterRegistry()
    for identifier, suffixes, requirements in (
        ("txt", (".txt",), ()),
        ("html", (".html", ".htm"), ()),
        ("docx", (".docx",), ("docx",)),
        ("pptx", (".pptx",), ("pptx",)),
        ("pdf", (".pdf",), ("fitz",)),
        ("latex", (".tex",), ("docx",)),
    ):
        registry.register(
            ExporterSpec(
                identifier,
                suffixes,
                _writer(identifier + "_writer", "write_" + identifier + "_model"),
                requirements,
                _validator(identifier),
            )
        )
    registry.register(ExporterSpec("json", (".json",), _json, validator=_validator("json")))
    return registry


def write_document(
    document: DocumentModel, path: str | Path, *, format_id: str | None = None, options: ExportOptions | None = None
) -> ConversionReport:
    return default_exporter_registry().write(document, path, format_id=format_id, options=options)
