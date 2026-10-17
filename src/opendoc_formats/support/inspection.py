"""Структурная инспекция документов и промежуточной модели."""

from __future__ import annotations

import base64
import hashlib
import re
from collections import Counter
from collections.abc import Callable
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from opendoc_model import ArtifactLimitError
from opendoc_model.diagnostics import IssueSeverity
from opendoc_model.inspection import (
    DocumentComparison as DocumentComparison,
)
from opendoc_model.inspection import (
    DocumentInspection as DocumentInspection,
)
from opendoc_model.inspection import (
    compare_inspections as compare_inspections,
)
from opendoc_model.inspection import (
    inspect_document_model as inspect_document_model,
)

from opendoc_formats.api import ImportOptions
from opendoc_formats.errors import FormatError, OperationCancelledError
from opendoc_formats.support.document_limits import limit_diagnostic


def inspect_path(path: str | Path, *, options: ImportOptions | None = None) -> DocumentInspection:
    """Inspect DOCX, PDF, PPTX, TXT, HTML, LaTeX or a JSON-serialized DocumentModel."""

    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(source)
    if options is not None and not isinstance(options, ImportOptions):
        raise ValueError('options must be ImportOptions')
    # Preserve the existing PDF input ceiling when called without options.
    chosen = options or ImportOptions(max_input_bytes=128 * 1024 * 1024)
    formats = {'.json': 'document-model-json', '.tex': 'latex'}
    identifier = formats.get(source.suffix.lower(), source.suffix.lower().lstrip('.'))
    if source.suffix.lower() not in {'.txt', '.docx', '.json', '.pdf', '.pptx', '.html', '.tex'}:
        raise FormatError(f"Unsupported inspection format: {source.suffix.lower() or '<none>'}")
    refusal = DocumentInspection(source, identifier)
    refusal.metadata['inspection_status'] = 'refused'
    try:
        _inspection_checkpoint(chosen.cancelled)
        if source.stat().st_size > chosen.max_input_bytes:
            refusal.add(IssueSeverity.ERROR, 'inspection.input-limit', 'Input exceeds max_input_bytes', str(source))
            return refusal
        digest = _inspection_digest(source, chosen)
        refusal.metadata['inspection_source_sha256'] = digest
        report = _inspect_path(source, chosen)
        _inspection_checkpoint(chosen.cancelled)
        if digest != _inspection_digest(source, chosen):
            refusal.add(IssueSeverity.ERROR, 'inspection.source-changed', 'Source changed during inspection', str(source))
            return refusal
        report.metadata['inspection_source_sha256'] = digest
        profile = report.metadata.get('text_flow_profile', {})
        partial = source.suffix.lower() == '.pdf' and not profile.get('complete', False)
        report.metadata['inspection_status'] = 'partial' if partial else ('completed' if report.valid else 'refused')
        return report
    except ArtifactLimitError as error:
        issue = limit_diagnostic(error, chosen.document_limits, str(source), 'inspection.document-limit')
        refusal.add(issue.severity, issue.code, issue.message, issue.location)
        refusal.metadata['document_limit'] = issue.measurement
        return refusal
    except OperationCancelledError:
        refusal.metadata['inspection_status'] = 'cancelled'
        refusal.add(IssueSeverity.ERROR, 'inspection.cancelled', 'Inspection cancelled; measurements discarded', str(source))
        return refusal


def _inspection_checkpoint(cancelled: Callable[[], bool] | None) -> None:
    if cancelled and cancelled():
        raise OperationCancelledError('Inspection cancelled')


def _inspection_digest(source: Path, options: ImportOptions) -> str:
    digest = hashlib.sha256()
    size = 0
    with source.open('rb') as stream:
        while True:
            _inspection_checkpoint(options.cancelled)
            chunk = stream.read(min(65536, options.max_input_bytes - size + 1))
            if not chunk:
                return digest.hexdigest()
            size += len(chunk)
            if size > options.max_input_bytes:
                raise ArtifactLimitError('Source grew beyond max_input_bytes during inspection',
                                         path='source', quota='input bytes', maximum=options.max_input_bytes)
            digest.update(chunk)


