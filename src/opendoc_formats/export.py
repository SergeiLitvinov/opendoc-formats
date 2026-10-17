"""Extensible model export with validation and atomic publication."""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from importlib import import_module
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, cast

from opendoc_model import ArtifactLimitError, ConversionReport, DocumentLimits, DocumentModel, IssueSeverity

from opendoc_formats.support.backends import missing_backends
from opendoc_formats.support.object_mapping import get_object_mapping, mapping_publication, mapping_result_matches
from opendoc_formats.text_profile import TextProfile, decode_text


@dataclass(frozen=True)
class ExportOptions:
    document_limits: DocumentLimits = field(default_factory=DocumentLimits)
    cancelled: Callable[[], bool] | None = None
    verify_output: bool = True
    txt_profile: TextProfile | None = None
    quality_gate: Callable[[ConversionReport, Path], bool] | None = None

    def __post_init__(self) -> None:
        if self.txt_profile is not None and not isinstance(self.txt_profile, TextProfile):
            raise ValueError("txt_profile must be TextProfile or None")
        if not isinstance(self.document_limits, DocumentLimits):
            raise ValueError("document_limits must be DocumentLimits")
        if self.cancelled is not None and not callable(self.cancelled):
            raise ValueError("cancelled must be callable")
        if self.quality_gate is not None and not callable(self.quality_gate):
            raise ValueError('quality_gate must be callable')
        if type(self.verify_output) is not bool:
            raise ValueError("verify_output must be bool")


Writer = Callable[[DocumentModel, Path], ConversionReport]
OutputValidator = Callable[[Path], None]


