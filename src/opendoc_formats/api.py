"""Format reader registry using the OpenDoc model and validation contract."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from importlib import import_module
from pathlib import Path
from typing import cast

from opendoc_model import ArtifactLimitError, DiagnosticIssue, DocumentLimits, DocumentModel, IssueSeverity, get_integration

from opendoc_formats.support.backends import missing_backends
from opendoc_formats.text_profile import TextEncodingError, TextProfile


@dataclass(frozen=True)
class ImportOptions:
    max_input_bytes: int = 10 * 1024 * 1024
    resource_root: str | Path | None = None
    document_limits: DocumentLimits = field(default_factory=DocumentLimits)
    pdf_mode: str = "fast"
    ocr_engine_factory: Callable[..., object] | None = None
    cancelled: Callable[[], bool] | None = None
    txt_profile: TextProfile = field(default_factory=TextProfile)
    epub_include_nonlinear: bool = False

    def __post_init__(self) -> None:
        if type(self.epub_include_nonlinear) is not bool:
            raise ValueError("epub_include_nonlinear must be boolean")
        if not isinstance(self.txt_profile, TextProfile):
            raise ValueError("txt_profile must be TextProfile")
        if type(self.max_input_bytes) is not int or self.max_input_bytes < 1:
            raise ValueError("max_input_bytes must be a positive integer")
        if not isinstance(self.document_limits, DocumentLimits):
            raise ValueError("document_limits must be DocumentLimits")
        if self.cancelled is not None and not callable(self.cancelled):
            raise ValueError("cancelled must be callable")
        if self.resource_root is not None and not isinstance(self.resource_root, (str, Path)):
            raise ValueError("resource_root must be a path")
        if self.pdf_mode not in ("fast", "structure", "scan"):
            raise ValueError("pdf_mode must be fast, structure or scan")
        if self.ocr_engine_factory is not None and not callable(self.ocr_engine_factory):
            raise ValueError("ocr_engine_factory must be callable")


@dataclass(frozen=True)
class ImportResult:
    document: DocumentModel | None
    format_id: str
    issues: tuple[DiagnosticIssue, ...] = ()

    @property
    def success(self) -> bool:
        return self.document is not None and not any(issue.severity is IssueSeverity.ERROR for issue in self.issues)

    @property
    def assessment_complete(self) -> bool:
        """Only an explicit, fully reported OpenDoc assessment proves coverage."""
        if self.document is None:
            return False
        model = get_integration(self.document)
        return bool(
            model is not None and model.assessment_complete and model.assessed_features
            and {record.issue.code for record in model.preservation} == set(model.assessed_features)
        )

    @property
    def lossless(self) -> bool:
        from opendoc_model import PreservationState

        if not self.success or not self.assessment_complete or self.document is None:
            return False
        model = get_integration(self.document)
        return bool(
            model is not None
            and all(record.state is PreservationState.SEMANTIC for record in model.preservation)
            and not any(issue.severity in (IssueSeverity.LOSS, IssueSeverity.ERROR) for issue in self.issues)
        )


Reader = Callable[[Path, ImportOptions], DocumentModel]


@dataclass(frozen=True)
class AdapterSpec:
    id: str
    extensions: tuple[str, ...]
    reader: Reader
    requirements: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id or not callable(self.reader):
            raise ValueError("adapter requires a nonempty ID and callable reader")
        if not self.extensions or any(
            not isinstance(value, str) or len(value) < 2 or not value.startswith(".") or value != value.lower()
            for value in self.extensions
        ):
            raise ValueError("extensions must be lowercase dotted suffixes")
        if len(set(self.extensions)) != len(self.extensions):
            raise ValueError("duplicate extensions in adapter")
        if any(not isinstance(name, str) or not name for name in self.requirements):
            raise ValueError("requirements must be nonempty module names")


class AdapterRegistry:
    def __init__(self) -> None:
        self._adapters: dict[str, AdapterSpec] = {}
        self._suffixes: dict[str, str] = {}

    def register(self, adapter: AdapterSpec) -> None:
        if not isinstance(adapter, AdapterSpec):
            raise ValueError("expected AdapterSpec")
        if adapter.id in self._adapters or any(value in self._suffixes for value in adapter.extensions):
            raise ValueError("duplicate adapter ID or extension")
        self._adapters[adapter.id] = adapter
        self._suffixes.update(dict.fromkeys(adapter.extensions, adapter.id))

    def adapters(self) -> tuple[AdapterSpec, ...]:
        return tuple(self._adapters.values())

    def read(self, path: str | Path, *, format_id: str | None = None, options: ImportOptions | None = None) -> ImportResult:
        source = Path(path)
        options = ImportOptions() if options is None else options
        if not isinstance(options, ImportOptions):
            raise ValueError("options must be ImportOptions")
        identifier = format_id or self._suffixes.get(source.suffix.lower(), "")

        def failure(code: str, message: str) -> ImportResult:
            return ImportResult(None, identifier, (DiagnosticIssue(code, IssueSeverity.ERROR, message, str(source)),))

        adapter = self._adapters.get(identifier)
        if adapter is None:
            return failure("import.unsupported-format", "No registered reader for the requested format")
        if options.cancelled and options.cancelled():
            return failure("import.cancelled", "Import cancelled before reading")
        if source.stat().st_size > options.max_input_bytes:
            return failure("import.input-limit", "Input exceeds max_input_bytes")
        missing = missing_backends(adapter.requirements)
        if missing:
            return failure("import.backend-unavailable", "Missing optional backends: " + ", ".join(missing))
        # Reader failures and missing files remain exceptions; never manufacture a valid empty model.
        try:
            document = adapter.reader(source, options)
        except TextEncodingError as error:
            return ImportResult(None, identifier, (DiagnosticIssue(
                "import.txt-encoding", IssueSeverity.ERROR, str(error), str(source), reason=error.reason,
            ),))
        if not isinstance(document, DocumentModel):
            return failure("import.invalid-result", "Reader did not return an OpenDoc DocumentModel")
        if options.cancelled and options.cancelled():
            return failure("import.cancelled", "Import cancelled; result discarded")
        try:
            errors = document.validate(limits=options.document_limits)
        except ArtifactLimitError as error:
            return failure("import.document-limit", str(error))
        if errors:
            return failure("import.invalid-model", "; ".join(errors))
        return ImportResult(document, identifier, _import_issues(document, identifier, source, options.document_limits))


def _import_issues(
    document: DocumentModel, identifier: str, source: Path, limits: DocumentLimits,
) -> tuple[DiagnosticIssue, ...]:
    """Expose existing diagnostics without guessing preservation from prose."""
    from opendoc_model import PreservationState

    issues: list[DiagnosticIssue] = []
    model = get_integration(document, limits=limits)
    if model is not None:
        for record in model.preservation:
            issue = record.issue
            if record.state is not PreservationState.SEMANTIC:
                severity = IssueSeverity.ERROR if record.state is PreservationState.REJECTED else IssueSeverity.LOSS
                issue = DiagnosticIssue(
                    issue.code, severity, issue.message, issue.location,
                    {**(issue.measurement or {}), "state": record.state.value, "node_id": record.node_id}, issue.reason,
                )
            issues.append(issue)
    containers = [(document.metadata, "metadata")]
    nested = document.metadata.get(identifier)
    if isinstance(nested, dict):
        containers.append((nested, f"metadata.{identifier}"))
    for container, location in containers:
        warnings = container.get("warnings", [])
        if not isinstance(warnings, list):
            continue
        for index, item in enumerate(warnings):
            fallback = f"{source}#{location}.warnings[{index}]"
            if isinstance(item, str):
                issue = DiagnosticIssue(f"{identifier}.warning", IssueSeverity.WARNING, item, fallback)
            elif isinstance(item, dict):
                issue = DiagnosticIssue(
                    str(item.get("feature") or f"{identifier}.warning"), IssueSeverity.WARNING,
                    str(item.get("message", "")), str(item.get("location") or fallback),
                )
            else:
                continue
            if issue not in issues:
                issues.append(issue)
    return tuple(issues)


def _txt(path: Path, options: ImportOptions) -> DocumentModel:
    reader = cast(Callable[..., DocumentModel], import_module("opendoc_formats.readers.txt").read_txt_model)
    return reader(path, profile=options.txt_profile)


def _html(path: Path, options: ImportOptions) -> DocumentModel:
    reader = cast(Callable[..., DocumentModel], import_module("opendoc_formats.readers.html").read_html_model)
    return reader(path, resource_root=options.resource_root)


def default_registry() -> AdapterRegistry:
    registry = AdapterRegistry()
    registry.register(AdapterSpec("txt", (".txt",), _txt))
    registry.register(AdapterSpec("latex", (".tex",), _tex))
    registry.register(AdapterSpec("html", (".html", ".htm"), _html, ("bs4", "tinycss2")))
    registry.register(AdapterSpec("docx", (".docx",), _docx, ("docx",)))
    registry.register(AdapterSpec("pptx", (".pptx",), _pptx, ("pptx",)))
    registry.register(AdapterSpec("epub", (".epub",), _epub, ("bs4",)))
    registry.register(AdapterSpec("pdf", (".pdf",), _pdf, ("fitz",)))
    registry.register(AdapterSpec("json", (".json",), _json))
    registry.register(AdapterSpec("djvu", (".djvu",), _djvu))
    return registry


def read_document(path: str | Path, *, format_id: str | None = None, options: ImportOptions | None = None) -> ImportResult:
    return default_registry().read(path, format_id=format_id, options=options)


def _docx(path: Path, options: ImportOptions) -> DocumentModel:
    reader = cast(Callable[[Path], DocumentModel], import_module("opendoc_formats.readers.docx").read_docx_model)
    return reader(path)


def _tex(path: Path, options: ImportOptions) -> DocumentModel:
    from opendoc_formats.readers.tex_model import read_tex_model

    return read_tex_model(path, max_input_bytes=options.max_input_bytes, cancelled=options.cancelled)


def _pptx(path: Path, options: ImportOptions) -> DocumentModel:
    reader = cast(Callable[[Path], DocumentModel], import_module("opendoc_formats.readers.pptx").read_pptx_model)
    return reader(path)


def _epub(path: Path, options: ImportOptions) -> DocumentModel:
    reader = cast(Callable[..., DocumentModel], import_module("opendoc_formats.readers.epub_model").read_epub_model)
    return reader(path, include_nonlinear=options.epub_include_nonlinear)


def _pdf(path: Path, options: ImportOptions) -> DocumentModel:
    reader = cast(Callable[..., DocumentModel], import_module("opendoc_formats.readers.pdf_model").read_pdf_model)
    return reader(path=path, mode=options.pdf_mode, ocr_engine_factory=options.ocr_engine_factory)


def _json(path: Path, options: ImportOptions) -> DocumentModel:
    from opendoc_model import load_document

    return load_document(path)


def _djvu(path: Path, options: ImportOptions) -> DocumentModel:
    from opendoc_formats.errors import ExtractError

    text = import_module("opendoc_formats.readers.txt").read_djvu(path)
    if not text:
        raise ExtractError("; ".join(text.warnings) or "DjVu text extraction returned no content")
    converter = cast(Callable[..., DocumentModel], import_module("opendoc_formats.support.document_adapters").text_to_document)
    return converter(text)