def _inspect_path(source: Path, options: ImportOptions) -> DocumentInspection:
    suffix = source.suffix.lower()
    if suffix == ".txt":
        from opendoc_formats.readers.txt import read_txt_model

        model = read_txt_model(source, profile=options.txt_profile)
        _inspection_checkpoint(options.cancelled)
        report = inspect_document_model(model, source_path=source, source_format="txt", limits=options.document_limits)
        # Model defaults are not evidence of pagination in a plain-text source.
        report.pages.clear()
        report.metrics.pop("pages", None)
        return report
    if suffix == ".docx":
        from opendoc_formats.readers.docx import read_docx_model

        model = read_docx_model(source, limits=options.document_limits)
        _inspection_checkpoint(options.cancelled)
        return inspect_document_model(model, source_path=source, source_format="docx", limits=options.document_limits)
    if suffix == ".json":
        from opendoc_model.document_codec import load_document

        model = load_document(source, limits=options.document_limits)
        _inspection_checkpoint(options.cancelled)
        return inspect_document_model(model, source_path=source, source_format="document-model-json",
                                      limits=options.document_limits)
    if suffix == ".pdf":
        return _inspect_pdf(source, cancelled=options.cancelled)
    if suffix == ".pptx":
        from opendoc_formats.readers.pptx import read_pptx_model

        model = read_pptx_model(source, limits=options.document_limits)
        _inspection_checkpoint(options.cancelled)
        return inspect_document_model(model, source_path=source, source_format="pptx", limits=options.document_limits)
    if suffix == ".html":
        return _inspect_html(source)
    if suffix == ".tex":
        return _inspect_latex(source)
    raise FormatError(f"Unsupported inspection format: {suffix or '<none>'}")


_PDF_INSPECTION_MAX_BYTES = 128 * 1024 * 1024
_PDF_INSPECTION_MAX_PAGES = 10_000
_PDF_INSPECTION_MAX_PAGE_TEXT = 1_000_000
_PDF_INSPECTION_MAX_TEXT = 10_000_000