@dataclass(frozen=True)
class _ModelWriter:
    module: str
    name: str

    def __call__(
        self, document: DocumentModel, path: Path, *, limits: DocumentLimits | None = None,
        cancelled: Callable[[], bool] | None = None,
    ) -> ConversionReport:
        writer = cast(Callable[..., ConversionReport], getattr(
            import_module('opendoc_formats.writers.' + self.module), self.name,
        ))
        if self.module == 'pdf_writer':
            return writer(document, path, limits=limits, cancelled=cancelled)
        return writer(document, path, limits=limits)


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

        def fail(code: str, message: str, location: str = '') -> ConversionReport:
            report.add(IssueSeverity.ERROR, code, message, location)
            mapping_publication(report, 'rejected', code=code, reason=code)
            return report

        def limit_failure(error: ArtifactLimitError) -> ConversionReport:
            from opendoc_formats.support.document_limits import limit_diagnostic

            issue = limit_diagnostic(error, options.document_limits, str(output), 'export.document-limit')
            report.metrics['document_limit'] = issue.measurement
            return fail(issue.code, issue.message, issue.location or '')

        if exporter is None:
            return fail("export.unsupported-format", "No registered writer for the requested format")
        if options.cancelled and options.cancelled():
            return fail("export.cancelled", "Export cancelled before writing")
        if not isinstance(document, DocumentModel):
            return fail("export.invalid-model", "Expected an OpenDoc DocumentModel")
        try:
            errors = document.validate(limits=options.document_limits)
        except ArtifactLimitError as error:
            return limit_failure(error)
        if errors:
            return fail("export.invalid-model", "; ".join(errors))
        missing = missing_backends(exporter.requirements)
        if missing:
            return fail("export.backend-unavailable", "Missing optional backends: " + ", ".join(missing))
        output.parent.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(prefix=".opendoc-formats-export-", dir=output.parent) as directory:
            staged = Path(directory) / output.name
            try:
                written = (
                    _txt(document, staged, profile=options.txt_profile)
                    if exporter.writer is _txt else _json(document, staged, limits=options.document_limits)
                    if exporter.writer is _json else exporter.writer(
                        document, staged, limits=options.document_limits, cancelled=options.cancelled,
                    ) if isinstance(exporter.writer, _ModelWriter) else exporter.writer(document, staged)
                )
            except ArtifactLimitError as error:
                return limit_failure(error)
            if not isinstance(written, ConversionReport):
                return fail("export.invalid-result", "Writer did not return an OpenDoc ConversionReport")
            report = written
            report.output_path = output
            if identifier != 'docx' and (isinstance(exporter.writer, _ModelWriter) or exporter.writer is _txt):
                from opendoc_model import LINE_SPACING_PROPERTY, Paragraph, TextStyle, walk_model

                for reference in walk_model(document, limits=options.document_limits):
                    if (isinstance(reference.node, (Paragraph, TextStyle))
                            and LINE_SPACING_PROPERTY in reference.node.properties):
                        report.add(IssueSeverity.LOSS, 'line-spacing',
                                   'Native projection of the common LineSpacing declaration is not implemented',
                                   reference.path + '.properties.' + LINE_SPACING_PROPERTY)
            if identifier in {'html', 'pdf', 'pptx', 'epub', 'latex', 'txt'}:
                from opendoc_model import (
                    Paragraph,
                    Table,
                    TableCell,
                    TextRun,
                    TextStyle,
                    get_borders,
                    get_tab_stops,
                    get_table_indent,
                    walk_model,
                )

                color_context = DocumentModel(styles=document.styles)
                inherited_colors: dict[str | None, Any] = {}
                from opendoc_formats.ooxml.paragraph_flow import FIELDS, unresolved_flow
                from opendoc_formats.ooxml.paragraph_indent import ATTRIBUTES, unresolved_indent

                def paragraph_layout_loss(layout_properties: Mapping[str, Any], location: str) -> None:
                    if (any(unresolved_indent(layout_properties, key) for key in ATTRIBUTES)
                            or (identifier in {'txt', 'latex'}
                                and any(layout_properties.get(key) is not None for key in ATTRIBUTES))):
                        report.add(IssueSeverity.LOSS, 'docx.paragraph-indent',
                                   f'{identifier.upper()} does not preserve these native paragraph indents', location)
                    lost_flow = [key for key in FIELDS if identifier not in {'html', 'epub', 'pptx'} or not key.endswith('_pt')]
                    if (any(unresolved_flow(layout_properties, key) for key in FIELDS)
                            or any(layout_properties.get(key) is not None for key in lost_flow)):
                        report.add(IssueSeverity.LOSS, 'docx.paragraph-flow',
                                   f'{identifier.upper()} does not preserve these native paragraph flow declarations', location)

                for indent_style_id, indent_style in document.styles.items():
                    paragraph_layout_loss(indent_style.properties, f'styles[{indent_style_id}]')
                for reference in walk_model(document, limits=options.document_limits):
                    if isinstance(reference.node, Paragraph):
                        paragraph_layout_loss(reference.node.properties, reference.path)
                    elif isinstance(reference.node, TextRun):
                        paragraph_layout_loss(reference.node.style.properties, reference.path + '.style')
                    if (identifier not in {'html', 'pdf', 'pptx'}
                            and isinstance(reference.node, TextRun) and reference.node.style.color == 'auto'):
                        report.add(IssueSeverity.LOSS, 'color-auto',
                                   f'{identifier.upper()} cannot preserve native automatic color semantics',
                                   reference.path + '.style.color')
                    if identifier not in {'html', 'pdf', 'pptx'} and isinstance(reference.node, Paragraph):
                        from opendoc_model import resolve_style

                        identifiers = {reference.node.style_id}
                        identifiers.update(run.style.properties.base_style_id for run in reference.node.content
                                           if isinstance(run, TextRun) and run.style.color is None)
                        for style_identifier in identifiers:
                            if style_identifier not in inherited_colors:
                                inherited_colors[style_identifier] = resolve_style(
                                    color_context, style_identifier, limits=options.document_limits,
                                ).color
                        paragraph_color = inherited_colors[reference.node.style_id]
                        for index, run in enumerate(reference.node.content):
                            if not isinstance(run, TextRun) or run.style.color is not None:
                                continue
                            character_color = inherited_colors[run.style.properties.base_style_id]
                            if (character_color if character_color is not None else paragraph_color) == 'auto':
                                report.add(IssueSeverity.LOSS, 'color-auto',
                                           f'{identifier.upper()} cannot preserve native automatic color semantics',
                                           reference.path + f'.content[{index}].style.color')
                    if isinstance(reference.node, (Paragraph, TextStyle)) and any(
                        reference.node.properties.get(key) is not None
                        for key in ('docx_line_spacing_rule', 'docx_line_spacing_unsupported')
                    ):
                        report.add(IssueSeverity.LOSS, 'docx.line-spacing-rule',
                                   f'{identifier.upper()} does not preserve native Word line-spacing rules', reference.path)
                    if isinstance(reference.node, (Table, Paragraph, TextStyle)):
                        properties = reference.node.properties
                        for key, feature in (('docx_table_indent_pt', 'table-indent'), ('docx_tab_stops', 'tab-stops')):
                            common = (get_table_indent(reference.node) if isinstance(reference.node, Table) and
                                      feature == 'table-indent' else get_tab_stops(reference.node)
                                      if isinstance(reference.node, Paragraph) and feature == 'tab-stops' else None)
                            if common is not None or properties.get(key) or properties.get(key + '_unsupported'):
                                report.add(IssueSeverity.LOSS, 'docx.' + feature,
                                           f'{identifier.upper()} does not preserve native Word {feature}', reference.path)
                    if isinstance(reference.node, (Table, TableCell)) and get_borders(reference.node) is not None:
                        report.add(IssueSeverity.LOSS, 'table-borders',
                                   (f'{identifier.upper()} uses a finite visual border profile '
                                    'without preserving native declarations'
                                    if identifier in {'html', 'epub'} else
                                    f'{identifier.upper()} writer does not preserve common border declarations'), reference.path)
            if not report.success:
                mapping_publication(report, 'rejected', code='export.writer-rejected', reason='writer-failed')
                return report
            if get_object_mapping(report) is not None:
                mapping_publication(report, 'staged')
            if options.cancelled and options.cancelled():
                return fail("export.cancelled", "Export cancelled; staged result discarded")
            if not staged.is_file():
                return fail("export.missing-output", "Writer did not produce a file")
            if options.verify_output and exporter.validator is not None:
                try:
                    if exporter.writer is _txt:
                        decode_text(staged.read_bytes(), TextProfile(encoding=str(report.metrics["encoding"])))
                    elif exporter.writer is _json:
                        from opendoc_model import load_document

                        load_document(staged, limits=options.document_limits)
                    else:
                        exporter.validator(staged)
                except Exception as error:  # noqa: BLE001 - third-party validators are a diagnostic boundary
                    return fail("export.invalid-output", str(error))
                report.metrics["output_verified"] = True
            if options.quality_gate is not None:
                try:
                    accepted = options.quality_gate(report, staged)
                    if type(accepted) is not bool:
                        raise ValueError('quality_gate must return bool')
                except Exception as error:  # noqa: BLE001 - caller quality checks are a diagnostic boundary
                    return fail('export.quality-check', str(error))
                if not accepted or not report.success:
                    return fail('export.quality-rejected', 'Caller quality gate rejected the staged result')
            if not mapping_result_matches(report, staged):
                report.add(IssueSeverity.ERROR, 'export.mapping-invalidated', 'Staged bytes changed after mapping measurement')
                mapping_publication(report, 'invalidated', code='export.mapping-invalidated', reason='result-changed')
                return report
            if options.cancelled and options.cancelled():
                return fail("export.cancelled", "Export cancelled before publication")
            try:
                os.replace(staged, output)
            except OSError as error:
                return fail('export.publication-failed', str(error))
            mapping_publication(report, 'published')
        return report


def _writer(module: str, name: str) -> Writer:
    return _ModelWriter(module, name)


def _json(document: DocumentModel, path: Path, *, limits: DocumentLimits | None = None) -> ConversionReport:
    from opendoc_model import save_document

    save_document(document, path, limits=limits)
    return ConversionReport(path)


def _txt(document: DocumentModel, path: Path, *, profile: TextProfile | None = None) -> ConversionReport:
    from opendoc_formats.writers.txt_writer import write_txt_model

    return write_txt_model(document, path, profile=profile)


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
        ("epub", (".epub",), ()),
        ("docx", (".docx",), ("docx",)),
        ("pptx", (".pptx",), ("pptx",)),
        ("pdf", (".pdf",), ("fitz",)),
        ("latex", (".tex",), ("docx",)),
    ):
        registry.register(
            ExporterSpec(
                identifier,
                suffixes,
                _txt if identifier == "txt" else _writer(identifier + "_writer", "write_" + identifier + "_model"),
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