def _inspect_pdf(path: Path, *, cancelled: Callable[[], bool] | None = None) -> DocumentInspection:
    import pymupdf as fitz
    from opendoc_model import TextFlowProfile, text_flow_profile_to_dict
    from opendoc_model.text_flow import TextFlowFingerprint

    from opendoc_formats.readers.pdf_fields import canonical_field_names

    report = DocumentInspection(path, "pdf")
    counters: Counter[str] = Counter()
    fonts: Counter[str] = Counter()
    resources: dict[int, dict[str, Any]] = {}
    flow = TextFlowFingerprint()
    profile = f"pdf-pymupdf-native-text-v1-{fitz.VersionBind}"

    def finish(reason: str | None = None, *, measured: bool = True) -> DocumentInspection:
        report.metadata["text_flow_profile"] = text_flow_profile_to_dict(
            TextFlowProfile(profile=profile, scope="pdf-native-text-layer-v1",
                            measured=measured, complete=reason is None, reason=reason)
        )
        if measured:
            report.metadata["text_flow"] = flow.to_dict()
        counters["resources"] = len(resources)
        report.metrics = dict(sorted(counters.items()))
        report.resources = list(resources.values())
        report.fonts = dict(fonts.most_common())
        return report

    if path.stat().st_size > _PDF_INSPECTION_MAX_BYTES:
        report.add(IssueSeverity.WARNING, "pdf.inspection-limit", "PDF file exceeds inspection limit", "source")
        return finish("file-limit", measured=False)
    with fitz.open(path) as document:
        if document.needs_pass and not document.authenticate(""):
            counters["encrypted"] = 1
            report.add(IssueSeverity.ERROR, "encryption", "PDF requires a password for structural inspection", "source")
            return finish("password-required", measured=False)
        if document.metadata.get("encryption"):
            report.add(IssueSeverity.WARNING, "encryption", "PDF is encrypted with an empty password", "source")
        counters["pages"] = len(document)
        if len(document) > _PDF_INSPECTION_MAX_PAGES:
            report.add(IssueSeverity.WARNING, "pdf.inspection-limit", "PDF exceeds page limit", "pages")
            return finish("page-limit", measured=False)
        try:
            counters["form_fields"] = len(canonical_field_names(document))
            report.metadata["pdf_field_names_complete"] = True
        except ValueError as error:
            report.metadata["pdf_field_names_complete"] = False
            report.add(IssueSeverity.WARNING, "pdf.field-inventory", str(error), "catalog.AcroForm.Fields")
        report.metadata.update({key: value for key, value in document.metadata.items() if value})
        raw_characters = 0
        for page_index, page in enumerate(document):
            _inspection_checkpoint(cancelled)
            try:
                text = page.get_text("text", sort=False, flags=fitz.TEXTFLAGS_TEXT)
            except RuntimeError as error:
                report.add(IssueSeverity.WARNING, "pdf.text-flow", str(error), f"pages[{page_index}]")
                return finish("backend-extraction-failed")
            if len(text) > _PDF_INSPECTION_MAX_PAGE_TEXT or raw_characters + len(text) > _PDF_INSPECTION_MAX_TEXT:
                report.add(IssueSeverity.WARNING, "pdf.inspection-limit", "Native text exceeds inspection limit",
                           f"pages[{page_index}]")
                return finish("text-limit")
            raw_characters += len(text)
            flow.add(text)
            rectangle = page.rect
            report.pages.append(
                {
                    "index": page_index,
                    "width_pt": rectangle.width,
                    "height_pt": rectangle.height,
                    "rotation": page.rotation,
                }
            )
            page_dict = page.get_text("dict")
            text_blocks = [block for block in page_dict.get("blocks", []) if block.get("type") == 0]
            counters["text_blocks"] += len(text_blocks)
            page_characters = 0
            for block in text_blocks:
                for line in block.get("lines", []):
                    counters["text_lines"] += 1
                    for span in line.get("spans", []):
                        counters["text_runs"] += 1
                        page_characters += len(span.get("text", ""))
                        if span.get("font"):
                            fonts[str(span["font"])] += 1
            counters["characters"] += page_characters
            counters["hyperlinks"] += len(page.get_links())
            drawings = page.get_drawings()
            counters["vector_drawings"] += len(drawings)
            images = page.get_images(full=True)
            counters["image_occurrences"] += len(images)
            for item in images:
                xref = int(item[0])
                if xref not in resources:
                    extracted = document.extract_image(xref)
                    data = extracted.get("image", b"")
                    resources[xref] = {
                        "id": f"xref-{xref}",
                        "kind": "raster_image",
                        "media_type": f"image/{extracted.get('ext', 'unknown')}",
                        "filename": None,
                        "size_bytes": len(data),
                        "sha256": hashlib.sha256(data).hexdigest() if data else None,
                        "embedded": True,
                        "width_px": extracted.get("width"),
                        "height_px": extracted.get("height"),
                    }
            counters["form_widgets"] += len(list(page.widgets() or []))
            if page_characters == 0 and not images and not drawings:
                report.add(
                    IssueSeverity.WARNING,
                    "blank-page",
                    "page has no text, images, or vector drawings",
                    f"pages[{page_index}]",
                )
    return finish()

_HTML_SKIP_TAGS = {"script", "style", "head"}
_LATEX_MATH_ENVS = (
    "equation",
    "equation*",
    "align",
    "align*",
    "gather",
    "gather*",
    "alignat",
    "alignat*",
    "eqnarray",
    "eqnarray*",
    "multline",
    "multline*",
    "flalign",
    "flalign*",
)
_LATEX_PAPER_SIZES = {
    "a3paper": (841.89, 1190.55),
    "a4paper": (595.28, 841.89),
    "a5paper": (419.53, 595.28),
    "letterpaper": (612.0, 792.0),
    "legalpaper": (612.0, 1008.0),
}
_LATEX_TEXT_COMMANDS = re.compile(r"\\(?:textbf|textit|emph|text|mbox|mathrm|mathsf|mathtt|mathcal|underline|url)\{([^{}]*)\}")
_LATEX_REF_COMMANDS = re.compile(r"\\(?:eqref|pageref|cref|vref|label|ref)\{")
_LATEX_CITE_COMMANDS = re.compile(r"\\[a-zA-Z@]*cite[a-zA-Z@]*\{")
_LATEX_HREF_COMMANDS = re.compile(r"\\href\{")
_LATEX_DISPLAY_MATH = re.compile(r"\$\$.*?\$\$|\\\[.*?\\\]", re.DOTALL)
_LATEX_INLINE_MATH = re.compile(r"(?<!\\)\$(?!\$)[^$\n]+(?<!\\)\$")
_LATEX_HEADING_COMMANDS = re.compile(r"\\(?:chapter|(?:sub)*section)\*?\{")
_LATEX_COMMAND_TOKEN = re.compile(r"\\[a-zA-Z@]+\*?")
_LATEX_BEGIN_END = re.compile(r"\\(?:begin|end)\{[a-zA-Z*]+\}")
_LATEX_ESCAPES = {
    r"\%": "%",
    r"\&": "&",
    r"\_": "_",
    r"\#": "#",
    r"\$": "$",
    r"\{": "{",
    r"\}": "}",
    r"\textbackslash": "\\",
    r"\textasciitilde": "~",
    r"\textasciicircum": "^",
    r"\ldots": "…",
    r"\textendash": "–",
    r"\textemdash": "—",
    r"\textquotedbl": '"',
    r"\textquoteleft": "‘",
    r"\textquoteright": "’",
    r"\textbullet": "•",
}


class _HtmlInspectionParser(HTMLParser):
    """Собрать структурные метрики и data-URI ресурсы из HTML."""

    def __init__(self, report: DocumentInspection) -> None:
        super().__init__(convert_charrefs=True)
        self.report = report
        self.counters: Counter[str] = Counter()
        self.fonts: Counter[str] = Counter()
        self.resources: dict[str, dict[str, Any]] = {}
        self._skip_depth = 0
        self._math_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {name: value or "" for name, value in attrs}
        if tag in _HTML_SKIP_TAGS:
            self._skip_depth += 1
        elif tag == "section":
            self.counters["sections"] += 1
        elif tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self.counters["headings"] += 1
        elif tag == "p":
            self.counters["paragraphs"] += 1
        elif tag == "table":
            self.counters["tables"] += 1
        elif tag == "tr":
            self.counters["table_rows"] += 1
        elif tag in {"td", "th"}:
            self.counters["table_cells"] += 1
        elif tag == "img":
            self.counters["images"] += 1
            self._inspect_image(attributes.get("src", ""))
        elif tag == "a":
            href = attributes.get("href")
            if href:
                if href.startswith("#"):
                    self.counters["internal_hyperlinks"] += 1
                else:
                    self.counters["hyperlinks"] += 1
        elif tag == "math":
            self.counters["formulas"] += 1
            self._math_depth += 1
        elif tag in {"ul", "ol"}:
            self.counters["lists"] += 1
        elif tag == "li":
            self.counters["list_items"] += 1
        style = attributes.get("style")
        if style:
            self._extract_fonts(style)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        if tag in _HTML_SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
        elif tag == "math":
            self._math_depth = max(0, self._math_depth - 1)

    def handle_data(self, data: str) -> None:
        if self._skip_depth or self._math_depth or not data.strip():
            return
        self.counters["characters"] += len(data)
        self.counters["text_runs"] += 1

    def _inspect_image(self, source: str) -> None:
        match = re.match(r"data:(image/[a-zA-Z0-9.+-]+);base64,([A-Za-z0-9+/=]+)", source)
        if not match:
            return
        media_type, encoded = match.groups()
        try:
            raw = base64.b64decode(encoded)
        except ValueError:
            return
        index = len(self.resources)
        self.resources[f"img-{index}"] = {
            "id": f"img-{index}",
            "kind": "raster_image",
            "media_type": media_type,
            "filename": None,
            "size_bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "embedded": True,
        }

    def _extract_fonts(self, style: str) -> None:
        for match in re.finditer(r"font-family\s*:\s*([^;}]+)", style):
            family = match.group(1).strip().strip("'\"").split(",")[0].strip()
            if family:
                self.fonts[family] += 1


def _inspect_html(path: Path) -> DocumentInspection:
    """Собрать структурные метрики, ресурсы и шрифты из HTML-файла."""

    report = DocumentInspection(path, "html")
    try:
        raw = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raw = path.read_text(encoding="utf-8", errors="replace")
    parser = _HtmlInspectionParser(report)
    parser.feed(raw)
    report.metrics = dict(sorted(parser.counters.items()))
    report.resources = list(parser.resources.values())
    report.fonts = dict(parser.fonts.most_common())
    if parser.counters["formulas"]:
        report.formula_formats = {"mathml": parser.counters["formulas"]}
    return report


def _inspect_latex(path: Path) -> DocumentInspection:
    """Собрать структурные метрики и геометрию страницы из LaTeX-файла."""

    report = DocumentInspection(path, "latex")
    raw = path.read_text(encoding="utf-8", errors="replace")
    counters: Counter[str] = Counter()
    counters["pages"] = 1
    counters["characters"] = len(_strip_latex_text(raw))
    counters["text_runs"] = len(re.findall(r"\S+", _strip_latex_text(raw)))
    counters["headings"] = len(_LATEX_HEADING_COMMANDS.findall(raw))
    counters["tables"] = len(re.findall(r"\\begin\{tabular", raw))
    counters["images"] = len(re.findall(r"\\includegraphics\*?", raw))
    counters["hyperlinks"] = len(_LATEX_HREF_COMMANDS.findall(raw))
    counters["internal_hyperlinks"] = len(_LATEX_REF_COMMANDS.findall(raw))
    counters["citations"] = len(_LATEX_CITE_COMMANDS.findall(raw))
    counters["formulas"] = _count_latex_formulas(raw)
    counters["list_items"] = len(re.findall(r"\\item", raw))
    counters["paragraphs"] = _count_latex_paragraphs(raw)
    papersize = _latex_paper_size(raw)
    report.metrics = dict(sorted(counters.items()))
    if papersize is not None:
        report.pages = [
            {
                "index": 0,
                "width_pt": papersize[0],
                "height_pt": papersize[1],
            }
        ]
    if counters["formulas"]:
        report.formula_formats = {"latex": counters["formulas"]}
    return report


def _latex_paper_size(raw: str) -> tuple[float, float] | None:
    match = re.search(r"\\documentclass\s*(?:\[[^\]]*\])?\s*\{[^{}]*\}", raw)
    options = match.group(0) if match else ""
    for name, size in _LATEX_PAPER_SIZES.items():
        if name in options:
            return size
    return None


def _count_latex_formulas(raw: str) -> int:
    return (
        len(_LATEX_DISPLAY_MATH.findall(raw))
        + len(_LATEX_INLINE_MATH.findall(raw))
        + sum(raw.count(rf"\begin{{{env}}}") for env in _LATEX_MATH_ENVS)
    )


def _count_latex_paragraphs(raw: str) -> int:
    body = re.search(r"\\begin\{document\}(.*?)\\end\{document\}", raw, re.DOTALL)
    source = body.group(1) if body else raw
    return sum(1 for block in re.split(r"\n\s*\n", source) if re.search(r"\w", _strip_latex_text(block)))


def _strip_latex_text(raw: str) -> str:
    text = re.sub(r"(?<!\\)%.*$", "", raw, flags=re.MULTILINE)
    text = _LATEX_DISPLAY_MATH.sub(" ", text)
    for env in _LATEX_MATH_ENVS:
        text = re.sub(rf"\\begin{{{env}}}.*?\\end{{{env}}}", " ", text, flags=re.DOTALL)
    text = _LATEX_INLINE_MATH.sub(" ", text)
    text = re.sub(r"\\href\{[^{}]*\}\{([^{}]*)\}", r"\1", text)
    text = _LATEX_CITE_COMMANDS.sub(" ", text)
    text = _LATEX_REF_COMMANDS.sub(" ", text)
    text = _LATEX_BEGIN_END.sub(" ", text)
    text = _LATEX_TEXT_COMMANDS.sub(r"\1", text)
    text = _LATEX_COMMAND_TOKEN.sub(" ", text)
    for token, replacement in _LATEX_ESCAPES.items():
        text = text.replace(token, replacement)
    text = text.replace("~", " ").replace("{", " ").replace("}", " ")
    return re.sub(r"\s+", " ", text).strip()


__all__ = [
    "DocumentComparison",
    "DocumentInspection",
    "compare_inspections",
    "inspect_document_model",
    "inspect_path",
]
