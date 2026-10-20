# Навигатор по коду

Создан автоматически из AST. Ссылки тестов показывают связь, а не покрытие.

## src/opendoc_formats/__init__.py

Document format readers and writers built on the OpenDoc model.


Импорты: `api`, `export`, `importlib.metadata`, `support.mapping_composition`, `support.object_mapping`, `support.pdf_mapping_history`, `text_profile`

## src/opendoc_formats/api.py

Format reader registry using the OpenDoc model and validation contract.

- `ImportOptions` — [строка 18](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/api.py#L18)
- `ImportResult` — [строка 48](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/api.py#L48)
- `success(self) -> bool` — [строка 55](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/api.py#L55)
- `assessment_complete(self) -> bool` — [строка 59](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/api.py#L59)
- `lossless(self) -> bool` — [строка 70](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/api.py#L70)
- `AdapterSpec` — [строка 87](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/api.py#L87)
- `AdapterRegistry` — [строка 107](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/api.py#L107)
- `__init__(self) -> None` — [строка 108](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/api.py#L108)
- `register(self, adapter: AdapterSpec) -> None` — [строка 112](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/api.py#L112)
- `adapters(self) -> tuple[AdapterSpec, ...]` — [строка 120](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/api.py#L120)
- `read(self, path: str | Path, *, format_id: str | None=None, options: ImportOptions | None=None) -> ImportResult` — [строка 123](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/api.py#L123)
- `default_registry() -> AdapterRegistry` — [строка 224](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/api.py#L224)
- `read_document(path: str | Path, *, format_id: str | None=None, options: ImportOptions | None=None) -> ImportResult` — [строка 238](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/api.py#L238)

Импорты: `__future__`, `collections.abc`, `dataclasses`, `importlib`, `opendoc_formats.errors`, `opendoc_formats.html_tables`, `opendoc_formats.ooxml.widths`, `opendoc_formats.pdf_outline`, `opendoc_formats.readers.tex_model`, `opendoc_formats.support.backends`, `opendoc_formats.support.document_limits`, `opendoc_formats.text_profile`, `opendoc_model`, `pathlib`, `typing`

Тесты: [test_djvu_text.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/readers/test_djvu_text.py#L1), [test_docx_layout_roundtrip.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/readers/test_docx_layout_roundtrip.py#L1), [test_docx_typed_widths.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/readers/test_docx_typed_widths.py#L1)

## src/opendoc_formats/docx.py

Public immutable DOCX snapshots and transactional native text editing.

- `DocxLimits` — [строка 17](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/docx.py#L17)
- `RunStyle` — [строка 34](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/docx.py#L34)
- `RunSnapshot` — [строка 44](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/docx.py#L44)
- `ParagraphSnapshot` — [строка 52](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/docx.py#L52)
- `in_table(self) -> bool` — [строка 71](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/docx.py#L71)
- `BodyItem` — [строка 76](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/docx.py#L76)
- `CellSnapshot` — [строка 85](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/docx.py#L85)
- `RowSnapshot` — [строка 97](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/docx.py#L97)
- `TableSnapshot` — [строка 110](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/docx.py#L110)
- `PackagePartInfo` — [строка 122](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/docx.py#L122)
- `DocxPackageInfo` — [строка 130](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/docx.py#L130)
- `ReplaceTextSpan` — [строка 138](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/docx.py#L138)
- `SetParagraphText` — [строка 146](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/docx.py#L146)
- `InsertParagraph` — [строка 153](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/docx.py#L153)
- `InsertTableRow` — [строка 160](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/docx.py#L160)
- `SetTableRowText` — [строка 167](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/docx.py#L167)
- `DocxEditResult` — [строка 176](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/docx.py#L176)
- `DocxPackage` — [строка 183](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/docx.py#L183)
- `__init__(self, source: Source, *, limits: DocxLimits=DocxLimits(), allow_macros: bool=False, cancelled: Cancellation | None=None) -> None` — [строка 186](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/docx.py#L186)
- `close(self) -> None` — [строка 211](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/docx.py#L211)
- `closed(self) -> bool` — [строка 215](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/docx.py#L215)
- `paragraphs(self) -> tuple[ParagraphSnapshot, ...]` — [строка 219](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/docx.py#L219)
- `body(self) -> tuple[BodyItem, ...]` — [строка 224](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/docx.py#L224)
- `tables(self) -> tuple[TableSnapshot, ...]` — [строка 229](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/docx.py#L229)
- `info(self) -> DocxPackageInfo` — [строка 234](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/docx.py#L234)
- `to_bytes(self, patches: Sequence[DocxPatch]=()) -> bytes` — [строка 238](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/docx.py#L238)
- `write(self, output: str | Path, patches: Sequence[DocxPatch]=()) -> DocxEditResult` — [строка 242](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/docx.py#L242)

Импорты: `__future__`, `collections.abc`, `dataclasses`, `hashlib`, `opendoc_formats.native.common`, `opendoc_formats.native.docx_package`, `pathlib`, `typing`

Тесты: [test_docx_access.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/native/test_docx_access.py#L1)

## src/opendoc_formats/epub_metadata.py

Finite Dublin Core text metadata profile shared by EPUB readers and writers.

- `read_dc_values(package: ET.Element) -> dict[str, tuple[str, ...]]` — [строка 19](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/epub_metadata.py#L19)
- `export_dc_values(metadata: Mapping[str, Any], defaults: Mapping[str, str], report: ConversionReport) -> dict[str, tuple[str, ...]]` — [строка 29](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/epub_metadata.py#L29)

Импорты: `__future__`, `collections.abc`, `opendoc_model`, `typing`

## src/opendoc_formats/errors.py

Format-specific errors, independent of consumers.

- `FormatError` — [строка 4](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/errors.py#L4)
- `ExtractError` — [строка 8](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/errors.py#L8)
- `ConvertError` — [строка 12](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/errors.py#L12)
- `NativeAccessError` — [строка 16](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/errors.py#L16)
- `BackendUnavailableError` — [строка 22](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/errors.py#L22)
- `InvalidDocumentError` — [строка 28](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/errors.py#L28)
- `EncryptedDocumentError` — [строка 34](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/errors.py#L34)
- `UnsupportedDocumentError` — [строка 40](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/errors.py#L40)
- `ResourceLimitError` — [строка 46](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/errors.py#L46)
- `OperationCancelledError` — [строка 52](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/errors.py#L52)
- `DocumentClosedError` — [строка 58](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/errors.py#L58)
- `PageIndexError` — [строка 64](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/errors.py#L64)
- `PatchConflictError` — [строка 70](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/errors.py#L70)
- `OfficeTimeoutError` — [строка 76](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/errors.py#L76)

Импорты: отсутствуют

Тесты: [test_docx_access.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/native/test_docx_access.py#L1), [test_office_access.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/native/test_office_access.py#L1), [test_package_resources.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/native/test_package_resources.py#L1), [test_pdf_access.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/native/test_pdf_access.py#L1), [test_djvu_text.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/readers/test_djvu_text.py#L1), [test_docx_layout_roundtrip.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/readers/test_docx_layout_roundtrip.py#L1), [test_fix_encoding.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/readers/test_fix_encoding.py#L1), [test_tex_model.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/readers/test_tex_model.py#L1), [test_latex_lists.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_latex_lists.py#L1)

## src/opendoc_formats/export.py

Extensible model export with validation and atomic publication.

- `ExportOptions` — [строка 21](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/export.py#L21)
- `ExporterSpec` — [строка 63](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/export.py#L63)
- `ExporterRegistry` — [строка 86](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/export.py#L86)
- `__init__(self) -> None` — [строка 87](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/export.py#L87)
- `register(self, exporter: ExporterSpec) -> None` — [строка 91](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/export.py#L91)
- `exporters(self) -> tuple[ExporterSpec, ...]` — [строка 99](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/export.py#L99)
- `write(self, document: DocumentModel, path: str | Path, *, format_id: str | None=None, options: ExportOptions | None=None) -> ConversionReport` — [строка 102](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/export.py#L102)
- `default_exporter_registry() -> ExporterRegistry` — [строка 340](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/export.py#L340)
- `write_document(document: DocumentModel, path: str | Path, *, format_id: str | None=None, options: ExportOptions | None=None) -> ConversionReport` — [строка 364](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/export.py#L364)

Импорты: `__future__`, `collections.abc`, `dataclasses`, `importlib`, `opendoc_formats.ooxml.paragraph_flow`, `opendoc_formats.ooxml.paragraph_indent`, `opendoc_formats.support.backends`, `opendoc_formats.support.document_limits`, `opendoc_formats.support.object_mapping`, `opendoc_formats.support.output_validation`, `opendoc_formats.text_profile`, `opendoc_formats.writers.txt_writer`, `opendoc_model`, `pathlib`, `tempfile`, `typing`

Тесты: [test_docx_layout_roundtrip.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/readers/test_docx_layout_roundtrip.py#L1), [test_import_limits.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/test_import_limits.py#L1)

## src/opendoc_formats/fonts/__init__.py

Детерминированное разрешение, подмена и аудит шрифтов.


Импорты: `opendoc_formats.fonts.resolver`

## src/opendoc_formats/fonts/docx_embedding.py

Embed deterministic obfuscated OpenType subsets into DOCX packages.

- `embed_docx_fonts(target: object, document: DocumentModel, report: ConversionReport) -> None` — [строка 18](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/fonts/docx_embedding.py#L18)
- `verify_docx_font_embedding(output: str | Path, report: ConversionReport) -> None` — [строка 101](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/fonts/docx_embedding.py#L101)

Импорты: `__future__`, `docx.opc.constants`, `docx.opc.packuri`, `docx.opc.part`, `docx.oxml`, `docx.oxml.ns`, `lxml`, `opendoc_formats.fonts.embedding`, `opendoc_model.diagnostics`, `opendoc_model.document_model`, `pathlib`, `uuid`

## src/opendoc_formats/fonts/embedding.py

Shared font usage collection and deterministic OpenType subsetting.

- `FontUsage` — [строка 13](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/fonts/embedding.py#L13)
- `collect_font_usages(document: DocumentModel) -> list[FontUsage]` — [строка 23](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/fonts/embedding.py#L23)
- `subset_font(usage: FontUsage) -> bytes` — [строка 69](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/fonts/embedding.py#L69)

Импорты: `__future__`, `dataclasses`, `fontTools`, `fontTools.ttLib`, `io`, `opendoc_model.document_model`, `pathlib`

Тесты: [test_pdf_docx_complex.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_pdf_docx_complex.py#L1)

## src/opendoc_formats/fonts/html_embedding.py

Target-specific embedding of resolved fonts into self-contained HTML.

- `embedded_font_stylesheet(document: DocumentModel, report: ConversionReport, *, target: str='html', subset_fonts: bool=False) -> str` — [строка 16](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/fonts/html_embedding.py#L16)
- `archived_font_stylesheet(document: DocumentModel, workspace: object, report: ConversionReport) -> str` — [строка 77](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/fonts/html_embedding.py#L77)

Импорты: `__future__`, `opendoc_formats.fonts.embedding`, `opendoc_model.diagnostics`, `opendoc_model.document_model`, `pathlib`

## src/opendoc_formats/fonts/resolver.py

Cross-platform font registry and metric-aware deterministic substitutions.

- `FontFace` — [строка 18](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/fonts/resolver.py#L18)
- `normalized_family(self) -> str` — [строка 31](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/fonts/resolver.py#L31)
- `FontResolution` — [строка 36](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/fonts/resolver.py#L36)
- `to_dict(self) -> dict[str, object]` — [строка 46](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/fonts/resolver.py#L46)
- `FontResolutionReport` — [строка 60](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/fonts/resolver.py#L60)
- `substitutions(self) -> list[FontResolution]` — [строка 64](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/fonts/resolver.py#L64)
- `missing_glyphs(self) -> dict[str, tuple[str, ...]]` — [строка 68](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/fonts/resolver.py#L68)
- `to_dict(self) -> dict[str, object]` — [строка 71](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/fonts/resolver.py#L71)
- `FontResolver` — [строка 79](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/fonts/resolver.py#L79)
- `__init__(self, faces: Iterable[FontFace]=()) -> None` — [строка 84](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/fonts/resolver.py#L84)
- `system(cls, search_paths: Iterable[str | Path] | None=None) -> FontResolver` — [строка 88](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/fonts/resolver.py#L88)
- `faces(self) -> tuple[FontFace, ...]` — [строка 93](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/fonts/resolver.py#L93)
- `resolve_style(self, style: TextStyle, text: str='') -> FontResolution` — [строка 96](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/fonts/resolver.py#L96)
- `resolve(self, family: str, text: str='', *, bold: bool=False, italic: bool=False) -> FontResolution` — [строка 99](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/fonts/resolver.py#L99)
- `prepare_document_fonts(document: DocumentModel, resolver: FontResolver | None=None, *, limits: od.DocumentLimits | None=None) -> tuple[DocumentModel, FontResolutionReport]` — [строка 142](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/fonts/resolver.py#L142)

Импорты: `__future__`, `collections.abc`, `dataclasses`, `fontTools.ttLib`, `functools`, `opendoc_model.document_model`, `pathlib`, `typing`

## src/opendoc_formats/fonts/resource_fonts.py

Use document-owned font programs during Word export without shared installs.

- `font_program_names(data: bytes) -> tuple[str, tuple[str, ...]]` — [строка 22](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/fonts/resource_fonts.py#L22)
- `ResourceFontResolver` — [строка 36](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/fonts/resource_fonts.py#L36)
- `__init__(self, embedded: FontResolver, aliases: dict[str, str], system: FontResolver, native_names: dict[str, str], bindings: dict[tuple[str, bool, bool], FontFace], *, strict: bool, resource_faces: dict[str, FontFace] | None=None, ambiguous: set[str] | None=None, report: Any=None, limits: DocumentLimits | None=None) -> None` — [строка 39](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/fonts/resource_fonts.py#L39)
- `resolve_style(self, style: TextStyle, text: str='') -> FontResolution` — [строка 54](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/fonts/resource_fonts.py#L54)
- `resolve(self, family: str, text: str='', *, bold: bool=False, italic: bool=False) -> FontResolution` — [строка 67](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/fonts/resource_fonts.py#L67)
- `document_font_resolver(document: DocumentModel, report: Any, *, limits: DocumentLimits | None=None) -> Iterator[FontResolver]` — [строка 83](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/fonts/resource_fonts.py#L83)

Импорты: `__future__`, `contextlib`, `dataclasses`, `fontTools.ttLib`, `io`, `opendoc_formats.fonts.resolver`, `opendoc_formats.support.artifacts`, `opendoc_model`, `typing`

## src/opendoc_formats/fonts/word_metrics.py

OpenType baseline metrics used by the fixed-layout Word writer.

- `word_line_ascent(style: TextStyle) -> float | None` — [строка 23](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/fonts/word_metrics.py#L23)
- `word_line_descent(style: TextStyle) -> float | None` — [строка 31](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/fonts/word_metrics.py#L31)

Импорты: `__future__`, `fontTools.ttLib`, `functools`, `opendoc_model`

## src/opendoc_formats/html_tables.py

Bridge explicit HTML table declarations to the common model contract.

- `import_table_semantics(table: Table, *, identifier: Callable[[], str], resources: dict, styles: dict, ambiguous_ids: frozenset[str]=frozenset()) -> str | None` — [строка 29](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/html_tables.py#L29)
- `migrate_html_tables(document: DocumentModel, *, limits: DocumentLimits | None=None) -> None` — [строка 101](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/html_tables.py#L101)
- `import_caption_semantics(table: Table, captions: list, *, identifier: Callable[[], str], resources: dict, styles: dict, ambiguous_ids: frozenset[str]=frozenset()) -> str | None` — [строка 196](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/html_tables.py#L196)

Импорты: `__future__`, `collections`, `collections.abc`, `dataclasses`, `opendoc_model`, `typing`

## src/opendoc_formats/native/__init__.py

Internal primitives shared by backend-independent native document APIs.


Импорты: отсутствуют

## src/opendoc_formats/native/common.py

Bounded inputs, cooperative cancellation and atomic publication.

- `check_cancel(cancelled: Cancellation | None) -> None` — [строка 19](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/native/common.py#L19)
- `positive_int(value: int, name: str, *, zero: bool=False) -> None` — [строка 24](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/native/common.py#L24)
- `positive_number(value: float, name: str) -> float` — [строка 29](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/native/common.py#L29)
- `backend(module: str, extra: str) -> ModuleType` — [строка 35](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/native/common.py#L35)
- `read_source(source: Source, maximum: int, cancelled: Cancellation | None) -> bytes` — [строка 42](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/native/common.py#L42)
- `publish(data: bytes, output: str | Path, maximum: int, cancelled: Cancellation | None) -> Path` — [строка 60](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/native/common.py#L60)

Импорты: `__future__`, `collections.abc`, `opendoc_formats.errors`, `pathlib`, `types`, `uuid`

## src/opendoc_formats/native/docx_package.py

Private ZIP/XML implementation of immutable DOCX snapshots and patches.

- `parse_xml(data: bytes, engine: Any) -> Any` — [строка 63](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/native/docx_package.py#L63)
- `NativePackage` — [строка 155](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/native/docx_package.py#L155)
- `__init__(self, source: Source, limits: DocxLimits, allow_macros: bool, cancelled: Cancellation | None) -> None` — [строка 156](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/native/docx_package.py#L156)
- `check_open(self) -> None` — [строка 170](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/native/docx_package.py#L170)
- `close(self) -> None` — [строка 175](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/native/docx_package.py#L175)
- `edit(self, patches: Sequence[DocxPatch]) -> tuple[bytes, tuple[str, ...]]` — [строка 584](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/native/docx_package.py#L584)

Импорты: `__future__`, `collections`, `collections.abc`, `opendoc_formats.docx`, `opendoc_formats.errors`, `opendoc_formats.native.common`, `pathlib`, `typing`, `urllib.parse`

## src/opendoc_formats/office.py

Managed LibreOffice conversion into validated PDF with atomic publication.

- `OfficeLimits` — [строка 41](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/office.py#L41)
- `OfficeConversionResult` — [строка 52](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/office.py#L52)
- `find_libreoffice() -> Path | None` — [строка 59](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/office.py#L59)
- `convert_office_to_pdf(source: str | Path, output: str | Path, *, executable: str | Path | None=None, timeout: float=180, limits: OfficeLimits=OfficeLimits(), cancelled: Cancellation | None=None) -> OfficeConversionResult` — [строка 88](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/office.py#L88)

Импорты: `__future__`, `dataclasses`, `hashlib`, `opendoc_formats.errors`, `opendoc_formats.native.common`, `opendoc_formats.pdf`, `pathlib`

Тесты: [test_office_access.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/native/test_office_access.py#L1)

## src/opendoc_formats/ooxml/__init__.py

Shared OOXML package, relationship, namespace, and unit helpers.


Импорты: `opendoc_formats.ooxml.package`

## src/opendoc_formats/ooxml/borders.py

Direct OOXML borders through the common model, with inert native extras.

- `native_only(node: Any) -> bool` — [строка 29](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/ooxml/borders.py#L29)
- `import_borders(source: Table | TableCell, owner: Any) -> None` — [строка 60](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/ooxml/borders.py#L60)
- `export_borders(source: Table | TableCell, owner: Any, report: Any, location: str) -> None` — [строка 135](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/ooxml/borders.py#L135)

Импорты: `__future__`, `collections`, `dataclasses`, `docx.oxml`, `lxml`, `opendoc_model`, `typing`

## src/opendoc_formats/ooxml/color.py

Shared OOXML DrawingML color resolution.

- `resolve_drawingml_color(node: Any, theme_colors: Mapping[str, str]) -> tuple[ColorValue | None, dict[str, Any]]` — [строка 20](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/ooxml/color.py#L20)

Импорты: `__future__`, `collections.abc`, `opendoc_model.color`, `typing`

Тесты: [test_ooxml_color.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/support/test_ooxml_color.py#L1)

## src/opendoc_formats/ooxml/group_geometry.py

Finite editable DrawingML rectangle groups, using official Model scene types.

- `axis_transform(value: AffineTransform) -> tuple[float, float, float, float]` — [строка 13](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/ooxml/group_geometry.py#L13)
- `paint_style(path: VectorPath) -> tuple[str, float]` — [строка 19](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/ooxml/group_geometry.py#L19)
- `rectangle(path: VectorPath) -> Box` — [строка 34](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/ooxml/group_geometry.py#L34)
- `scene_profile(scene: VectorScene) -> dict[str, Box]` — [строка 50](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/ooxml/group_geometry.py#L50)
- `preview_svg(scene: VectorScene) -> bytes` — [строка 106](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/ooxml/group_geometry.py#L106)

Импорты: `__future__`, `opendoc_model`, `xml.etree`

## src/opendoc_formats/ooxml/headings.py

Map native Word outline levels to OpenDoc's explicit heading contract.

- `import_heading(native: Any, paragraph: Paragraph) -> None` — [строка 18](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/ooxml/headings.py#L18)
- `export_heading(paragraph: Paragraph, native: Any) -> None` — [строка 52](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/ooxml/headings.py#L52)
- `retain_derived_styles(part: Any, graph: PackageGraph) -> PackageGraph` — [строка 91](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/ooxml/headings.py#L91)

Импорты: `__future__`, `copy`, `dataclasses`, `docx.enum.style`, `docx.oxml`, `docx.oxml.ns`, `lxml`, `opendoc_formats.ooxml.package`, `opendoc_model`, `typing`

## src/opendoc_formats/ooxml/layout.py

Direct Word layout declarations using existing versioned property bags.

- `native_layout_supported(node: Any) -> bool` — [строка 79](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/ooxml/layout.py#L79)
- `import_layout(properties: MutableMapping[str, Any], owner: Any, *, table: bool=False) -> None` — [строка 89](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/ooxml/layout.py#L89)
- `import_common_layout(source: Table | Paragraph) -> None` — [строка 108](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/ooxml/layout.py#L108)
- `inherited_tab_positions(source: Paragraph, document: DocumentModel) -> tuple[float, ...]` — [строка 137](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/ooxml/layout.py#L137)
- `export_layout(properties: Mapping[str, Any], owner: Any, report: Any, location: str, *, table: bool=False, inherited: tuple[float, ...]=()) -> None` — [строка 208](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/ooxml/layout.py#L208)
- `retain_layout_styles(graph: PackageGraph, styles: Mapping[str, TextStyle], report: Any, *, limits: DocumentLimits | None=None) -> PackageGraph` — [строка 267](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/ooxml/layout.py#L267)

Импорты: `__future__`, `collections.abc`, `dataclasses`, `decimal`, `docx.oxml`, `lxml`, `opendoc_formats.ooxml.package`, `opendoc_formats.ooxml.paragraph_flow`, `opendoc_formats.ooxml.paragraph_indent`, `opendoc_formats.ooxml.spacing`, `opendoc_formats.ooxml.word_color`, `opendoc_model`, `typing`

## src/opendoc_formats/ooxml/merged_cell_borders.py

Map whole merged-cell borders onto Word's physical continuation cells.

- `export_merge_borders(target: Any, placements: list, report: Any, location: str) -> None` — [строка 14](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/ooxml/merged_cell_borders.py#L14)
- `import_merge_borders(origin: TableCell, owner: Any) -> None` — [строка 47](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/ooxml/merged_cell_borders.py#L47)

Импорты: `__future__`, `dataclasses`, `docx.oxml.ns`, `lxml`, `opendoc_formats.ooxml.borders`, `opendoc_formats.ooxml.widths`, `opendoc_model`, `typing`

## src/opendoc_formats/ooxml/package.py

Reusable helpers for importing and restoring OOXML package topology.

- `load_package_graph(root_part: Any, *, format_name: str, supported_relationships: Collection[str], recursive_relationships: Collection[str]=(), include: RelationshipFilter | None=None) -> PackageGraph | None` — [строка 46](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/ooxml/package.py#L46)
- `package_part_for_relationship(graph: PackageGraph | None, relationship_type: str) -> PackagePart | None` — [строка 77](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/ooxml/package.py#L77)
- `restore_package_graph(root_part: Any, graph: PackageGraph, *, protected_roots: Collection[Any]=(), source_parts: Mapping[str, Any] | None=None) -> None` — [строка 83](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/ooxml/package.py#L83)

Импорты: `__future__`, `collections.abc`, `docx.opc.packuri`, `docx.opc.part`, `opendoc_model.document_model`, `opendoc_model.units`, `pathlib`, `pptx.opc.packuri`, `pptx.opc.part`, `typing`

Тесты: [test_ooxml_package.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/support/test_ooxml_package.py#L1)

## src/opendoc_formats/ooxml/paragraph_flow.py

Finite direct paragraph spacing and pagination, with live style inheritance.

- `import_flow(properties: MutableMapping[str, Any], owner: Any) -> None` — [строка 24](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/ooxml/paragraph_flow.py#L24)
- `unresolved_flow(properties: Mapping[str, Any], key: str) -> bool` — [строка 60](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/ooxml/paragraph_flow.py#L60)
- `native_flow_supported(node: Any) -> bool` — [строка 67](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/ooxml/paragraph_flow.py#L67)
- `flow_needs_patch(properties: Mapping[str, Any]) -> bool` — [строка 76](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/ooxml/paragraph_flow.py#L76)
- `export_flow(properties: Mapping[str, Any], owner: Any, report: Any, location: str) -> None` — [строка 85](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/ooxml/paragraph_flow.py#L85)
- `effective_flow(document: DocumentModel, paragraph: Paragraph, key: str) -> Any` — [строка 128](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/ooxml/paragraph_flow.py#L128)

Импорты: `__future__`, `collections.abc`, `opendoc_model`, `typing`

## src/opendoc_formats/ooxml/paragraph_frame.py

Finite page-anchored editable paragraph frames for fixed-layout conversion.

- `import_frame(source: Any, target: Paragraph) -> None` — [строка 15](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/ooxml/paragraph_frame.py#L15)
- `export_frame(source: Paragraph, target: Any, report: Any, location: str, *, pdf: bool=False) -> None` — [строка 34](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/ooxml/paragraph_frame.py#L34)

Импорты: `__future__`, `docx.oxml`, `opendoc_formats.fonts.word_metrics`, `opendoc_model`, `typing`

## src/opendoc_formats/ooxml/paragraph_indent.py

Finite direct Word paragraph indents and live native inheritance.

- `import_indents(properties: MutableMapping[str, Any], owner: Any) -> None` — [строка 35](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/ooxml/paragraph_indent.py#L35)
- `native_indents_supported(node: Any) -> bool` — [строка 59](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/ooxml/paragraph_indent.py#L59)
- `indents_need_patch(properties: Mapping[str, Any]) -> bool` — [строка 65](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/ooxml/paragraph_indent.py#L65)
- `unresolved_indent(properties: Mapping[str, Any], key: str) -> bool` — [строка 76](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/ooxml/paragraph_indent.py#L76)
- `export_indents(properties: Mapping[str, Any], owner: Any, report: Any, location: str) -> None` — [строка 82](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/ooxml/paragraph_indent.py#L82)
- `effective_indent(document: DocumentModel, paragraph: Paragraph, key: str) -> Any` — [строка 119](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/ooxml/paragraph_indent.py#L119)

Импорты: `__future__`, `collections.abc`, `docx.oxml`, `opendoc_model`, `typing`

Тесты: [test_docx_paragraph_indents.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/readers/test_docx_paragraph_indents.py#L1)

## src/opendoc_formats/ooxml/positioned_text.py

Editable page-positioned Word text boxes on the native drawing layer.

- `create_positioned_text(container: Any, source: Paragraph, report: Any, location: str, *, pdf: bool) -> Any` — [строка 45](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/ooxml/positioned_text.py#L45)
- `positioned_text_source(paragraph: Any) -> tuple[Any, Box, int] | None` — [строка 93](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/ooxml/positioned_text.py#L93)
- `native_positioned_content_supported(node: Any) -> bool` — [строка 171](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/ooxml/positioned_text.py#L171)

Импорты: `__future__`, `docx.oxml`, `docx.text.paragraph`, `opendoc_formats.fonts.word_metrics`, `opendoc_formats.ooxml.package`, `opendoc_model`, `opendoc_model.units`, `types`, `typing`

Тесты: [test_pdf_model_docx.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_pdf_model_docx.py#L1)

## src/opendoc_formats/ooxml/run_position.py

Direct native Word baseline shifts in half-point units.

- `import_run_position(run: Any, properties: Any) -> None` — [строка 13](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/ooxml/run_position.py#L13)
- `native_position(properties: Mapping[str, Any]) -> int | None` — [строка 25](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/ooxml/run_position.py#L25)
- `export_run_position(properties: Mapping[str, Any], owner: Any) -> None` — [строка 39](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/ooxml/run_position.py#L39)

Импорты: `__future__`, `collections.abc`, `docx.oxml`, `typing`

## src/opendoc_formats/ooxml/spacing.py

Finite Word line-spacing declarations, separate from their numeric units.

- `common_spacing(properties: Mapping[str, Any], limits: DocumentLimits | None=None) -> LineSpacing | None` — [строка 50](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/ooxml/spacing.py#L50)
- `prepare_legacy_spacing_view(owner: Paragraph | TextStyle, limits: DocumentLimits | None=None) -> None` — [строка 63](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/ooxml/spacing.py#L63)
- `default_spacing_owner(root: Any) -> Any` — [строка 81](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/ooxml/spacing.py#L81)
- `native_spacing_supported(node: Any) -> bool` — [строка 106](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/ooxml/spacing.py#L106)
- `spacing_needs_patch(properties: Mapping[str, Any]) -> bool` — [строка 116](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/ooxml/spacing.py#L116)
- `import_spacing(properties: MutableMapping[str, Any], formats: list[Any]) -> None` — [строка 120](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/ooxml/spacing.py#L120)
- `import_spacing_nodes(properties: MutableMapping[str, Any], owners: list[Any]) -> None` — [строка 124](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/ooxml/spacing.py#L124)
- `export_spacing(properties: Mapping[str, Any], owner: Any, report: Any, location: str, *, limits: DocumentLimits | None=None) -> None` — [строка 155](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/ooxml/spacing.py#L155)

Импорты: `__future__`, `collections.abc`, `copy`, `docx.oxml`, `lxml`, `opendoc_model`, `typing`

## src/opendoc_formats/ooxml/table_grid.py

Bounded projection of sparse Model spans onto a native Word table grid.

- `native_grid(table: Table, *, limits: DocumentLimits | None=None) -> tuple[int, list[tuple[int, int, TableCell]]]` — [строка 10](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/ooxml/table_grid.py#L10)

Импорты: `__future__`, `bisect`, `opendoc_model`

## src/opendoc_formats/ooxml/table_position.py

Finite page-relative Word table placement and measured native row heights.

- `export_table_position(source: Table, target: Any, report: Any, location: str) -> None` — [строка 20](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/ooxml/table_position.py#L20)
- `import_table_position(source: Any, target: Table) -> None` — [строка 46](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/ooxml/table_position.py#L46)

Импорты: `__future__`, `docx.oxml`, `opendoc_model`, `typing`

## src/opendoc_formats/ooxml/widths.py

Bridge native preferred widths to the shared model without layout guesses.

- `native_width(value: object, *, cell: bool) -> WidthMeasure | None` — [строка 14](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/ooxml/widths.py#L14)
- `import_width(source: Table | TableCell) -> None` — [строка 58](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/ooxml/widths.py#L58)
- `export_width(source: Table | TableCell, owner: Any, tag: str) -> None` — [строка 72](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/ooxml/widths.py#L72)

Импорты: `__future__`, `decimal`, `docx.oxml`, `docx.oxml.ns`, `opendoc_formats.errors`, `opendoc_model`, `typing`

## src/opendoc_formats/ooxml/word_color.py

Own direct Word color declarations without flattening the style cascade.

- `color_record(style: TextStyle) -> Any` — [строка 11](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/ooxml/word_color.py#L11)
- `color_needs_patch(style: TextStyle) -> bool` — [строка 15](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/ooxml/word_color.py#L15)
- `default_color_owner(root: Any) -> Any` — [строка 20](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/ooxml/word_color.py#L20)
- `apply_color(owner: Any, style: TextStyle) -> None` — [строка 34](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/ooxml/word_color.py#L34)

Импорты: `__future__`, `docx.oxml`, `docx.oxml.ns`, `opendoc_model.color`, `opendoc_model.document_model`, `typing`

Тесты: [test_docx_color_spacing.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/readers/test_docx_color_spacing.py#L1)

## src/opendoc_formats/package_resources.py

Attach explicitly selected native DOCX resources to the official OpenDoc package graph.

- `assemble_docx_package_resources(document: DocumentModel, resource_roles: Mapping[str, DocxResourceRole], *, consume_resources: bool=False, max_bytes: int=128 * 1024 * 1024, cancelled: Cancellation | None=None) -> DocumentModel` — [строка 47](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/package_resources.py#L47)

Импорты: `__future__`, `collections.abc`, `opendoc_formats.errors`, `opendoc_formats.native.common`, `opendoc_model`, `pathlib`, `typing`

Тесты: [test_package_resources.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/native/test_package_resources.py#L1)

## src/opendoc_formats/pdf.py

Public, bounded PDF page access without exposing the optional rendering engine.

- `PdfLimits` — [строка 22](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/pdf.py#L22)
- `PdfPageInfo` — [строка 38](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/pdf.py#L38)
- `RenderedPage` — [строка 47](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/pdf.py#L47)
- `PdfDocument` — [строка 55](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/pdf.py#L55)
- `__init__(self, source: Source, *, limits: PdfLimits=PdfLimits(), cancelled: Cancellation | None=None) -> None` — [строка 58](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/pdf.py#L58)
- `close(self) -> None` — [строка 98](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/pdf.py#L98)
- `closed(self) -> bool` — [строка 106](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/pdf.py#L106)
- `page_count(self) -> int` — [строка 115](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/pdf.py#L115)
- `page_info(self, index: int) -> PdfPageInfo` — [строка 130](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/pdf.py#L130)
- `render_page(self, index: int, *, dpi: float | None=None, scale: float | None=None, max_dimension: int | None=None, rotation: float=0) -> RenderedPage` — [строка 142](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/pdf.py#L142)

Импорты: `__future__`, `collections`, `dataclasses`, `opendoc_formats.errors`, `opendoc_formats.native.common`, `typing`

Тесты: [test_format_audit.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/native/test_format_audit.py#L1), [test_office_access.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/native/test_office_access.py#L1), [test_pdf_access.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/native/test_pdf_access.py#L1)

## src/opendoc_formats/pdf_graphics.py

Validate adapter-owned native PDF paint evidence before a target projection.

- `finite_number(value: Any) -> float` — [строка 9](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/pdf_graphics.py#L9)
- `paint_clips(evidence: dict, sequence: int, kinds: set[str], *, compositing: bool=False) -> tuple[dict, list[dict]]` — [строка 15](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/pdf_graphics.py#L15)
- `rectangle_points(clip: dict) -> list[tuple[float, float]] | None` — [строка 75](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/pdf_graphics.py#L75)
- `axis_rectangle(points: list[tuple[float, float]], *, tolerance: float=0.0001) -> list[float] | None` — [строка 84](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/pdf_graphics.py#L84)
- `contains(bounds: list[float], inner: list[float]) -> bool` — [строка 103](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/pdf_graphics.py#L103)

Импорты: `__future__`, `typing`

## src/opendoc_formats/pdf_outline.py

Bridge inert native PDF outlines to the shared Model contract.

- `import_pdf_outline(document: DocumentModel, *, pdf: Any=None, source: str='', limits: DocumentLimits | None=None) -> None` — [строка 22](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/pdf_outline.py#L22)

Импорты: `__future__`, `dataclasses`, `opendoc_formats.pdf_page_geometry`, `opendoc_model`, `typing`

## src/opendoc_formats/pdf_page_geometry.py

Native PDF regions in the shared top-down source coordinate contract.

- `native_xyz_destination(pdf: Any, xref: int) -> tuple[int, float | None, float | None, float | None] | None` — [строка 15](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/pdf_page_geometry.py#L15)
- `read_page_geometry(page: Any, identifier: str) -> DocumentPage` — [строка 28](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/pdf_page_geometry.py#L28)
- `apply_page_geometry(page: Any, geometry: PageGeometry, source_origin: tuple[float, float]) -> tuple[float, float]` — [строка 51](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/pdf_page_geometry.py#L51)
- `translate_generated_links(pdf: Any, placements: dict[int, tuple[float, float]], links: dict[int, list[int]]) -> None` — [строка 80](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/pdf_page_geometry.py#L80)

Импорты: `__future__`, `opendoc_model`, `typing`

## src/opendoc_formats/readers/__init__.py

Optional backends are imported only when selected.


Импорты: отсутствуют

## src/opendoc_formats/readers/_djvu_text.py

Bounded external DjVu text extraction, using only the standard library.

- `extract_djvu_text(path: str | Path, *, timeout: float, max_output_bytes: int, cancelled: Callable[[], bool] | None) -> Text` — [строка 17](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/_djvu_text.py#L17)

Импорты: `__future__`, `collections.abc`, `opendoc_formats.errors`, `opendoc_formats.types`, `pathlib`, `typing`

## src/opendoc_formats/readers/_txt_model.py

Plain-text input without application types or optional dependencies.

- `read_txt_model(path: str | Path, *, profile: TextProfile | None=None) -> DocumentModel` — [строка 12](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/_txt_model.py#L12)

Импорты: `opendoc_formats.text_profile`, `opendoc_model`, `pathlib`

## src/opendoc_formats/readers/docx.py

DOCX readers for extracted text and editable OpenDoc documents.

- `read_docx(path: Union[str, Path], *, include_tables: bool=True) -> Text` — [строка 41](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/docx.py#L41)
- `read_docx_model(path: Union[str, Path], *, mode: ConversionMode=ConversionMode.BALANCED, limits: DocumentLimits | None=None) -> DocumentModel` — [строка 75](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/docx.py#L75)

Импорты: `__future__`, `collections.abc`, `docx`, `docx.oxml.ns`, `docx.oxml.table`, `docx.oxml.text.paragraph`, `docx.table`, `docx.text.paragraph`, `lxml`, `opendoc_formats.ooxml.package`, `opendoc_formats.readers.docx_diagnostics`, `opendoc_formats.readers.docx_features`, `opendoc_formats.readers.docx_fonts`, `opendoc_formats.readers.docx_groups`, `opendoc_formats.readers.docx_section`, `opendoc_formats.readers.docx_style`, `opendoc_formats.readers.docx_table`, `opendoc_formats.readers.docx_text`, `opendoc_formats.support.io`, `opendoc_formats.types`, `opendoc_model`, `opendoc_model.document_model`, `opendoc_model.units`, `pathlib`, `typing`

Тесты: [test_format_audit.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/native/test_format_audit.py#L1), [test_docx_layout_roundtrip.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/readers/test_docx_layout_roundtrip.py#L1), [test_docx_model.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/readers/test_docx_model.py#L1), [test_docx_typed_widths.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/readers/test_docx_typed_widths.py#L1), [test_full_contract.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/test_full_contract.py#L1), [test_docx_writer.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_docx_writer.py#L1), [test_html_normalize.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_html_normalize.py#L1)

## src/opendoc_formats/readers/docx_diagnostics.py

Evidence-based partial preservation assessment of advanced DOCX objects.

- `attach_docx_diagnostics(document: Any, model: DocumentModel, source: Path, *, limits: DocumentLimits | None=None) -> None` — [строка 113](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/docx_diagnostics.py#L113)

Импорты: `__future__`, `collections`, `dataclasses`, `lxml`, `opendoc_formats.ooxml.borders`, `opendoc_formats.ooxml.layout`, `opendoc_formats.ooxml.paragraph_flow`, `opendoc_formats.ooxml.paragraph_indent`, `opendoc_formats.ooxml.positioned_text`, `opendoc_formats.ooxml.spacing`, `opendoc_formats.readers.docx_features`, `opendoc_model`, `pathlib`, `typing`

## src/opendoc_formats/readers/docx_drawing.py

DOCX drawing importer for raster/vector resources and anchor geometry.

- `read_run_images(run: Any, model: DocumentModel) -> list[Image]` — [строка 25](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/docx_drawing.py#L25)
- `read_run_vml_colors(run: Any) -> tuple[list[dict[str, Any]], list[str]]` — [строка 80](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/docx_drawing.py#L80)

Импорты: `__future__`, `docx.oxml.ns`, `lxml`, `opendoc_formats.ooxml.color`, `opendoc_formats.readers.docx_groups`, `opendoc_formats.readers.docx_style`, `opendoc_formats.readers.svg_color`, `opendoc_model.document_model`, `opendoc_model.units`, `pathlib`, `typing`

## src/opendoc_formats/readers/docx_features.py

Inventory advanced DOCX features and their preservation level.

- `inspect_docx_features(document: Any) -> dict[str, Any]` — [строка 25](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/docx_features.py#L25)

Импорты: `__future__`, `collections`, `lxml`, `typing`

## src/opendoc_formats/readers/docx_fonts.py

Decode document-owned Word font programs into bounded Model resources.

- `read_embedded_fonts(document: object, *, limits: DocumentLimits | None=None) -> dict[str, Resource]` — [строка 13](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/docx_fonts.py#L13)
- `attach_font_references(model: DocumentModel, *, limits: DocumentLimits | None=None) -> None` — [строка 50](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/docx_fonts.py#L50)

Импорты: `__future__`, `docx.opc.constants`, `lxml`, `opendoc_formats.fonts.docx_embedding`, `opendoc_model`, `uuid`

## src/opendoc_formats/readers/docx_groups.py

Parse native Word groups into editable official vector paths and groups.

- `stage_groups(run: Any, model: DocumentModel) -> list[Image]` — [строка 43](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/docx_groups.py#L43)
- `attach_groups(model: DocumentModel, *, limits: DocumentLimits | None) -> None` — [строка 78](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/docx_groups.py#L78)
- `parse_group(drawing: Any, identifier: str, node_id: str, *, limits: DocumentLimits | None) -> VectorScene` — [строка 92](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/docx_groups.py#L92)

Импорты: `__future__`, `dataclasses`, `lxml`, `opendoc_formats.ooxml.group_geometry`, `opendoc_formats.readers.docx_drawing`, `opendoc_model`, `typing`

## src/opendoc_formats/readers/docx_notes.py

Чтение ссылок на сноски из текстовых runs DOCX.

- `append_note_references(content: list[Any], run: Any, style: TextStyle) -> None` — [строка 10](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/docx_notes.py#L10)

Импорты: `__future__`, `docx.oxml.ns`, `opendoc_model.document_model`, `typing`

## src/opendoc_formats/readers/docx_section.py

DOCX section importer for page geometry and running content.

- `read_section(source: Any, blocks: list[Block], model: DocumentModel, section_index: int, read_blocks: BlockReader, *, odd_and_even_pages: bool) -> Section` — [строка 13](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/docx_section.py#L13)

Импорты: `__future__`, `collections.abc`, `opendoc_model.document_model`, `typing`

## src/opendoc_formats/readers/docx_style.py

DOCX style resolver for inheritance, themes, defaults, and numbering.

- `read_document_styles(document: Any, model: DocumentModel | None=None) -> dict[str, TextStyle]` — [строка 14](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/docx_style.py#L14)
- `read_document_defaults(document: Any, model: DocumentModel) -> TextStyle | None` — [строка 35](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/docx_style.py#L35)
- `read_run_style(run: Any, paragraph: Any, model: DocumentModel | None=None) -> TextStyle` — [строка 87](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/docx_style.py#L87)
- `read_paragraph_properties(paragraph: Any) -> dict[str, Any]` — [строка 133](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/docx_style.py#L133)
- `document_theme_colors(model: DocumentModel) -> dict[str, str]` — [строка 177](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/docx_style.py#L177)

Импорты: `__future__`, `docx.enum.style`, `docx.oxml.ns`, `lxml`, `opendoc_formats.ooxml.layout`, `opendoc_formats.ooxml.package`, `opendoc_formats.ooxml.paragraph_flow`, `opendoc_formats.ooxml.paragraph_indent`, `opendoc_formats.ooxml.spacing`, `opendoc_model.color`, `opendoc_model.document_model`, `typing`

## src/opendoc_formats/readers/docx_table.py

DOCX table importer for spans, geometry, fills, margins, and styles.

- `read_table(table: Any, model: DocumentModel, read_blocks: BlockReader) -> Table` — [строка 17](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/docx_table.py#L17)

Импорты: `__future__`, `collections.abc`, `docx.oxml.ns`, `docx.table`, `lxml`, `opendoc_formats.ooxml.borders`, `opendoc_formats.ooxml.layout`, `opendoc_formats.ooxml.merged_cell_borders`, `opendoc_formats.ooxml.table_position`, `opendoc_formats.ooxml.widths`, `opendoc_model.document_model`, `typing`

## src/opendoc_formats/readers/docx_text.py

Чтение абзацев и строчного содержимого DOCX.

- `read_paragraph(paragraph: Any, model: DocumentModel) -> Paragraph` — [строка 15](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/docx_text.py#L15)
- `read_block_ooxml(element: Any) -> Paragraph` — [строка 113](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/docx_text.py#L113)

Импорты: `__future__`, `docx.oxml.ns`, `docx.text.hyperlink`, `docx.text.run`, `lxml`, `opendoc_formats.ooxml.headings`, `opendoc_formats.ooxml.layout`, `opendoc_formats.ooxml.paragraph_frame`, `opendoc_formats.ooxml.positioned_text`, `opendoc_formats.ooxml.run_position`, `opendoc_formats.readers.docx_drawing`, `opendoc_formats.readers.docx_notes`, `opendoc_formats.readers.docx_style`, `opendoc_model.document_model`, `typing`

## src/opendoc_formats/readers/epub.py

EPUB → Text.

- `read_epub(path: Union[str, Path], *, backend: str='native') -> Text` — [строка 16](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/epub.py#L16)
- `read_epub_model(path: Union[str, Path], *, backend: str='native', include_nonlinear: bool=False) -> od.DocumentModel` — [строка 66](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/epub.py#L66)

Импорты: `__future__`, `bs4`, `opendoc_formats.readers.epub_model`, `opendoc_formats.readers.epub_package`, `opendoc_formats.types`, `pathlib`, `typing`

Тесты: [test_epub_model.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/readers/test_epub_model.py#L1)

## src/opendoc_formats/readers/epub_diagnostics.py

Located, partial EPUB preservation assessment using the OpenDoc contract.

- `EpubDiagnostics` — [строка 23](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/epub_diagnostics.py#L23)
- `__init__(self, source: Path, root_directory: str='', resources: dict[str, Resource] | None=None) -> None` — [строка 24](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/epub_diagnostics.py#L24)
- `lost(self, feature: str, reason: str, message: str, part: str, node: Any=None) -> None` — [строка 30](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/epub_diagnostics.py#L30)
- `opaque(self, feature: str, reason: str, message: str, part: str, resource_id: str, node: Any=None) -> None` — [строка 33](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/epub_diagnostics.py#L33)
- `attach(self, document: DocumentModel, *, limits: DocumentLimits | None=None) -> None` — [строка 65](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/epub_diagnostics.py#L65)
- `chapter(self, body: Any, part: str, blocks: set[str]) -> None` — [строка 76](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/epub_diagnostics.py#L76)

Импорты: `__future__`, `opendoc_model`, `pathlib`, `typing`

## src/opendoc_formats/readers/epub_model.py

Rich EPUB spine importer with links, media, and a small deterministic CSS cascade.

- `read_epub_model(path: str | Path, *, backend: str='native', include_nonlinear: bool=False, limits: od.DocumentLimits | None=None) -> DocumentModel` — [строка 42](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/epub_model.py#L42)

Импорты: `__future__`, `bs4`, `collections.abc`, `opendoc_formats.readers.epub_diagnostics`, `opendoc_formats.readers.epub_package`, `opendoc_formats.readers.html_resources`, `opendoc_model.document_model`, `pathlib`, `typing`, `urllib.parse`

Тесты: [test_source_coverage.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/test_source_coverage.py#L1)

## src/opendoc_formats/readers/epub_package.py

Original, bounded EPUB container reader; no network or XML entity expansion.

- `EpubItem` — [строка 25](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/epub_package.py#L25)
- `EpubPackage` — [строка 34](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/epub_package.py#L34)
- `read_epub_package(path: str | Path) -> EpubPackage` — [строка 100](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/epub_package.py#L100)

Импорты: `__future__`, `dataclasses`, `opendoc_formats.epub_metadata`, `opendoc_formats.support.io`, `pathlib`, `urllib.parse`

Тесты: [test_epub_package.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/readers/test_epub_package.py#L1), [test_epub_writer.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_epub_writer.py#L1)

## src/opendoc_formats/readers/fix_encoding.py

- `fix_encoding(file_path: str | Path, output_path: str | Path | None=None) -> str` — [строка 19](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/fix_encoding.py#L19)

Импорты: `opendoc_formats.errors`, `opendoc_formats.support.io`, `pathlib`

Тесты: [test_fix_encoding.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/readers/test_fix_encoding.py#L1), [test_text.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/readers/test_text.py#L1)

## src/opendoc_formats/readers/html.py

Static HTML to editable document blocks, without browser or network execution.

- `read_html_model(path: str | Path, *, resource_root: str | Path | None=None, limits: od.DocumentLimits | None=None) -> DocumentModel` — [строка 37](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/html.py#L37)
- `HtmlReader` — [строка 79](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/html.py#L79)
- `__init__(self, soup: Any, source: Path, resource_root: str | Path | None) -> None` — [строка 80](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/html.py#L80)
- `semantic_id(self) -> str` — [строка 92](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/html.py#L92)
- `language(node: Any) -> str | None` — [строка 101](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/html.py#L101)
- `blocks(self, root: Any) -> list[od.Block]` — [строка 107](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/html.py#L107)
- `link(self, href: str | None) -> str | None` — [строка 240](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/html.py#L240)
- `list_blocks(self, node: Any) -> list[od.Block]` — [строка 248](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/html.py#L248)
- `table(self, node: Any) -> od.Table` — [строка 281](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/html.py#L281)

Импорты: `__future__`, `bs4`, `collections`, `opendoc_formats.html_tables`, `opendoc_formats.readers.html_css`, `opendoc_formats.readers.html_diagnostics`, `opendoc_formats.readers.html_resources`, `opendoc_model`, `pathlib`, `typing`, `urllib.parse`

Тесты: [test_html_reader.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/test_html_reader.py#L1)

## src/opendoc_formats/readers/html_css.py

Bounded static CSS cascade; unsupported syntax is never silently accepted.

- `Cascade` — [строка 26](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/html_css.py#L26)
- `__init__(self, soup: Any, warn: Callable[..., None]) -> None` — [строка 27](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/html_css.py#L27)
- `declarations(self, raw: Any, warn: Callable[..., None] | None=None) -> list[tuple[str, str, bool]]` — [строка 49](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/html_css.py#L49)
- `style(self, node: Any) -> dict[str, str]` — [строка 74](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/html_css.py#L74)
- `matches(node: Any, selector: str) -> bool` — [строка 135](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/html_css.py#L135)
- `text_style(self, css: dict[str, str], node: Any=None) -> od.TextStyle` — [строка 144](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/html_css.py#L144)

Импорты: `__future__`, `collections.abc`, `opendoc_model`, `tinycss2.color3`, `typing`

## src/opendoc_formats/readers/html_diagnostics.py

Resolve source-node diagnostics to stable, JSON-persisted imported blocks.

- `HtmlDiagnostics` — [строка 14](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/html_diagnostics.py#L14)
- `__init__(self) -> None` — [строка 15](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/html_diagnostics.py#L15)
- `at(self, node: Any) -> Iterator[None]` — [строка 22](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/html_diagnostics.py#L22)
- `warn(self, feature: str, message: str, node: Any=None) -> None` — [строка 30](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/html_diagnostics.py#L30)
- `bind(self, block: od.Block, root: Any, nodes: Iterable[Any]=()) -> None` — [строка 35](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/html_diagnostics.py#L35)
- `resolve(self, node: Any) -> str` — [строка 56](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/html_diagnostics.py#L56)
- `finish(self) -> dict[str, Any]` — [строка 73](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/html_diagnostics.py#L73)
- `attach(self, document: od.DocumentModel, source: Path, data: bytes, *, limits: od.DocumentLimits | None=None) -> None` — [строка 91](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/html_diagnostics.py#L91)

Импорты: `__future__`, `collections.abc`, `contextlib`, `opendoc_model`, `pathlib`, `typing`

Тесты: [test_html_diagnostics.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/readers/test_html_diagnostics.py#L1)

## src/opendoc_formats/readers/html_resources.py

Embedded HTML resources with explicit opt-in for a bounded local directory.

- `clean_xml(value: str, kind: str, warn: Callable[..., None]) -> str | None` — [строка 22](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/html_resources.py#L22)
- `Resources` — [строка 66](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/html_resources.py#L66)
- `__init__(self, warn: Callable[..., None], root: str | Path | None=None) -> None` — [строка 67](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/html_resources.py#L67)
- `image(self, src: str, alt: str='') -> od.Image | None` — [строка 71](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/html_resources.py#L71)
- `svg(self, xml: str, alt: str='') -> od.Image | None` — [строка 108](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/html_resources.py#L108)

Импорты: `__future__`, `collections.abc`, `opendoc_model`, `pathlib`, `urllib.parse`

Тесты: [test_epub_structure.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/readers/test_epub_structure.py#L1)

## src/opendoc_formats/readers/html_text.py

Lazy public HTML readers.

- `read_html_model(path: str | Path, *, resource_root: str | Path | None=None) -> od.DocumentModel` — [строка 13](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/html_text.py#L13)
- `read_html(path: str | Path) -> Text` — [строка 19](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/html_text.py#L19)

Импорты: `__future__`, `opendoc_formats.readers.html`, `opendoc_formats.support.document_adapters`, `opendoc_formats.types`, `pathlib`

Тесты: [test_html_diagnostics.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/readers/test_html_diagnostics.py#L1), [test_html_model.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/readers/test_html_model.py#L1), [test_html_normalize.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_html_normalize.py#L1)

## src/opendoc_formats/readers/latex.py

- `docx_to_latex(input_path: str | Path, output_path: str | Path | None=None, doc_type: str='manuscript') -> str` — [строка 52](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/latex.py#L52)
- `docx_to_latex_pandoc(input_path: str | Path, output_path: str | Path, doc_type: str='manuscript') -> str` — [строка 116](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/latex.py#L116)

Импорты: `__future__`, `docx`, `docx.enum.text`, `opendoc_formats.errors`, `opendoc_formats.support.artifacts`, `opendoc_formats.support.io`, `opendoc_formats.support.latex`, `pathlib`, `typing`

Тесты: [test_text.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/readers/test_text.py#L1), [test_latex.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_latex.py#L1)

## src/opendoc_formats/readers/pdf.py

Текстовый ридер с цепочкой fallback-движков.

- `read_pdf_geometry(path: str | Path) -> PdfGeometryDocument` — [строка 92](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/pdf.py#L92)
- `read_pdf(path: str) -> Text` — [строка 98](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/pdf.py#L98)
- `get_pdf_info(path: str) -> dict` — [строка 125](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/pdf.py#L125)

Импорты: `__future__`, `opendoc_formats.readers.pdf_geometry`, `opendoc_formats.readers.pdf_semantic`, `opendoc_formats.support.backends`, `opendoc_formats.support.pdf_probe`, `opendoc_formats.types`, `pathlib`, `pypdf`, `typing`

Тесты: [test_pdf_geometry.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/readers/test_pdf_geometry.py#L1), [test_pdf_ocr_merge.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/readers/test_pdf_ocr_merge.py#L1), [test_pdf_probe.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/support/test_pdf_probe.py#L1)

## src/opendoc_formats/readers/pdf_classify.py

Семантическая классификация геометрических блоков PDF.

- `PdfSemanticClassification` — [строка 23](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/pdf_classify.py#L23)
- `repeated_margin_roles(document: PdfGeometryDocument) -> dict[tuple[int, int], str]` — [строка 30](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/pdf_classify.py#L30)
- `classify_text_block(block: PdfTextBlockGeometry, page: PdfPageGeometry, *, repeated_role: str | None=None) -> PdfSemanticClassification` — [строка 50](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/pdf_classify.py#L50)

Импорты: `__future__`, `collections`, `dataclasses`, `opendoc_formats.readers.pdf_geometry`, `opendoc_formats.types`

## src/opendoc_formats/readers/pdf_composition_policy.py

Conservative native-dictionary audit for the finite RGB compositor profile.

- `unsupported_policy(document: Any, limits: DocumentLimits) -> str | None` — [строка 10](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/pdf_composition_policy.py#L10)

Импорты: `__future__`, `opendoc_model`, `typing`

## src/opendoc_formats/readers/pdf_content.py

Disposable native content view without interactive appearances or stale caches.

- `content_only_pdf(path: str | Path) -> Iterator[Any]` — [строка 14](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/pdf_content.py#L14)

Импорты: `__future__`, `collections.abc`, `contextlib`, `opendoc_model`, `pathlib`, `typing`

## src/opendoc_formats/readers/pdf_fields.py

Bounded AcroForm tree audit independent of widget appearance extraction.

- `canonical_field_names(pdf: Any) -> set[str]` — [строка 25](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/pdf_fields.py#L25)
- `audit_field_tree(pdf: Any, widgets: set[int], record: Callable[..., None]) -> None` — [строка 71](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/pdf_fields.py#L71)

Импорты: `__future__`, `collections.abc`, `opendoc_model`, `typing`

Тесты: [test_pdf_field_tree.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/readers/test_pdf_field_tree.py#L1)

## src/opendoc_formats/readers/pdf_font_bindings.py

Bind painted glyph origins to actual native font bytes, never family guesses.

- `painted_font_programs(page: Any, resources: dict[str, Resource], origins: set[tuple[float, float]]) -> dict` — [строка 11](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/pdf_font_bindings.py#L11)

Импорты: `__future__`, `opendoc_model`, `typing`

## src/opendoc_formats/readers/pdf_fonts.py

Preserve embedded PDF font programs as bounded public Model resources.

- `extract_pdf_fonts(path: str | Path, *, limits: DocumentLimits | None=None) -> dict[str, Resource]` — [строка 10](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/pdf_fonts.py#L10)

Импорты: `__future__`, `opendoc_model`, `pathlib`

## src/opendoc_formats/readers/pdf_geometry.py

Геометрический слой импорта PDF без семантических эвристик.

- `PdfSpanGeometry` — [строка 15](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/pdf_geometry.py#L15)
- `PdfLineGeometry` — [строка 28](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/pdf_geometry.py#L28)
- `text(self) -> str` — [строка 36](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/pdf_geometry.py#L36)
- `PdfTextBlockGeometry` — [строка 41](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/pdf_geometry.py#L41)
- `text(self) -> str` — [строка 47](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/pdf_geometry.py#L47)
- `PdfImageGeometry` — [строка 52](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/pdf_geometry.py#L52)
- `PdfTableCellGeometry` — [строка 62](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/pdf_geometry.py#L62)
- `PdfTableGeometry` — [строка 70](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/pdf_geometry.py#L70)
- `text(self) -> str` — [строка 80](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/pdf_geometry.py#L80)
- `row_count(self) -> int` — [строка 84](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/pdf_geometry.py#L84)
- `column_count(self) -> int` — [строка 88](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/pdf_geometry.py#L88)
- `PdfPageGeometry` — [строка 93](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/pdf_geometry.py#L93)
- `PdfGeometryDocument` — [строка 106](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/pdf_geometry.py#L106)
- `extract_pdf_geometry(path: str | Path, *, exclude_interactions: bool=False) -> PdfGeometryDocument` — [строка 113](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/pdf_geometry.py#L113)

Импорты: `__future__`, `bisect`, `dataclasses`, `opendoc_formats.readers.pdf_content`, `pathlib`, `statistics`, `typing`

Тесты: [test_pdf_geometry.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/readers/test_pdf_geometry.py#L1), [test_pdf_images.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/readers/test_pdf_images.py#L1), [test_pdf_ocr_merge.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/readers/test_pdf_ocr_merge.py#L1)

## src/opendoc_formats/readers/pdf_graphics_state.py

Bounded native PDF paint states, including Form XObject clip/group scopes.

- `native_paint_states(page: Any, *, limits: DocumentLimits | None=None) -> dict` — [строка 15](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/pdf_graphics_state.py#L15)

Импорты: `__future__`, `opendoc_formats.readers.pdf_composition_policy`, `opendoc_formats.readers.pdf_scopes`, `opendoc_model`, `typing`

Тесты: [test_pdf_docx_graphics.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_pdf_docx_graphics.py#L1)

## src/opendoc_formats/readers/pdf_image_alpha.py

Combine straight PDF image samples and a soft mask without alpha roundoff.

- `straight_alpha_png(image: bytes, mask: bytes) -> bytes` — [строка 11](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/pdf_image_alpha.py#L11)

Импорты: `__future__`, `opendoc_formats.errors`

Тесты: [test_pdf_docx_complex.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_pdf_docx_complex.py#L1)

## src/opendoc_formats/readers/pdf_image_clips.py

Read a bounded single-image quadrilateral clip profile, without executing content.

- `image_clip_profiles(page: Any) -> list[tuple[int, tuple[float, ...], tuple[float, ...], ImageCrop]]` — [строка 21](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/pdf_image_clips.py#L21)
- `clipped_image_placement(info: dict[str, Any], profiles: list[tuple[int, tuple[float, ...], tuple[float, ...], ImageCrop]]) -> tuple[tuple[float, ...], tuple[float, ...], ImageCrop] | None` — [строка 89](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/pdf_image_clips.py#L89)

Импорты: `__future__`, `opendoc_model`, `typing`

## src/opendoc_formats/readers/pdf_images.py

Extract raster images and vector drawings from PDF pages.

- `ExtractedPdfImage` — [строка 29](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/pdf_images.py#L29)
- `media_type(self) -> str` — [строка 49](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/pdf_images.py#L49)
- `PdfVectorDrawing` — [строка 67](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/pdf_images.py#L67)
- `is_path(self) -> bool` — [строка 94](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/pdf_images.py#L94)
- `extract_pdf_images(path: str | Path) -> tuple[list[ExtractedPdfImage], list[str]]` — [строка 116](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/pdf_images.py#L116)
- `extract_pdf_vector_drawings(path: str | Path) -> tuple[list[PdfVectorDrawing], list[str]]` — [строка 202](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/pdf_images.py#L202)
- `enrich_geometry_with_images(geometry: PdfGeometryDocument, images: list[ExtractedPdfImage] | None=None, vector_drawings: list[PdfVectorDrawing] | None=None) -> PdfGeometryDocument` — [строка 307](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/pdf_images.py#L307)

Импорты: `__future__`, `dataclasses`, `opendoc_formats.errors`, `opendoc_formats.readers.pdf_content`, `opendoc_formats.readers.pdf_geometry`, `opendoc_formats.readers.pdf_image_alpha`, `opendoc_formats.readers.pdf_image_clips`, `opendoc_model`, `opendoc_model.color`, `pathlib`, `typing`

Тесты: [test_format_audit.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/native/test_format_audit.py#L1), [test_pdf_images.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/readers/test_pdf_images.py#L1)

## src/opendoc_formats/readers/pdf_interactive.py

Finite PDF interaction profile; actions are inert data, never executed.

- `attach_pdf_interactions(model: DocumentModel, source: str | Path, *, limits: DocumentLimits | None=None) -> None` — [строка 68](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/pdf_interactive.py#L68)

Импорты: `__future__`, `opendoc_formats.pdf_graphics`, `opendoc_formats.pdf_outline`, `opendoc_formats.pdf_page_geometry`, `opendoc_formats.readers.pdf_fields`, `opendoc_model`, `pathlib`, `typing`

## src/opendoc_formats/readers/pdf_layout.py

Детерминированный порядок чтения для геометрических блоков PDF.

- `PdfOrderedBlock` — [строка 13](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/pdf_layout.py#L13)
- `PdfPageReadingOrder` — [строка 20](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/pdf_layout.py#L20)
- `analyze_page_reading_order(page: PdfPageGeometry) -> PdfPageReadingOrder` — [строка 26](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/pdf_layout.py#L26)
- `analyze_reading_order(blocks: list[PdfPositionedBlock], page_width: float) -> PdfPageReadingOrder` — [строка 32](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/pdf_layout.py#L32)

Импорты: `__future__`, `dataclasses`, `opendoc_formats.readers.pdf_geometry`

## src/opendoc_formats/readers/pdf_model.py

PDF → модель OpenDoc: геометрия, семантические блоки и внедряемый OCR.

- `read_pdf_model(*, path: str | Path, use_ocr: bool=False, ocr_backend: str='', handwriting: bool=False, use_gpu: bool=False, mode: str | None=None, ocr_engine_factory: Callable[..., Any] | None=None, limits: DocumentLimits | None=None) -> DocumentModel` — [строка 43](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/pdf_model.py#L43)

Импорты: `__future__`, `collections.abc`, `opendoc_formats.readers.pdf_fonts`, `opendoc_formats.readers.pdf_geometry`, `opendoc_formats.readers.pdf_images`, `opendoc_formats.readers.pdf_interactive`, `opendoc_formats.readers.pdf_ocr_merge`, `opendoc_formats.readers.pdf_paint`, `opendoc_formats.readers.pdf_scopes`, `opendoc_formats.readers.pdf_table_model`, `opendoc_formats.support.object_mapping`, `opendoc_formats.support.pdf_mapping_history`, `opendoc_formats.types`, `opendoc_model`, `opendoc_model.color`, `opendoc_model.document_model`, `opendoc_model.units`, `pathlib`, `typing`

## src/opendoc_formats/readers/pdf_ocr_merge.py

Объединение текстового слоя PDF и OCR с координатами и уверенностью.

- `merge_pdf_with_ocr(geometry: PdfGeometryDocument, ocr_pages: list[OcrPageResult] | None=None, *, use_text_layer: bool=True) -> Text` — [строка 147](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/pdf_ocr_merge.py#L147)
- `read_pdf_scenario(path: str, mode: str=PDF_SCENARIO_STRUCTURE, ocr_engine: Any=None, scale: int=3, handwriting: bool=False) -> Text` — [строка 299](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/pdf_ocr_merge.py#L299)
- `read_pdf_with_ocr(path: str, ocr_engine: Any=None, scale: int=3, handwriting: bool=False) -> Text` — [строка 350](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/pdf_ocr_merge.py#L350)

Импорты: `__future__`, `opendoc_formats.readers.pdf`, `opendoc_formats.readers.pdf_classify`, `opendoc_formats.readers.pdf_geometry`, `opendoc_formats.readers.pdf_layout`, `opendoc_formats.readers.pdf_ocr_types`, `opendoc_formats.types`, `typing`

Тесты: [test_pdf_ocr_merge.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/readers/test_pdf_ocr_merge.py#L1)

## src/opendoc_formats/readers/pdf_ocr_types.py

Типы для OCR-блоков с координатами и уверенностью.

- `OcrBlockGeometry` — [строка 14](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/pdf_ocr_types.py#L14)
- `OcrPageResult` — [строка 25](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/pdf_ocr_types.py#L25)
- `plain(self) -> str` — [строка 32](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/pdf_ocr_types.py#L32)
- `MergedTextBlock` — [строка 40](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/pdf_ocr_types.py#L40)

Импорты: `__future__`, `dataclasses`, `typing`

Тесты: [test_pdf_ocr_merge.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/readers/test_pdf_ocr_merge.py#L1)

## src/opendoc_formats/readers/pdf_paint.py

PDF paint evidence, independent of semantic reading order and Word layout.

- `attach_text_paint(document: DocumentModel, path: str | Path, *, limits: DocumentLimits | None) -> None` — [строка 12](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/pdf_paint.py#L12)

Импорты: `__future__`, `collections`, `opendoc_formats.pdf_graphics`, `opendoc_formats.readers.pdf_content`, `opendoc_formats.readers.pdf_font_bindings`, `opendoc_formats.readers.pdf_graphics_state`, `opendoc_formats.readers.pdf_image_clips`, `opendoc_formats.readers.pdf_images`, `opendoc_model`, `pathlib`, `typing`

## src/opendoc_formats/readers/pdf_scopes.py

Bind measured PDF paint scopes to the official mixed VectorScene contract.

- `scope_color_spaces(evidence: dict) -> dict[int | None, GroupColorSpace]` — [строка 34](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/pdf_scopes.py#L34)
- `needs_scene(evidence: dict) -> bool` — [строка 50](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/pdf_scopes.py#L50)
- `attach_pdf_scopes(document: DocumentModel, *, limits: DocumentLimits | None, include_neutral: bool=False) -> None` — [строка 70](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/pdf_scopes.py#L70)

Импорты: `__future__`, `dataclasses`, `opendoc_formats.pdf_graphics`, `opendoc_model`

## src/opendoc_formats/readers/pdf_semantic.py

Семантическая интерпретация геометрического слоя PDF.

- `analyze_pdf_geometry(document: PdfGeometryDocument) -> Text` — [строка 11](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/pdf_semantic.py#L11)

Импорты: `__future__`, `opendoc_formats.readers.pdf_classify`, `opendoc_formats.readers.pdf_geometry`, `opendoc_formats.readers.pdf_layout`, `opendoc_formats.types`

Тесты: [test_pdf_geometry.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/readers/test_pdf_geometry.py#L1)

## src/opendoc_formats/readers/pdf_table_model.py

Retain native PDF cell geometry and text styling in reconstructed Model tables.

- `pdf_table_rows(page: PdfPageGeometry, meta: dict[str, Any], run_builder: Callable[[Any, str, dict[str, Any]], list[TextRun]], warnings: list[str]) -> list[TableRow]` — [строка 14](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/pdf_table_model.py#L14)

Импорты: `__future__`, `collections.abc`, `dataclasses`, `opendoc_formats.readers.pdf_geometry`, `opendoc_model`, `typing`

## src/opendoc_formats/readers/pptx.py

PPTX → Text / DocumentModel импортёры.

- `read_pptx(path: Union[str, Path], *, include_tables: bool=True) -> Text` — [строка 359](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/pptx.py#L359)
- `read_pptx_model(path: Union[str, Path], *, mode: ConversionMode=ConversionMode.BALANCED, limits: DocumentLimits | None=None) -> DocumentModel` — [строка 400](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/pptx.py#L400)

Импорты: `__future__`, `dataclasses`, `lxml`, `opendoc_formats.ooxml.color`, `opendoc_formats.readers.pptx_chart_data`, `opendoc_formats.readers.pptx_diagnostics`, `opendoc_formats.readers.pptx_geometry`, `opendoc_formats.readers.pptx_numeric_cache`, `opendoc_formats.readers.pptx_paragraph`, `opendoc_formats.readers.pptx_picture`, `opendoc_formats.readers.pptx_placeholder`, `opendoc_formats.readers.pptx_table`, `opendoc_formats.readers.pptx_theme_fonts`, `opendoc_formats.support.io`, `opendoc_formats.types`, `opendoc_model`, `opendoc_model.color`, `opendoc_model.document_model`, `opendoc_model.units`, `pathlib`, `pptx`, `pptx.opc.constants`, `typing`

Тесты: [test_pptx_visual_roundtrip.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/readers/test_pptx_visual_roundtrip.py#L1), [test_source_coverage.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/test_source_coverage.py#L1), [test_mathml_decorations.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_mathml_decorations.py#L1), [test_mathml_pptx.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_mathml_pptx.py#L1), [test_pptx_chart_roundtrip.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_pptx_chart_roundtrip.py#L1), [test_pptx_combo_roundtrip.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_pptx_combo_roundtrip.py#L1), [test_pptx_custom_errors.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_pptx_custom_errors.py#L1), [test_pptx_error_directions.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_pptx_error_directions.py#L1), [test_pptx_geometry_roundtrip.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_pptx_geometry_roundtrip.py#L1), [test_pptx_label_roundtrip.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_pptx_label_roundtrip.py#L1), [test_pptx_multiple_trends.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_pptx_multiple_trends.py#L1), [test_pptx_office_regressions.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_pptx_office_regressions.py#L1), [test_pptx_placeholder_roundtrip.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_pptx_placeholder_roundtrip.py#L1), [test_pptx_plot_roundtrip.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_pptx_plot_roundtrip.py#L1), [test_pptx_point_roundtrip.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_pptx_point_roundtrip.py#L1), [test_pptx_statistics_roundtrip.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_pptx_statistics_roundtrip.py#L1), [test_pptx_table_roundtrip.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_pptx_table_roundtrip.py#L1), [test_pptx_text_roundtrip.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_pptx_text_roundtrip.py#L1), [test_pptx_theme_fonts.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_pptx_theme_fonts.py#L1), [test_pptx_trend_forecast.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_pptx_trend_forecast.py#L1), [test_pptx_writer.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_pptx_writer.py#L1)

## src/opendoc_formats/readers/pptx_chart_data.py

Indexed chart caches: preserve absent points and numeric XY dimensions.

- `cached_values(node: Any) -> list[str | None]` — [строка 10](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/pptx_chart_data.py#L10)
- `numeric_series(series: Any) -> dict[str, Any]` — [строка 29](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/pptx_chart_data.py#L29)
- `plot_settings(node: Any) -> dict[str, str | None]` — [строка 45](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/pptx_chart_data.py#L45)
- `plot_appearance(node: Any) -> dict[str, Any]` — [строка 54](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/pptx_chart_data.py#L54)

Импорты: `__future__`, `typing`

## src/opendoc_formats/readers/pptx_diagnostics.py

Partial, source-located PPTX preservation diagnostics; never execute content.

- `PptxDiagnostics` — [строка 24](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/pptx_diagnostics.py#L24)
- `__init__(self, source: Path) -> None` — [строка 25](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/pptx_diagnostics.py#L25)
- `record(self, feature: str, reason: str, message: str, node: Any=None, *, state: PreservationState=PreservationState.LOST, resource_id: str | None=None) -> None` — [строка 31](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/pptx_diagnostics.py#L31)
- `slide(self, slide: Any, page: int, original_part: str) -> None` — [строка 49](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/pptx_diagnostics.py#L49)
- `graphic(self, element: Any, *, resource_id: str | None=None) -> None` — [строка 64](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/pptx_diagnostics.py#L64)
- `attach(self, document: DocumentModel, *, limits: DocumentLimits | None=None) -> None` — [строка 77](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/pptx_diagnostics.py#L77)

Импорты: `__future__`, `opendoc_model`, `pathlib`, `typing`

## src/opendoc_formats/readers/pptx_geometry.py

Format-local native geometry and identity needed by the PPTX reverse path.

- `shape_geometry(element: Any) -> dict[str, Any]` — [строка 14](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/pptx_geometry.py#L14)
- `remember_shape_identity(block: od.Block, element: Any) -> None` — [строка 45](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/pptx_geometry.py#L45)

Импорты: `__future__`, `dataclasses`, `lxml`, `typing`

## src/opendoc_formats/readers/pptx_numeric_cache.py

Чтение числовых массивов диаграммы с сохранением пропущенных индексов.

- `indexed_numbers(node: Any) -> list[str | None]` — [строка 10](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/pptx_numeric_cache.py#L10)

Импорты: `__future__`, `typing`

Тесты: [test_pptx_custom_errors.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_pptx_custom_errors.py#L1)

## src/opendoc_formats/readers/pptx_paragraph.py

Explicit paragraph and frame formatting from DrawingML.

- `merge_text_styles(inherited: od.TextStyle | None, explicit: od.TextStyle) -> od.TextStyle` — [строка 12](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/pptx_paragraph.py#L12)
- `paragraph_metadata(element: Any, alignments: dict[str, str]) -> dict[str, Any]` — [строка 28](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/pptx_paragraph.py#L28)
- `paragraph_properties(properties: dict[str, Any], alignments: dict[str, str]) -> dict[str, Any]` — [строка 33](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/pptx_paragraph.py#L33)
- `merge_paragraph_settings(inherited: dict[str, Any], explicit: dict[str, Any]) -> dict[str, Any]` — [строка 73](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/pptx_paragraph.py#L73)
- `frame_metadata(body: Any) -> dict[str, Any]` — [строка 89](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/pptx_paragraph.py#L89)

Импорты: `__future__`, `copy`, `dataclasses`, `opendoc_model.document_model`, `typing`

## src/opendoc_formats/readers/pptx_picture.py

Read SVG companions and cropping without flattening vector resources.

- `read_picture(element: Any, slide_part: Any, state: Any, box: od.Box | None) -> od.Image | None` — [строка 16](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/pptx_picture.py#L16)

Импорты: `__future__`, `opendoc_model.document_model`, `typing`

## src/opendoc_formats/readers/pptx_placeholder.py

Наследование оформления текстовых заполнителей из макета и образца.

- `placeholder_chain(element: Any, layout: Any, master: Any) -> list[Any]` — [строка 29](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/pptx_placeholder.py#L29)
- `inherited_frame(chain: list[Any], element: Any) -> dict[str, Any]` — [строка 57](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/pptx_placeholder.py#L57)
- `inherited_paragraph(chain: list[Any], body: Any, level: int, meta: dict[str, Any], style: Any, *, parse_style: Any, alignments: dict[str, str], colors: dict[str, str]) -> tuple[dict[str, Any], Any]` — [строка 66](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/pptx_placeholder.py#L66)

Импорты: `__future__`, `opendoc_formats.readers.pptx_paragraph`, `typing`

Тесты: [test_pptx_placeholder_roundtrip.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_pptx_placeholder_roundtrip.py#L1)

## src/opendoc_formats/readers/pptx_table.py

Editable table cells, including paragraph structure and explicit cell appearance.

- `read_table(element: Any, box: od.Box | None, slide_part: Any, theme_colors: dict[str, str], parse_runs: Callable[..., None], resolve_color: Callable[..., Any], alignments: dict[str, str]) -> od.Table` — [строка 16](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/pptx_table.py#L16)

Импорты: `__future__`, `collections.abc`, `opendoc_formats.readers.pptx_paragraph`, `opendoc_model.document_model`, `typing`

## src/opendoc_formats/readers/pptx_theme_fonts.py

Материализация ссылок на шрифты темы в текстовых фрагментах PPTX.

- `slide_theme_fonts(slide: Any) -> dict[str, str]` — [строка 40](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/pptx_theme_fonts.py#L40)
- `materialize_theme_fonts(blocks: list[Any], fonts: dict[str, str]) -> None` — [строка 56](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/pptx_theme_fonts.py#L56)

Импорты: `__future__`, `lxml`, `opendoc_model.document_model`, `pptx.opc.constants`, `typing`

Тесты: [test_pptx_theme_fonts.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_pptx_theme_fonts.py#L1)

## src/opendoc_formats/readers/svg_color.py

Safe SVG color discovery for canonical resource metadata.

- `parse_svg_color(value: str, *, opacity: float | None=None) -> ColorValue | None` — [строка 17](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/svg_color.py#L17)
- `svg_color_catalog(data: bytes) -> list[dict[str, object]]` — [строка 33](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/svg_color.py#L33)

Импорты: `__future__`, `opendoc_model.color`, `xml.etree`

Тесты: [test_svg_color.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/readers/test_svg_color.py#L1)

## src/opendoc_formats/readers/tex_model.py

Finite source LaTeX parsing into OpenDoc, with inert original bytes and located losses.

- `read_tex_model(path: str | Path, *, max_input_bytes: int=10 * 1024 * 1024, cancelled: Callable[[], bool] | None=None, limits: DocumentLimits | None=None) -> DocumentModel` — [строка 565](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/tex_model.py#L565)

Импорты: `__future__`, `dataclasses`, `opendoc_formats.errors`, `opendoc_formats.readers.tex_source`, `opendoc_formats.tex_lists`, `opendoc_model`, `pathlib`, `typing`

Тесты: [test_tex_model.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/readers/test_tex_model.py#L1)

## src/opendoc_formats/readers/tex_source.py

Bounded lexical LaTeX source reader; no TeX engine, file commands or macro execution.

- `TexToken` — [строка 15](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/tex_source.py#L15)
- `tokenize_tex(text: str, *, max_tokens: int=250000) -> list[TexToken]` — [строка 22](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/tex_source.py#L22)
- `load_tex_source(path: Path, max_bytes: int) -> tuple[bytes, str, list[TexToken]]` — [строка 45](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/tex_source.py#L45)

Импорты: `__future__`, `dataclasses`, `opendoc_formats.errors`, `pathlib`

Тесты: [test_tex_model.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/readers/test_tex_model.py#L1)

## src/opendoc_formats/readers/text.py

- `extract_text(input_path: str | Path, output_path: str | Path | None=None) -> str` — [строка 7](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/text.py#L7)
- `extract_text_with_tables(input_path: str | Path, output_path: str | Path | None=None) -> str` — [строка 25](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/text.py#L25)

Импорты: `opendoc_formats.errors`, `opendoc_formats.readers.docx`, `opendoc_formats.support.io`, `pathlib`

Тесты: [test_text.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/readers/test_text.py#L1)

## src/opendoc_formats/readers/txt.py

TXT и DjVu → Text.

- `read_txt(path: Union[str, Path], *, profile: TextProfile | None=None) -> Text` — [строка 14](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/txt.py#L14)
- `read_djvu(path: Union[str, Path], *, timeout: float=30, max_output_bytes: int=10 * 1024 * 1024, cancelled: Callable[[], bool] | None=None) -> Text` — [строка 33](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/readers/txt.py#L33)

Импорты: `__future__`, `collections.abc`, `opendoc_formats.readers._djvu_text`, `opendoc_formats.readers._txt_model`, `opendoc_formats.text_profile`, `opendoc_formats.types`, `pathlib`, `typing`

Тесты: [test_djvu_text.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/readers/test_djvu_text.py#L1), [test_text_profile.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/test_text_profile.py#L1)

## src/opendoc_formats/support/__init__.py

Format adapter implementation helpers.


Импорты: отсутствуют

## src/opendoc_formats/support/artifacts.py

Safe lifecycle management for temporary conversion artifacts.

- `ArtifactWorkspace` — [строка 26](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/support/artifacts.py#L26)
- `__init__(self, *, parent: str | Path | None=None, prefix: str='opendoc_formats_', max_bytes: int=DEFAULT_ARTIFACT_QUOTA) -> None` — [строка 33](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/support/artifacts.py#L33)
- `artifact_path(self, name: str, *, fallback: str='artifact') -> Path` — [строка 48](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/support/artifacts.py#L48)
- `write_bytes(self, name: str, data: bytes, *, fallback: str='artifact') -> Path` — [строка 55](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/support/artifacts.py#L55)
- `write_upload(self, upload: Any, name: str | None=None, *, chunk_size: int=1024 * 1024) -> Path` — [строка 70](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/support/artifacts.py#L70)
- `validate_artifact(self, artifact: str | Path) -> Path` — [строка 89](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/support/artifacts.py#L89)
- `cleanup(self) -> None` — [строка 105](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/support/artifacts.py#L105)
- `safe_artifact_filename(name: str, *, fallback: str) -> str` — [строка 129](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/support/artifacts.py#L129)

Импорты: `__future__`, `opendoc_model.storage`, `pathlib`, `types`, `typing`

Тесты: [test_artifacts.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/support/test_artifacts.py#L1), [test_io.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/support/test_io.py#L1)

## src/opendoc_formats/support/backends.py

Availability checks for optional modules, including missing dotted parents.

- `missing_backends(requirements: tuple[str, ...]) -> list[str]` — [строка 6](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/support/backends.py#L6)

Импорты: `importlib`

## src/opendoc_formats/support/document_adapters.py

Совместимые адаптеры между старым ``Text`` и богатым ``DocumentModel``.

- `text_to_document(text: Text) -> DocumentModel` — [строка 25](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/support/document_adapters.py#L25)
- `document_to_text(document: DocumentModel) -> Text` — [строка 50](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/support/document_adapters.py#L50)

Импорты: `__future__`, `opendoc_formats.types`, `opendoc_model.document_model`

Тесты: [test_full_contract.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/test_full_contract.py#L1)

## src/opendoc_formats/support/document_limits.py

Located SDK quota failures, preserving unknown error text without guessed fields.

- `limit_diagnostic(error: ArtifactLimitError, limits: DocumentLimits, source: str, code: str) -> DiagnosticIssue` — [строка 10](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/support/document_limits.py#L10)

Импорты: `__future__`, `opendoc_model`

Тесты: [test_import_limits.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/test_import_limits.py#L1)

## src/opendoc_formats/support/inspection.py

Структурная инспекция документов и промежуточной модели.

- `inspect_path(path: str | Path, *, options: ImportOptions | None=None) -> DocumentInspection` — [строка 34](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/support/inspection.py#L34)

Импорты: `__future__`, `collections`, `collections.abc`, `html.parser`, `opendoc_formats.api`, `opendoc_formats.errors`, `opendoc_formats.readers.docx`, `opendoc_formats.readers.pdf_fields`, `opendoc_formats.readers.pptx`, `opendoc_formats.readers.txt`, `opendoc_formats.support.document_limits`, `opendoc_model`, `opendoc_model.diagnostics`, `opendoc_model.document_codec`, `opendoc_model.inspection`, `opendoc_model.text_flow`, `pathlib`, `typing`

Тесты: [test_import_limits.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/test_import_limits.py#L1), [test_emphasis_quality.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_emphasis_quality.py#L1), [test_text_edit_budget.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_text_edit_budget.py#L1), [test_text_flow.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_text_flow.py#L1), [test_text_quality.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_text_quality.py#L1)

## src/opendoc_formats/support/io.py

Файловые утилиты: хеширование, безопасные архивы и атомарная запись.

- `ArchiveSafetyError` — [строка 24](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/support/io.py#L24)
- `check_archive_safety(path: PathLike, *, max_entries: int=DEFAULT_MAX_ARCHIVE_ENTRIES, max_total_size: int=DEFAULT_MAX_ARCHIVE_SIZE, max_ratio: int=DEFAULT_MAX_COMPRESSION_RATIO) -> None` — [строка 28](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/support/io.py#L28)
- `compute_hash(path: PathLike, algorithm: str='sha256', chunk: int=65536) -> str` — [строка 81](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/support/io.py#L81)
- `find_duplicates_by_paths(paths: Iterable[PathLike]) -> list[set[Path]]` — [строка 91](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/support/io.py#L91)
- `find_duplicates_in_folder(folder: PathLike) -> dict[Path, list[Path]]` — [строка 101](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/support/io.py#L101)
- `sanitize_filename(name: str, replacement: str='_') -> str` — [строка 119](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/support/io.py#L119)
- `sanitize_path(path: str) -> str` — [строка 126](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/support/io.py#L126)
- `ensure_dir(path: PathLike) -> Path` — [строка 131](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/support/io.py#L131)
- `ensure_folder(folder: PathLike) -> Path` — [строка 138](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/support/io.py#L138)
- `read_text_file(path: PathLike) -> str` — [строка 143](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/support/io.py#L143)
- `write_text_file(path: PathLike, content: str) -> None` — [строка 152](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/support/io.py#L152)
- `atomic_write_text(path: PathLike, content: str, encoding: str='utf-8', *, max_bytes: int | None=100 * 1024 * 1024) -> Path` — [строка 164](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/support/io.py#L164)
- `atomic_write_bytes(path: PathLike, data: bytes, *, max_bytes: int | None=100 * 1024 * 1024) -> Path` — [строка 188](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/support/io.py#L188)
- `atomic_copy(src: PathLike, dst: PathLike, *, max_bytes: int | None=100 * 1024 * 1024) -> Path` — [строка 202](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/support/io.py#L202)
- `atomic_replace_directory(src: PathLike, dst: PathLike) -> Path` — [строка 231](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/support/io.py#L231)
- `progress_bar(current: int, total: int, width: int=30) -> str` — [строка 271](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/support/io.py#L271)
- `validate_pdf(file_path: PathLike) -> bool` — [строка 278](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/support/io.py#L278)
- `get_file_info(file_path: PathLike) -> dict` — [строка 289](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/support/io.py#L289)
- `list_files(folder: PathLike, extensions: Optional[list[str]]=None, recursive: bool=False) -> list[dict]` — [строка 303](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/support/io.py#L303)
- `create_zip_archive(files: list[Path], output_path: Path) -> Path` — [строка 321](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/support/io.py#L321)

Импорты: `__future__`, `collections`, `collections.abc`, `opendoc_formats.support.artifacts`, `opendoc_formats.support.pdf_probe`, `pathlib`, `typing`

Тесты: [test_io.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/support/test_io.py#L1), [test_pdf_probe.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/support/test_pdf_probe.py#L1)

## src/opendoc_formats/support/latex.py

Утилиты для работы с LaTeX.

- `escape_latex(text: str) -> str` — [строка 25](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/support/latex.py#L25)

Импорты: отсутствуют

Тесты: [test_latex.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/support/test_latex.py#L1), [test_full_contract.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/test_full_contract.py#L1), [test_latex_list_acceptance.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_latex_list_acceptance.py#L1), [test_latex_native_text.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_latex_native_text.py#L1)

## src/opendoc_formats/support/mapping_composition.py

Bounded composition of explicit occurrence relations using OpenDoc's public codec.

- `compose_object_mappings(first: ObjectMapping, second: ObjectMapping, bridges: Mapping[str, tuple[str, ...] | None], *, source: DocumentModel | None=None, target: DocumentModel | None=None) -> ObjectMapping` — [строка 26](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/support/mapping_composition.py#L26)

Импорты: `__future__`, `collections.abc`, `dataclasses`, `opendoc_model`

## src/opendoc_formats/support/object_mapping.py

Measured PDF fallback occurrences using the public OpenDoc mapping contract.

- `get_object_mapping(report: ConversionReport) -> ObjectMapping | None` — [строка 34](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/support/object_mapping.py#L34)
- `mapping_publication(report: ConversionReport, state: MappingPublication, *, code: str | None=None, reason: str | None=None) -> None` — [строка 40](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/support/object_mapping.py#L40)
- `mapping_result_matches(report: ConversionReport, path: Path) -> bool` — [строка 53](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/support/object_mapping.py#L53)
- `PdfFallbackMapping` — [строка 68](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/support/object_mapping.py#L68)
- `__init__(self, report: ConversionReport) -> None` — [строка 71](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/support/object_mapping.py#L71)
- `record(self, image: Image, location: str, replacement_id: str | None, message: str, *, rejected: bool=False, history: dict[str, Any] | None=None, generated: bool=False, provenance: Provenance | None=None) -> int` — [строка 83](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/support/object_mapping.py#L83)
- `bind(self, image: Image, index: int, location: str='') -> None` — [строка 120](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/support/object_mapping.py#L120)
- `source_for(self, image: Image, location: str='') -> int | None` — [строка 123](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/support/object_mapping.py#L123)
- `placed(self, index: int | None, page: int, occurrence: int, digest: bytes) -> None` — [строка 127](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/support/object_mapping.py#L127)
- `embed(self, pdf: Any) -> None` — [строка 131](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/support/object_mapping.py#L131)
- `story_resource(self, image: Image, location: str, resource: Resource, *, layout: bool=True) -> Resource` — [строка 136](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/support/object_mapping.py#L136)
- `prepare_story(self, document: Any) -> None` — [строка 167](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/support/object_mapping.py#L167)
- `resolve_story(self, pdf: Any, page_offset: int) -> None` — [строка 175](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/support/object_mapping.py#L175)
- `materialize(self, path: Path) -> None` — [строка 219](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/support/object_mapping.py#L219)

Импорты: `__future__`, `copy`, `dataclasses`, `opendoc_formats.readers.pdf_model`, `opendoc_formats.support.pdf_mapping_history`, `opendoc_formats.writers.html_resources`, `opendoc_model`, `opendoc_model.object_mapping`, `pathlib`, `typing`

Тесты: [test_pdf_mapping.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_pdf_mapping.py#L1), [test_pdf_svg_mapping.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_pdf_svg_mapping.py#L1)

## src/opendoc_formats/support/output_validation.py

Readability checks for staged exports; these do not measure visual fidelity.

- `validate_output(path: Path, format_id: str) -> None` — [строка 20](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/support/output_validation.py#L20)

Импорты: `__future__`, `docx`, `html.parser`, `opendoc_formats.readers.epub_package`, `opendoc_model`, `pathlib`, `pptx`, `zipfile`

Тесты: [test_release_contracts.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/test_release_contracts.py#L1)

## src/opendoc_formats/support/pdf_mapping_history.py

Bounded inert vector-origin declarations, bound anew to measured native rasters.

- `origin_history(source: ObjectOccurrence, issue: DiagnosticIssue) -> dict[str, Any]` — [строка 40](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/support/pdf_mapping_history.py#L40)
- `checked_history(raw: Any) -> dict[str, Any]` — [строка 53](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/support/pdf_mapping_history.py#L53)
- `embed_history(pdf: Any, histories: dict[int, dict[str, Any]], placements: dict[int, list[tuple[int, int, bytes]]]) -> None` — [строка 69](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/support/pdf_mapping_history.py#L69)
- `load_history(path: str | Path) -> tuple[dict[tuple[int, int], dict[str, Any]], list[DiagnosticIssue]]` — [строка 124](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/support/pdf_mapping_history.py#L124)
- `attach_history_map(document: DocumentModel, path: str | Path, matched: list[tuple[Any, dict[str, Any]]], issues: list[DiagnosticIssue], *, limits: DocumentLimits | None=None) -> ObjectMapping | None` — [строка 184](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/support/pdf_mapping_history.py#L184)
- `read_pdf_origin_mapping(path: str | Path) -> ObjectMapping | None` — [строка 230](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/support/pdf_mapping_history.py#L230)

Импорты: `__future__`, `dataclasses`, `opendoc_formats.readers.pdf_model`, `opendoc_formats.support.object_mapping`, `opendoc_formats.writers.html_resources`, `opendoc_model`, `pathlib`, `typing`

Тесты: [test_pdf_mapping_history.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_pdf_mapping_history.py#L1)

## src/opendoc_formats/support/pdf_probe.py

Small PDF checks use an already installed profile instead of requiring another parser.

- `probe_pdf(path: str | Path, *, metadata: bool=False) -> tuple[int | None, dict[str, str]]` — [строка 11](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/support/pdf_probe.py#L11)

Импорты: `__future__`, `importlib`, `opendoc_formats.errors`, `pathlib`

## src/opendoc_formats/tex_lists.py

Inert TeX paragraph identity comments, not an alternate document model.

- `paragraph_marker(anchor: Anchor | None, item: ListItem | None) -> str` — [строка 15](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/tex_lists.py#L15)
- `paragraph_markers(text: str, *, limits: DocumentLimits | None=None) -> list[tuple[int, dict]]` — [строка 33](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/tex_lists.py#L33)

Импорты: `opendoc_formats.errors`, `opendoc_model`

## src/opendoc_formats/text_profile.py

Finite, dependency-free text encoding and newline policies.

- `TextProfile` — [строка 15](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/text_profile.py#L15)
- `TextEncodingError` — [строка 33](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/text_profile.py#L33)
- `__init__(self, reason: str, message: str) -> None` — [строка 34](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/text_profile.py#L34)
- `decode_text(data: bytes, profile: TextProfile) -> tuple[str, str, bool]` — [строка 39](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/text_profile.py#L39)
- `normalize_newlines(text: str) -> str` — [строка 65](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/text_profile.py#L65)
- `source_profile(text: str, encoding: str, bom: bool) -> dict[str, Any]` — [строка 69](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/text_profile.py#L69)
- `encode_text(text: str, profile: TextProfile, original: dict[str, Any]) -> tuple[bytes, dict[str, Any], bool]` — [строка 74](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/text_profile.py#L74)

Импорты: `__future__`, `dataclasses`, `typing`

## src/opendoc_formats/types.py

Lightweight extraction results; rich documents use OpenDoc.DocumentModel.

- `DocFormat` — [строка 10](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/types.py#L10)
- `BlockType` — [строка 24](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/types.py#L24)
- `Block` — [строка 37](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/types.py#L37)
- `Table` — [строка 48](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/types.py#L48)
- `Text` — [строка 56](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/types.py#L56)
- `to_dict(self) -> dict[str, Any]` — [строка 76](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/types.py#L76)

Импорты: `__future__`, `dataclasses`, `enum`, `typing`

Тесты: [test_pdf_geometry.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/readers/test_pdf_geometry.py#L1), [test_pdf_ocr_merge.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/readers/test_pdf_ocr_merge.py#L1), [test_full_contract.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/test_full_contract.py#L1)

## src/opendoc_formats/writers/__init__.py

Format adapter implementation helpers.


Импорты: отсутствуют

## src/opendoc_formats/writers/base.py

- `ConversionResult` — [строка 7](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/base.py#L7)
- `__init__(self, input_path: str | Path, output_path: str | Path, success: bool, error: str | None=None) -> None` — [строка 14](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/base.py#L14)
- `error(self) -> str | None` — [строка 27](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/base.py#L27)
- `to_dict(self) -> dict[str, object]` — [строка 33](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/base.py#L33)
- `BaseConverter` — [строка 40](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/base.py#L40)
- `convert(self, input_path: str | Path, output_path: str | Path) -> ConversionReport` — [строка 55](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/base.py#L55)

Импорты: `abc`, `opendoc_model.diagnostics`, `pathlib`

## src/opendoc_formats/writers/color_inheritance.py

Resolve DOCX color and spacing in a private renderer view, preserving public declarations.

- `materialize_docx_colors(document: DocumentModel, limits: DocumentLimits | None=None) -> DocumentModel` — [строка 21](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/color_inheritance.py#L21)

Импорты: `__future__`, `copy`, `opendoc_formats.ooxml.paragraph_flow`, `opendoc_formats.ooxml.paragraph_indent`, `opendoc_formats.ooxml.spacing`, `opendoc_model`, `opendoc_model.color`, `opendoc_model.limits`

Тесты: [test_docx_common_spacing.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/readers/test_docx_common_spacing.py#L1), [test_docx_paragraph_flow.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/readers/test_docx_paragraph_flow.py#L1), [test_docx_paragraph_indents.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/readers/test_docx_paragraph_indents.py#L1)

## src/opendoc_formats/writers/color_preflight.py

Target-specific diagnostics for canonical color metadata.

- `preflight_colors(document: DocumentModel, report: ConversionReport, *, target: str) -> None` — [строка 12](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/color_preflight.py#L12)

Импорты: `__future__`, `collections.abc`, `opendoc_model.color`, `opendoc_model.diagnostics`, `opendoc_model.document_model`

Тесты: [test_color_preflight.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_color_preflight.py#L1)

## src/opendoc_formats/writers/docx_drawing_writer.py

DOCX drawing exporter for raster and vector images.

- `write_image(paragraph: Any, image: Image, document: DocumentModel, report: ConversionReport, location: str, *, limits: DocumentLimits | None=None) -> None` — [строка 17](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/docx_drawing_writer.py#L17)

Импорты: `__future__`, `docx.opc.constants`, `docx.opc.part`, `docx.oxml`, `docx.oxml.ns`, `docx.shared`, `io`, `lxml`, `opendoc_formats.ooxml.package`, `opendoc_formats.writers.docx_groups`, `opendoc_model`, `opendoc_model.diagnostics`, `opendoc_model.document_model`, `opendoc_model.units`, `pathlib`, `typing`

## src/opendoc_formats/writers/docx_groups.py

Write bound Model vector scopes as editable Word group/shape objects.

- `bound_scene(document: DocumentModel, image: Image, *, limits: DocumentLimits | None=None) -> VectorScene | None` — [строка 18](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/docx_groups.py#L18)
- `write_group(paragraph: Any, image: Image, scene: VectorScene) -> None` — [строка 29](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/docx_groups.py#L29)

Импорты: `__future__`, `docx.oxml`, `docx.oxml.ns`, `lxml`, `opendoc_formats.ooxml.group_geometry`, `opendoc_formats.ooxml.package`, `opendoc_formats.writers.docx_drawing_writer`, `opendoc_model`, `typing`

## src/opendoc_formats/writers/docx_html_links.py

Stable Word bookmark names for arbitrary HTML fragment identifiers.

- `bookmark_name(identifier: str) -> str` — [строка 9](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/docx_html_links.py#L9)
- `add_bookmark(paragraph: Any, identifier: str) -> None` — [строка 13](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/docx_html_links.py#L13)

Импорты: `__future__`, `docx.oxml`, `docx.oxml.ns`, `hashlib`, `typing`

## src/opendoc_formats/writers/docx_html_lists.py

Native Word numbering for independently editable HTML lists.

- `apply_html_list(paragraph: Any, properties: dict[str, Any]) -> None` — [строка 8](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/docx_html_lists.py#L8)

Импорты: `__future__`, `docx.oxml`, `docx.oxml.ns`, `docx.shared`, `typing`

## src/opendoc_formats/writers/docx_notes_writer.py

Запись ссылок на сноски в текстовый поток DOCX.

- `write_note_reference(paragraph: Any, item: TextRun) -> bool` — [строка 12](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/docx_notes_writer.py#L12)

Импорты: `__future__`, `docx.oxml`, `docx.oxml.ns`, `opendoc_formats.writers.docx_style_writer`, `opendoc_model.document_model`, `typing`

## src/opendoc_formats/writers/docx_postprocess.py

Пост-обработка DOCX: восстановление структуры (заголовки) после конвертации.

- `apply_heading_styles(path: str | Path) -> None` — [строка 36](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/docx_postprocess.py#L36)
- `ensure_min_font(path: str | Path, min_pt: float=8.0) -> None` — [строка 100](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/docx_postprocess.py#L100)

Импорты: `__future__`, `docx`, `opendoc_formats.support.io`, `pathlib`, `typing`

## src/opendoc_formats/writers/docx_section_writer.py

DOCX section exporter for page geometry and running content.

- `section_start_type(source: Section, section_enum: Any) -> Any` — [строка 17](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/docx_section_writer.py#L17)
- `configure_section(target: Any, source: Section, document: DocumentModel, report: ConversionReport, section_index: int, counters: dict[str, int], write_blocks: BlockWriter) -> None` — [строка 22](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/docx_section_writer.py#L22)

Импорты: `__future__`, `collections.abc`, `docx.shared`, `lxml`, `opendoc_model.diagnostics`, `opendoc_model.document_model`, `typing`

## src/opendoc_formats/writers/docx_style_writer.py

DOCX style exporter for definitions, font formatting, and numbering.

- `write_styles(target: Any, styles: dict[str, TextStyle], report: ConversionReport, *, limits: DocumentLimits | None=None) -> None` — [строка 14](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/docx_style_writer.py#L14)
- `apply_paragraph_format(paragraph_format: Any, properties: Mapping[str, Any], report: ConversionReport, location: str, *, limits: DocumentLimits | None=None) -> None` — [строка 92](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/docx_style_writer.py#L92)
- `apply_numbering(paragraph_properties: Any, properties: Mapping[str, Any]) -> None` — [строка 106](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/docx_style_writer.py#L106)
- `apply_text_style(run: Any, style: TextStyle) -> None` — [строка 126](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/docx_style_writer.py#L126)
- `apply_font_style(font: Any, style: TextStyle) -> None` — [строка 141](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/docx_style_writer.py#L141)

Импорты: `__future__`, `collections.abc`, `docx.enum.style`, `docx.oxml`, `docx.oxml.ns`, `docx.shared`, `opendoc_formats.ooxml.layout`, `opendoc_formats.ooxml.paragraph_flow`, `opendoc_formats.ooxml.paragraph_indent`, `opendoc_formats.ooxml.run_position`, `opendoc_formats.ooxml.spacing`, `opendoc_formats.ooxml.word_color`, `opendoc_model`, `opendoc_model.diagnostics`, `opendoc_model.document_model`, `opendoc_model.limits`, `typing`

## src/opendoc_formats/writers/docx_table_writer.py

DOCX table exporter for spans, geometry, fills, margins, and styles.

- `write_table(container: Any, source: Table, document: DocumentModel, report: ConversionReport, location: str, counters: dict[str, int], write_blocks: BlockWriter, *, limits: DocumentLimits | None=None) -> None` — [строка 22](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/docx_table_writer.py#L22)

Импорты: `__future__`, `collections.abc`, `docx.enum.table`, `docx.oxml`, `docx.oxml.ns`, `docx.shared`, `lxml`, `opendoc_formats.ooxml.borders`, `opendoc_formats.ooxml.layout`, `opendoc_formats.ooxml.merged_cell_borders`, `opendoc_formats.ooxml.table_grid`, `opendoc_formats.ooxml.table_position`, `opendoc_formats.ooxml.widths`, `opendoc_formats.writers.pdf_docx_cells`, `opendoc_model`, `opendoc_model.diagnostics`, `opendoc_model.document_model`, `opendoc_model.properties`, `typing`

## src/opendoc_formats/writers/docx_text_writer.py

Запись абзацев и строчного содержимого в DOCX.

- `add_paragraph(container: Any, source: Paragraph, document: DocumentModel, report: ConversionReport, location: str, *, limits: DocumentLimits | None=None) -> Any` — [строка 19](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/docx_text_writer.py#L19)
- `write_paragraph_content(paragraph: Any, source: Paragraph, document: DocumentModel, report: ConversionReport, location: str, counters: dict[str, int], *, limits: DocumentLimits | None=None) -> None` — [строка 109](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/docx_text_writer.py#L109)
- `write_formula(paragraph: Any, formula: Formula, report: ConversionReport, location: str) -> None` — [строка 198](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/docx_text_writer.py#L198)

Импорты: `__future__`, `docx.enum.text`, `docx.opc.constants`, `docx.oxml`, `docx.oxml.ns`, `opendoc_formats.ooxml.headings`, `opendoc_formats.ooxml.layout`, `opendoc_formats.ooxml.package`, `opendoc_formats.ooxml.paragraph_flow`, `opendoc_formats.ooxml.paragraph_frame`, `opendoc_formats.ooxml.paragraph_indent`, `opendoc_formats.ooxml.positioned_text`, `opendoc_formats.ooxml.run_position`, `opendoc_formats.writers.docx_drawing_writer`, `opendoc_formats.writers.docx_html_links`, `opendoc_formats.writers.docx_html_lists`, `opendoc_formats.writers.docx_notes_writer`, `opendoc_formats.writers.docx_style_writer`, `opendoc_formats.writers.mathml_to_omml`, `opendoc_model`, `opendoc_model.diagnostics`, `opendoc_model.document_model`, `opendoc_model.limits`, `typing`, `urllib.parse`

## src/opendoc_formats/writers/docx_to_latex.py

Конвертер DOCX → LaTeX.

- `DocxToLatexConverter` — [строка 56](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/docx_to_latex.py#L56)
- `name(self) -> str` — [строка 58](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/docx_to_latex.py#L58)
- `convert(self, input_path: str | Path, output_path: str | Path) -> ConversionResult` — [строка 61](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/docx_to_latex.py#L61)

Импорты: `__future__`, `docx`, `docx.oxml.ns`, `opendoc_formats.support.io`, `opendoc_formats.support.latex`, `opendoc_formats.types`, `opendoc_formats.writers.base`, `pathlib`, `typing`

Тесты: [test_pdf_to_docx.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_pdf_to_docx.py#L1)

## src/opendoc_formats/writers/docx_writer.py

Экспорт богатой промежуточной модели в редактируемый DOCX.

- `write_docx_model(document: DocumentModel, output_path: str | Path, *, limits: DocumentLimits | None=None) -> ConversionReport` — [строка 35](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/docx_writer.py#L35)

Импорты: `__future__`, `docx`, `docx.enum.section`, `docx.oxml`, `functools`, `opendoc_formats.fonts`, `opendoc_formats.fonts.docx_embedding`, `opendoc_formats.fonts.resource_fonts`, `opendoc_formats.ooxml.group_geometry`, `opendoc_formats.ooxml.headings`, `opendoc_formats.ooxml.layout`, `opendoc_formats.ooxml.package`, `opendoc_formats.support.artifacts`, `opendoc_formats.support.io`, `opendoc_formats.writers.color_preflight`, `opendoc_formats.writers.docx_drawing_writer`, `opendoc_formats.writers.docx_section_writer`, `opendoc_formats.writers.docx_style_writer`, `opendoc_formats.writers.docx_table_writer`, `opendoc_formats.writers.docx_text_writer`, `opendoc_formats.writers.font_preflight`, `opendoc_formats.writers.html_resources`, `opendoc_formats.writers.pdf_docx_cells`, `opendoc_formats.writers.pdf_docx_model`, `opendoc_model`, `opendoc_model.diagnostics`, `opendoc_model.document_model`, `opendoc_model.limits`, `pathlib`, `typing`

Тесты: [test_format_audit.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/native/test_format_audit.py#L1), [test_docx_layout_roundtrip.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/readers/test_docx_layout_roundtrip.py#L1), [test_docx_typed_widths.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/readers/test_docx_typed_widths.py#L1), [test_docx_writer.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_docx_writer.py#L1), [test_html_normalize.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_html_normalize.py#L1)

## src/opendoc_formats/writers/epub_writer.py

Finite EPUB 3 export using the shared HTML renderer and Python's standard library.

- `write_epub_model(document: DocumentModel, output_path: str | Path, *, limits: DocumentLimits | None=None) -> ConversionReport` — [строка 198](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/epub_writer.py#L198)

Импорты: `__future__`, `copy`, `dataclasses`, `datetime`, `html.parser`, `opendoc_formats.epub_metadata`, `opendoc_formats.support.io`, `opendoc_formats.writers.html_resources`, `opendoc_formats.writers.html_writer`, `opendoc_model`, `pathlib`, `tempfile`, `urllib.parse`, `zipfile`

Тесты: [test_epub_writer.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_epub_writer.py#L1)

## src/opendoc_formats/writers/extracted_text.py

Serialize extracted plain text independently of OCR engines or applications.

- `write_extracted_text(text: str, output_path: str | Path, *, format_id: str) -> Path` — [строка 8](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/extracted_text.py#L8)

Импорты: `docx`, `opendoc_formats.support.io`, `opendoc_formats.support.latex`, `pathlib`

Тесты: [test_full_contract.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/test_full_contract.py#L1)

## src/opendoc_formats/writers/font_preflight.py

Shared font preflight for model exporters.

- `prepare_fonts(document: DocumentModel, report: ConversionReport, *, limits: DocumentLimits | None=None, resolver: FontResolver | None=None) -> DocumentModel` — [строка 12](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/font_preflight.py#L12)

Импорты: `__future__`, `opendoc_formats.fonts`, `opendoc_model.diagnostics`, `opendoc_model.document_model`, `opendoc_model.limits`

## src/opendoc_formats/writers/html_borders.py

Bounded visual projection of common table borders to static CSS.

- `table_border_styles(table: Table, report: ConversionReport, location: str) -> tuple[list[str], dict[int, list[str]]]` — [строка 37](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/html_borders.py#L37)

Импорты: `__future__`, `opendoc_model`

## src/opendoc_formats/writers/html_layout.py

Подготовка геометрии отображаемых объектов для браузерного HTML.

- `HtmlLayoutStage` — [строка 23](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/html_layout.py#L23)
- `execute(self, value: StageValue, context: StageContext) -> StageResult` — [строка 29](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/html_layout.py#L29)
- `geometry_styles(box: Box | None, properties: Any, *, positioned: bool, browser: bool=False) -> list[str]` — [строка 83](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/html_layout.py#L83)

Импорты: `__future__`, `collections.abc`, `dataclasses`, `opendoc_formats.writers.stages`, `opendoc_model.diagnostics`, `opendoc_model.document_model`, `opendoc_model.units`, `typing`

Тесты: [test_html_layout.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_html_layout.py#L1)

## src/opendoc_formats/writers/html_lists.py

Serialize model list paragraphs as nested semantic HTML lists.

- `render_blocks(blocks: Iterable[od.Block], render: Callable[[od.Block], str]) -> str` — [строка 11](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/html_lists.py#L11)

Импорты: `__future__`, `collections.abc`, `opendoc_model.document_model`

## src/opendoc_formats/writers/html_normalize.py

Нормализация ссылок и закладок модели для HTML без изменения источника.

- `HtmlNormalizeStage` — [строка 21](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/html_normalize.py#L21)
- `execute(self, value: StageValue, context: StageContext) -> StageResult` — [строка 27](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/html_normalize.py#L27)

Импорты: `__future__`, `collections.abc`, `dataclasses`, `opendoc_formats.writers.stages`, `opendoc_model.diagnostics`, `opendoc_model.document_model`, `urllib.parse`

Тесты: [test_html_normalize.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_html_normalize.py#L1)

## src/opendoc_formats/writers/html_resources.py

Подготовка снимка изображений для переносимого HTML до записи результата.

- `HtmlResourceStage` — [строка 35](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/html_resources.py#L35)
- `execute(self, value: StageValue, context: StageContext) -> StageResult` — [строка 41](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/html_resources.py#L41)
- `document_images(document: DocumentModel) -> Iterator[tuple[Image, str]]` — [строка 87](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/html_resources.py#L87)
- `image_data_uri(resource: Resource) -> str` — [строка 94](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/html_resources.py#L94)

Импорты: `__future__`, `collections.abc`, `dataclasses`, `opendoc_formats.writers.stages`, `opendoc_model.diagnostics`, `opendoc_model.document_model`, `pathlib`

Тесты: [test_html_resources.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_html_resources.py#L1), [test_pdf_mapping_history.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_pdf_mapping_history.py#L1), [test_pdf_svg_mapping.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_pdf_svg_mapping.py#L1)

## src/opendoc_formats/writers/html_verify.py

Проверка внутренних ссылок сериализованного HTML перед публикацией.

- `HtmlVerifyStage` — [строка 36](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/html_verify.py#L36)
- `execute(self, value: StageValue, context: StageContext) -> StageResult` — [строка 42](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/html_verify.py#L42)
- `publish_verified_html(html: str, output: Path, report: ConversionReport) -> None` — [строка 76](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/html_verify.py#L76)

Импорты: `__future__`, `collections`, `dataclasses`, `html.parser`, `opendoc_formats.writers.stages`, `opendoc_model.diagnostics`, `pathlib`, `urllib.parse`

## src/opendoc_formats/writers/html_writer.py

Экспорт богатой промежуточной модели в самодостаточный HTML.

- `write_html_model(document: DocumentModel, output_path: str | Path, *, limits: DocumentLimits | None=None) -> ConversionReport` — [строка 95](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/html_writer.py#L95)

Импорты: `__future__`, `html`, `opendoc_formats.fonts.html_embedding`, `opendoc_formats.html_tables`, `opendoc_formats.writers.color_inheritance`, `opendoc_formats.writers.color_preflight`, `opendoc_formats.writers.font_preflight`, `opendoc_formats.writers.html_borders`, `opendoc_formats.writers.html_layout`, `opendoc_formats.writers.html_lists`, `opendoc_formats.writers.html_normalize`, `opendoc_formats.writers.html_resources`, `opendoc_formats.writers.html_verify`, `opendoc_formats.writers.pptx_to_html._omml`, `opendoc_formats.writers.pptx_to_html._pptx_lib`, `opendoc_formats.writers.stages`, `opendoc_model`, `opendoc_model.color`, `opendoc_model.diagnostics`, `opendoc_model.document_model`, `opendoc_model.limits`, `opendoc_model.units`, `pathlib`, `typing`, `urllib.parse`

Тесты: [test_html_chart_statistics.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_html_chart_statistics.py#L1), [test_html_layout.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_html_layout.py#L1), [test_html_normalize.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_html_normalize.py#L1), [test_html_resources.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_html_resources.py#L1), [test_html_writer.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_html_writer.py#L1), [test_pptx_custom_errors.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_pptx_custom_errors.py#L1), [test_pptx_error_directions.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_pptx_error_directions.py#L1), [test_pptx_multiple_trends.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_pptx_multiple_trends.py#L1), [test_pptx_trend_forecast.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_pptx_trend_forecast.py#L1)

## src/opendoc_formats/writers/latex_lists.py

Project SDK list membership into native TeX scopes and counters.

- `list_paragraphs(document: DocumentModel, paragraphs: list[tuple[Paragraph, str]], *, limits: DocumentLimits | None) -> str` — [строка 8](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/latex_lists.py#L8)

Импорты: `opendoc_formats.tex_lists`, `opendoc_model`

## src/opendoc_formats/writers/latex_text.py

Dependency-free finite TeX text profile; other objects retain the DOCX route.

- `native_text(document: DocumentModel, *, limits: DocumentLimits | None) -> str | None` — [строка 31](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/latex_text.py#L31)

Импорты: `dataclasses`, `opendoc_formats.support.latex`, `opendoc_formats.writers.latex_lists`, `opendoc_model`

## src/opendoc_formats/writers/latex_writer.py

Native text-to-TeX export, with the established bridge for other objects.

- `write_latex_model(document: DocumentModel, output_path: str | Path, *, limits: DocumentLimits | None=None) -> ConversionReport` — [строка 9](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/latex_writer.py#L9)

Импорты: `opendoc_formats.support.backends`, `opendoc_formats.writers.docx_to_latex`, `opendoc_formats.writers.docx_writer`, `opendoc_formats.writers.latex_text`, `opendoc_model`, `pathlib`, `tempfile`

Тесты: [test_latex_native_text.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_latex_native_text.py#L1)

## src/opendoc_formats/writers/mathml_to_omml.py

Compatibility entry point for the shared MathML-to-Office-Math structure converter.


Импорты: `opendoc_model.mathml`

Тесты: [test_mathml_decorations.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_mathml_decorations.py#L1), [test_mathml_pptx.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_mathml_pptx.py#L1)

## src/opendoc_formats/writers/pdf_docx_borders.py

Project only proven complete PDF grid strokes into editable Word cell borders.

- `project_table_borders(document: DocumentModel, section: Section) -> None` — [строка 8](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pdf_docx_borders.py#L8)

Импорты: `__future__`, `opendoc_model`

## src/opendoc_formats/writers/pdf_docx_cells.py

Measured native PDF cell baselines after Word font resolution.

- `prepare_cell_baselines(cell: TableCell) -> None` — [строка 22](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pdf_docx_cells.py#L22)
- `fit_virtual_tables(document: DocumentModel, *, limits: DocumentLimits | None) -> None` — [строка 55](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pdf_docx_cells.py#L55)

Импорты: `__future__`, `opendoc_formats.fonts.word_metrics`, `opendoc_model`

## src/opendoc_formats/writers/pdf_docx_graphics.py

Project verified native PDF clip scopes into Word pictures without page rasterization.

- `prepare_section_graphics(document: DocumentModel, section: Section, *, limits: DocumentLimits | None) -> None` — [строка 30](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pdf_docx_graphics.py#L30)
- `verify_text_clip(properties: dict, evidence: dict) -> None` — [строка 98](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pdf_docx_graphics.py#L98)
- `clip_svg(root: ET.Element, clips: list[dict], box: Box, *, max_commands: int=50000) -> None` — [строка 160](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pdf_docx_graphics.py#L160)
- `install_svg(document: DocumentModel, image: Image, source: Resource, root: ET.Element, box: Box) -> None` — [строка 236](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pdf_docx_graphics.py#L236)
- `word_svg_bytes(root: ET.Element) -> bytes` — [строка 247](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pdf_docx_graphics.py#L247)

Импорты: `__future__`, `dataclasses`, `opendoc_formats.pdf_graphics`, `opendoc_formats.writers.pdf_group_compositor`, `opendoc_formats.writers.pdf_native_groups`, `opendoc_formats.writers.pdf_scope_projection`, `opendoc_model`, `xml.etree`

## src/opendoc_formats/writers/pdf_docx_images.py

Represent orthogonal native PDF image matrices using editable Word pictures.

- `prepare_image_transform(image: Image) -> None` — [строка 10](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pdf_docx_images.py#L10)

Импорты: `__future__`, `opendoc_model`

Тесты: [test_pdf_docx_complex.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_pdf_docx_complex.py#L1)

## src/opendoc_formats/writers/pdf_docx_model.py

Private fixed-layout Word view of the public PDF model; source stays unchanged.

- `prepare_pdf_docx(document: DocumentModel, *, limits: DocumentLimits | None=None) -> DocumentModel` — [строка 37](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pdf_docx_model.py#L37)

Импорты: `__future__`, `copy`, `dataclasses`, `opendoc_formats.fonts.resource_fonts`, `opendoc_formats.readers.pdf_geometry`, `opendoc_formats.readers.pdf_model`, `opendoc_formats.readers.pdf_scopes`, `opendoc_formats.writers.pdf_docx_borders`, `opendoc_formats.writers.pdf_docx_graphics`, `opendoc_formats.writers.pdf_docx_images`, `opendoc_formats.writers.pdf_docx_paint`, `opendoc_formats.writers.pdf_docx_vectors`, `opendoc_model`, `opendoc_model.limits`

Тесты: [test_pdf_group_scopes.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_pdf_group_scopes.py#L1)

## src/opendoc_formats/writers/pdf_docx_paint.py

Map measured PDF paint order to Word's drawing and body-text planes.

- `prepare_text_paint(paragraph: Paragraph) -> None` — [строка 8](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pdf_docx_paint.py#L8)
- `prepare_page_paint(section: Section, *, limits: DocumentLimits | None) -> None` — [строка 34](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pdf_docx_paint.py#L34)

Импорты: `__future__`, `opendoc_model`

## src/opendoc_formats/writers/pdf_docx_vectors.py

Keep supported PDF path objects as separate, positioned Word SVG pictures.

- `convert_vector(document: DocumentModel, image: Image, location: str) -> None` — [строка 11](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pdf_docx_vectors.py#L11)

Импорты: `__future__`, `dataclasses`, `opendoc_formats.writers.pdf_docx_graphics`, `opendoc_formats.writers.pdf_vectors`, `opendoc_model`, `xml.etree`

## src/opendoc_formats/writers/pdf_flow.py

Reserve inline image space and capture its actual Story page position.

- `PdfFlowRenderer` — [строка 15](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pdf_flow.py#L15)
- `__init__(self, document: DocumentModel, report: ConversionReport, flow_ids: dict[str, str], mapping: Any=None, *, limits: DocumentLimits | None=None) -> None` — [строка 16](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pdf_flow.py#L16)
- `record_position(positions: dict[tuple[str, int], tuple[float, ...]], position: Any) -> None` — [строка 62](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pdf_flow.py#L62)

Импорты: `__future__`, `dataclasses`, `opendoc_formats.writers.html_resources`, `opendoc_formats.writers.html_writer`, `opendoc_model`, `opendoc_model.limits`, `typing`

## src/opendoc_formats/writers/pdf_group_compositor.py

Exact planar RGB rectangle composition; no bitmap or SVG filter fallback.

- `project_rectangular_groups(document: DocumentModel, section: Section, evidence: dict, *, limits: DocumentLimits | None) -> dict` — [строка 60](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pdf_group_compositor.py#L60)

Импорты: `__future__`, `copy`, `dataclasses`, `opendoc_formats.pdf_graphics`, `opendoc_formats.writers.pdf_docx_graphics`, `opendoc_formats.writers.pdf_vectors`, `opendoc_model`, `xml.etree`

## src/opendoc_formats/writers/pdf_interactive.py

Bounded native PDF interactions; source actions are never executed.

- `write_interactions(pdf: Any, document: DocumentModel, report: ConversionReport, pages: dict[str, tuple[int, tuple[float, float], bool]], cancelled: Callable[[], bool], *, limits: DocumentLimits | None=None) -> None` — [строка 14](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pdf_interactive.py#L14)

Импорты: `__future__`, `opendoc_formats.writers.pdf_outline`, `opendoc_model`, `opendoc_model.limits`, `typing`

## src/opendoc_formats/writers/pdf_native_groups.py

Translate verified PDF vector occurrences into native editable scene groups.

- `project_native_groups(document: DocumentModel, section: Section, scene: VectorScene | None, evidence: dict, *, limits: DocumentLimits | None) -> dict` — [строка 32](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pdf_native_groups.py#L32)

Импорты: `__future__`, `copy`, `dataclasses`, `opendoc_formats.ooxml.group_geometry`, `opendoc_formats.writers.pdf_vectors`, `opendoc_model`

## src/opendoc_formats/writers/pdf_outline.py

Write shared outline hierarchy with explicit page and anchor destination maps.

- `write_outline(pdf: Any, document: DocumentModel, report: ConversionReport, pages: dict[str, tuple[int, tuple[float, float], bool]], anchors: dict[str, tuple[int, tuple[float, float]]], source_origins: dict[int, tuple[float, float]] | None=None, *, limits: DocumentLimits | None=None) -> None` — [строка 22](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pdf_outline.py#L22)

Импорты: `__future__`, `opendoc_model`, `opendoc_model.limits`, `typing`, `urllib.parse`

## src/opendoc_formats/writers/pdf_rasters.py

Bounded native raster transforms and placement in PDF page and Story coordinates.

- `PdfRaster` — [строка 27](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pdf_rasters.py#L27)
- `prepare_rasters(document: DocumentModel, report: ConversionReport, cancelled: Callable[[], bool], mapping: Any=None, *, limits: DocumentLimits | None=None) -> tuple[DocumentModel, list[list[PdfRaster]]]` — [строка 73](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pdf_rasters.py#L73)
- `draw_rasters(page: Any, rasters: list[PdfRaster], cancelled: Callable[[], bool], *, mapping: Any=None, page_index: int=0) -> None` — [строка 229](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pdf_rasters.py#L229)

Импорты: `__future__`, `collections.abc`, `dataclasses`, `opendoc_formats.support.pdf_mapping_history`, `opendoc_model`, `opendoc_model.limits`, `typing`

## src/opendoc_formats/writers/pdf_resources.py

Подготовка изображений для PDF Story без изменения исходной модели.

- `PdfResourceStage` — [строка 17](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pdf_resources.py#L17)
- `execute(self, value: StageValue, context: StageContext) -> StageResult` — [строка 24](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pdf_resources.py#L24)

Импорты: `__future__`, `dataclasses`, `opendoc_formats.writers.html_resources`, `opendoc_formats.writers.stages`, `opendoc_model.diagnostics`, `opendoc_model.document_model`, `typing`

Тесты: [test_pdf_resources.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_pdf_resources.py#L1), [test_pdf_svg_mapping.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_pdf_svg_mapping.py#L1)

## src/opendoc_formats/writers/pdf_scope_projection.py

Resolve authoritative SDK scopes into a private native-evidence projection.

- `project_scopes(document: DocumentModel, section: Section, *, limits: DocumentLimits | None) -> dict` — [строка 23](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pdf_scope_projection.py#L23)

Импорты: `__future__`, `copy`, `opendoc_formats.readers.pdf_scopes`, `opendoc_model`

## src/opendoc_formats/writers/pdf_text_verify.py

Bounded check of rendered plain text before PDF publication.

- `verify_section_text(pdf: Any, section: Section, report: ConversionReport, location: str) -> None` — [строка 40](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pdf_text_verify.py#L40)

Импорты: `__future__`, `collections.abc`, `opendoc_model`, `typing`

Тесты: [test_pdf_text_content.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_pdf_text_content.py#L1)

## src/opendoc_formats/writers/pdf_to_docx.py

- `PdfModelConverter` — [строка 18](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pdf_to_docx.py#L18)
- `name(self) -> str` — [строка 22](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pdf_to_docx.py#L22)
- `__init__(self, *, import_options: ImportOptions | None=None, export_options: ExportOptions | None=None) -> None` — [строка 25](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pdf_to_docx.py#L25)
- `convert(self, input_path: str | Path, output_path: str | Path) -> ConversionResult` — [строка 29](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pdf_to_docx.py#L29)
- `Pdf2DocxConverter` — [строка 105](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pdf_to_docx.py#L105)
- `name(self) -> str` — [строка 107](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pdf_to_docx.py#L107)
- `convert(self, input_path: str | Path, output_path: str | Path) -> ConversionResult` — [строка 110](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pdf_to_docx.py#L110)
- `PyMuPdfConverter` — [строка 131](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pdf_to_docx.py#L131)
- `name(self) -> str` — [строка 141](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pdf_to_docx.py#L141)
- `__init__(self, render_dpi: int=150, text_threshold: int=50) -> None` — [строка 144](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pdf_to_docx.py#L144)
- `convert(self, input_path: str | Path, output_path: str | Path) -> ConversionResult` — [строка 148](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pdf_to_docx.py#L148)
- `LibreOfficeConverter` — [строка 219](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pdf_to_docx.py#L219)
- `name(self) -> str` — [строка 228](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pdf_to_docx.py#L228)
- `__init__(self, libreoffice_path: str | None=None) -> None` — [строка 231](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pdf_to_docx.py#L231)
- `convert(self, input_path: str | Path, output_path: str | Path) -> ConversionResult` — [строка 250](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pdf_to_docx.py#L250)
- `FanOutConverter` — [строка 265](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pdf_to_docx.py#L265)
- `name(self) -> str` — [строка 275](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pdf_to_docx.py#L275)
- `__init__(self, tools: list[str] | None=None) -> None` — [строка 278](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pdf_to_docx.py#L278)
- `convert(self, input_path: str | Path, output_path: str | Path) -> ConversionResult` — [строка 283](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pdf_to_docx.py#L283)
- `create_converter(tool: str) -> BaseConverter` — [строка 331](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pdf_to_docx.py#L331)

Импорты: `__future__`, `dataclasses`, `docx`, `docx.shared`, `opendoc_formats`, `opendoc_formats.errors`, `opendoc_formats.support.artifacts`, `opendoc_formats.support.document_limits`, `opendoc_formats.support.io`, `opendoc_formats.support.object_mapping`, `opendoc_formats.writers.base`, `opendoc_formats.writers.docx_postprocess`, `opendoc_model`, `pathlib`, `typing`

Тесты: [test_pdf_docx_complex.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_pdf_docx_complex.py#L1), [test_pdf_docx_graphics.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_pdf_docx_graphics.py#L1), [test_pdf_group_scopes.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_pdf_group_scopes.py#L1), [test_pdf_model_docx.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_pdf_model_docx.py#L1), [test_pdf_to_docx.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_pdf_to_docx.py#L1)

## src/opendoc_formats/writers/pdf_unicode.py

Restore unambiguous ligature text in PDFs generated by the Story backend.

- `restore_ligature_unicode(pdf: Any, report: ConversionReport, location: str) -> None` — [строка 11](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pdf_unicode.py#L11)

Импорты: `__future__`, `fontTools.ttLib`, `io`, `opendoc_model`, `typing`

Тесты: [test_pdf_unicode.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_pdf_unicode.py#L1)

## src/opendoc_formats/writers/pdf_vectors.py

Bounded native PDF paths, separated from raster HTML resources.

- `PdfVector` — [строка 20](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pdf_vectors.py#L20)
- `prepare_vectors(document: DocumentModel, report: ConversionReport, cancelled: Callable[[], bool], mapping: Any=None) -> tuple[DocumentModel, list[list[PdfVector]]]` — [строка 115](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pdf_vectors.py#L115)
- `draw_vectors(page: Any, vectors: list[PdfVector], cancelled: Callable[[], bool]) -> None` — [строка 201](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pdf_vectors.py#L201)

Импорты: `__future__`, `dataclasses`, `opendoc_model`, `opendoc_model.color`, `opendoc_model.diagnostics`, `typing`

## src/opendoc_formats/writers/pdf_writer.py

Экспорт DocumentModel в PDF через встроенный HTML-layout PyMuPDF.

- `write_pdf_model(document: DocumentModel, output_path: str | Path, *, cancelled: Callable[[], bool] | None=None, limits: DocumentLimits | None=None) -> ConversionReport` — [строка 22](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pdf_writer.py#L22)

Импорты: `__future__`, `dataclasses`, `opendoc_formats.fonts.embedding`, `opendoc_formats.fonts.html_embedding`, `opendoc_formats.pdf_page_geometry`, `opendoc_formats.support.artifacts`, `opendoc_formats.support.io`, `opendoc_formats.support.object_mapping`, `opendoc_formats.writers.color_inheritance`, `opendoc_formats.writers.color_preflight`, `opendoc_formats.writers.font_preflight`, `opendoc_formats.writers.html_writer`, `opendoc_formats.writers.pdf_flow`, `opendoc_formats.writers.pdf_interactive`, `opendoc_formats.writers.pdf_outline`, `opendoc_formats.writers.pdf_rasters`, `opendoc_formats.writers.pdf_resources`, `opendoc_formats.writers.pdf_text_verify`, `opendoc_formats.writers.pdf_unicode`, `opendoc_formats.writers.pdf_vectors`, `opendoc_formats.writers.stages`, `opendoc_model`, `opendoc_model.diagnostics`, `opendoc_model.document_model`, `pathlib`, `typing`

Тесты: [test_pdf_raster_roundtrip.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_pdf_raster_roundtrip.py#L1), [test_pdf_resources.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_pdf_resources.py#L1), [test_pdf_vectors.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_pdf_vectors.py#L1), [test_pdf_writer.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_pdf_writer.py#L1)

## src/opendoc_formats/writers/pptx_cell_writer.py

Explicit cell appearance; no dependency on source table style IDs.

- `configure_cell(cell: Any, properties: dict[str, Any], report: od.ConversionReport, location: str) -> None` — [строка 15](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pptx_cell_writer.py#L15)

Импорты: `__future__`, `lxml`, `opendoc_formats.writers.pptx_text_writer`, `opendoc_model.color`, `opendoc_model.diagnostics`, `pptx.dml.color`, `pptx.enum.text`, `pptx.oxml.xmlchemy`, `pptx.util`, `typing`

## src/opendoc_formats/writers/pptx_chart_settings.py

Native axis scales and titles, independent of chart data/workbook generation.

- `configure_chart(chart: Any, data: dict[str, Any], report: od.ConversionReport, location: str) -> None` — [строка 14](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pptx_chart_settings.py#L14)

Импорты: `__future__`, `lxml`, `opendoc_model.diagnostics`, `pptx.chart.axis`, `pptx.enum.chart`, `typing`

## src/opendoc_formats/writers/pptx_chart_writer.py

Native chart data export, including stacking and independent XY series.

- `write_chart(slide: Any, data: dict[str, Any], geometry: tuple[int, int, int, int], report: od.ConversionReport, location: str) -> bool` — [строка 92](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pptx_chart_writer.py#L92)

Импорты: `__future__`, `opendoc_formats.writers.pptx_chart_settings`, `opendoc_formats.writers.pptx_combo_writer`, `opendoc_formats.writers.pptx_label_writer`, `opendoc_formats.writers.pptx_plot_writer`, `opendoc_formats.writers.pptx_point_writer`, `opendoc_formats.writers.pptx_statistics_writer`, `opendoc_formats.writers.pptx_text_writer`, `opendoc_model.diagnostics`, `pptx.chart.data`, `pptx.enum.chart`, `typing`

## src/opendoc_formats/writers/pptx_combo_writer.py

Compose native category plots against one shared embedded workbook.

- `is_combo(data: dict[str, Any]) -> bool` — [строка 13](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pptx_combo_writer.py#L13)
- `compose_combo(data: dict[str, Any], chart_data: Any, kind_for: Callable[[dict[str, Any]], Any]) -> tuple[list[Any], list[Any]]` — [строка 20](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pptx_combo_writer.py#L20)
- `install_combo(chart: Any, scene: tuple[list[Any], list[Any]]) -> None` — [строка 87](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pptx_combo_writer.py#L87)

Импорты: `__future__`, `collections.abc`, `copy`, `itertools`, `pptx.chart.xmlwriter`, `pptx.oxml`, `typing`

## src/opendoc_formats/writers/pptx_geometry_writer.py

Restore editable DrawingML shapes instead of substituting text boxes.

- `write_shape(slide: Any, meta: dict[str, Any], geometry: tuple[int, int, int, int], report: od.ConversionReport, location: str) -> Any` — [строка 15](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pptx_geometry_writer.py#L15)

Импорты: `__future__`, `lxml`, `opendoc_formats.writers.pptx_text_writer`, `opendoc_model.diagnostics`, `pptx.enum.shapes`, `pptx.util`, `typing`

## src/opendoc_formats/writers/pptx_image_writer.py

Native raster and SVG package resources for PPTX.

- `write_image(slide: Any, image: od.Image, document: od.DocumentModel, geometry: tuple[int, int, int, int], report: od.ConversionReport, location: str) -> Any` — [строка 13](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pptx_image_writer.py#L13)

Импорты: `__future__`, `io`, `opendoc_model.diagnostics`, `pathlib`, `pptx.opc.constants`, `pptx.opc.package`, `pptx.oxml`, `pptx.oxml.ns`, `typing`

## src/opendoc_formats/writers/pptx_label_writer.py

Нативные подписи данных на уровне набора диаграмм и отдельного ряда.

- `configure_labels(*, chart: Any, data: dict[str, Any], report: ConversionReport, location: str) -> None` — [строка 22](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pptx_label_writer.py#L22)

Импорты: `__future__`, `lxml`, `opendoc_model.diagnostics`, `typing`

## src/opendoc_formats/writers/pptx_objects_writer.py

Native PPTX tables and category charts.

- `write_table(slide: Any, block: od.Table, geometry: tuple[int, int, int, int], report: od.ConversionReport, location: str) -> None` — [строка 15](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pptx_objects_writer.py#L15)
- `write_chart(slide: Any, data: dict[str, Any], geometry: tuple[int, int, int, int], report: od.ConversionReport, location: str) -> bool` — [строка 63](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pptx_objects_writer.py#L63)

Импорты: `__future__`, `opendoc_formats.writers.pptx_cell_writer`, `opendoc_formats.writers.pptx_chart_writer`, `opendoc_formats.writers.pptx_text_writer`, `opendoc_model.diagnostics`, `opendoc_model.document_model`, `pptx.util`, `typing`

## src/opendoc_formats/writers/pptx_paragraph_writer.py

Native paragraph/list and text-frame settings, independent of run writing.

- `configure_frame(frame: Any, block: od.Block, report: od.ConversionReport, location: str) -> None` — [строка 13](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pptx_paragraph_writer.py#L13)
- `configure_paragraph(paragraph: Any, block: od.Block, index: int) -> None` — [строка 50](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pptx_paragraph_writer.py#L50)

Импорты: `__future__`, `lxml`, `opendoc_model.diagnostics`, `pptx.enum.text`, `pptx.util`, `typing`

## src/opendoc_formats/writers/pptx_plot_writer.py

Нативная геометрия столбцов и секторов с независимостью наборов диаграммы.

- `configure_plots(*, chart: Any, data: dict[str, Any], report: ConversionReport, location: str) -> None` — [строка 18](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pptx_plot_writer.py#L18)

Импорты: `__future__`, `lxml`, `opendoc_model.diagnostics`, `typing`

## src/opendoc_formats/writers/pptx_point_writer.py

Перенос явной заливки точек и отрыва секторов в нативные диаграммы.

- `configure_points(*, source: dict[str, Any], target: Any, kind: str, report: ConversionReport, location: str) -> None` — [строка 12](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pptx_point_writer.py#L12)

Импорты: `__future__`, `lxml`, `opendoc_formats.writers.pptx_text_writer`, `opendoc_model.diagnostics`, `typing`

## src/opendoc_formats/writers/pptx_scene_writer.py

Slide-local transforms, connector identities and native group hierarchy.

- `apply_transform(shape: Any, block: od.Block, report: od.ConversionReport, location: str) -> None` — [строка 17](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pptx_scene_writer.py#L17)
- `restore_connections(entries: list[tuple[od.Block, Any, str]], report: od.ConversionReport, groups: dict[str, list[Any]] | None=None) -> None` — [строка 53](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pptx_scene_writer.py#L53)
- `restore_groups(slide: Any, entries: list[tuple[od.Block, Any, str]], report: od.ConversionReport) -> dict[str, list[Any]]` — [строка 83](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pptx_scene_writer.py#L83)

Импорты: `__future__`, `collections`, `itertools`, `lxml`, `opendoc_model.diagnostics`, `pptx.util`, `typing`

## src/opendoc_formats/writers/pptx_statistics_writer.py

Нативные линии тренда и планки погрешностей рядов диаграмм.

- `configure_statistics(*, source: dict[str, Any], target: Any, options: dict[str, Any], report: Any, location: str) -> None` — [строка 144](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pptx_statistics_writer.py#L144)

Импорты: `__future__`, `lxml`, `opendoc_model.color`, `opendoc_model.diagnostics`, `typing`

## src/opendoc_formats/writers/pptx_text_writer.py

Native DrawingML text and Office Math, without importing PPTX at package import.

- `set_color(color_format: Any, value: od.ColorValue | str | dict[str, Any] | None, report: od.ConversionReport, location: str) -> None` — [строка 15](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pptx_text_writer.py#L15)
- `write_text(frame: Any, block: od.Block, report: od.ConversionReport, location: str, *, append: bool=False) -> None` — [строка 33](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pptx_text_writer.py#L33)
- `write_formula(paragraph: Any, formula: od.Formula, report: od.ConversionReport, location: str) -> None` — [строка 82](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pptx_text_writer.py#L82)

Импорты: `__future__`, `lxml`, `opendoc_formats.writers.mathml_to_omml`, `opendoc_formats.writers.pptx_paragraph_writer`, `opendoc_model.color`, `opendoc_model.diagnostics`, `opendoc_model.document_model`, `pptx.dml.color`, `pptx.util`, `typing`

## src/opendoc_formats/writers/pptx_to_html/__init__.py

Пакет ``opendoc_formats.writers.pptx_to_html``.


Импорты: `converter`

## src/opendoc_formats/writers/pptx_to_html/_omml.py

Convert OMML (Office Math Markup Language) to MathML.

- `convert_omml(omml_xml: str | Any) -> str` — [строка 79](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pptx_to_html/_omml.py#L79)
- `escape_xml(s: str) -> str` — [строка 132](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pptx_to_html/_omml.py#L132)
- `convert_math_elem(elem: Any, parent: Any) -> None` — [строка 136](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pptx_to_html/_omml.py#L136)
- `extract_math_from_paragraph(p_elem: Any) -> list[dict]` — [строка 396](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pptx_to_html/_omml.py#L396)
- `has_math(p_elem: Any) -> bool` — [строка 429](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pptx_to_html/_omml.py#L429)

Импорты: `__future__`, `lxml`, `typing`

Тесты: [test_mathml_decorations.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_mathml_decorations.py#L1), [test_mathml_pptx.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_mathml_pptx.py#L1), [test_pptx_to_html.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_pptx_to_html.py#L1)

## src/opendoc_formats/writers/pptx_to_html/_pptx_lib.py

Convert a .pptx file to a self-contained HTML viewer.

- `qn(t: str) -> str` — [строка 35](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pptx_to_html/_pptx_lib.py#L35)
- `emu_to_in(emu: int | str | None) -> float` — [строка 46](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pptx_to_html/_pptx_lib.py#L46)
- `fmt(v: float) -> str` — [строка 52](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pptx_to_html/_pptx_lib.py#L52)
- `pos_style(left_in: float, top_in: float, width_in: float, height_in: float, rotation: float=0.0) -> str` — [строка 57](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pptx_to_html/_pptx_lib.py#L57)
- `color_to_hex(elem: Any) -> Optional[str]` — [строка 87](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pptx_to_html/_pptx_lib.py#L87)
- `apply_lum(r: float, g: float, b: float, lm_val: float=1.0, lo_val: float=0.0, shd_val: float=1.0, tint_val: float=0.0) -> tuple[int, int, int]` — [строка 127](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pptx_to_html/_pptx_lib.py#L127)
- `rgb_to_hls(r: float, g: float, b: float) -> tuple[float, float, float]` — [строка 149](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pptx_to_html/_pptx_lib.py#L149)
- `hls_to_rgb(h: float, lightness: float, s: float) -> tuple[float, float, float]` — [строка 168](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pptx_to_html/_pptx_lib.py#L168)
- `size_to_pt(sz: int | str | None) -> str` — [строка 193](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pptx_to_html/_pptx_lib.py#L193)
- `safe_id(s: str) -> str` — [строка 200](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pptx_to_html/_pptx_lib.py#L200)

Импорты: `__future__`, `opendoc_model.units`, `typing`

Тесты: [test_pptx_to_html.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_pptx_to_html.py#L1)

## src/opendoc_formats/writers/pptx_to_html/_renderer.py

Convert a .pptx to a self-contained HTML viewer.

- `extract_resources(pptx_path: Path, out_dir: Path) -> dict[str, str]` — [строка 48](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pptx_to_html/_renderer.py#L48)
- `resolve_image(media_index: dict[str, str], rels: dict[str, str], rid: str) -> Optional[str]` — [строка 88](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pptx_to_html/_renderer.py#L88)
- `parse_xfrm(spPr_elem: Any, parent_xfrm: tuple[float, float, float, float, float] | None=None) -> tuple[float, float, float, float, float]` — [строка 103](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pptx_to_html/_renderer.py#L103)
- `get_ph_position(sp_elem: Any, slide: Any, ph_cache: dict[tuple[str, int | None], tuple[float, float, float, float, float]] | None=None) -> tuple[float, float, float, float, float] | None` — [строка 127](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pptx_to_html/_renderer.py#L127)
- `get_fill(sp_elem: Any) -> dict[str, Any] | None` — [строка 168](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pptx_to_html/_renderer.py#L168)
- `get_line(sp_elem: Any) -> dict[str, Any] | None` — [строка 207](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pptx_to_html/_renderer.py#L207)
- `build_path_for_prst(prst: str, avLst: Any=None) -> Optional[str]` — [строка 231](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pptx_to_html/_renderer.py#L231)
- `render_shape_svg(sp_elem: Any, width_in: float, height_in: float, xfrm_pos: tuple[float, float, float, float, float], fill_info: dict[str, Any] | None, line_info: dict[str, Any] | None) -> str` — [строка 241](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pptx_to_html/_renderer.py#L241)
- `render_custgeom(cust: Any, width_in: float, height_in: float, fill_info: dict[str, Any] | None, line_info: dict[str, Any] | None) -> str` — [строка 368](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pptx_to_html/_renderer.py#L368)
- `build_arrow_markers(line_info: dict[str, Any] | None) -> str` — [строка 432](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pptx_to_html/_renderer.py#L432)
- `arrow_marker_attrs(line_info: dict[str, Any] | None) -> str` — [строка 445](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pptx_to_html/_renderer.py#L445)
- `render_text_body(txBody_elem: Any, placeholder_type: str | None=None) -> str` — [строка 459](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pptx_to_html/_renderer.py#L459)
- `render_paragraph(p: Any) -> str` — [строка 494](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pptx_to_html/_renderer.py#L494)
- `render_paragraph_with_math(p: Any, align: str, marL: float, indent_first: float, bullet_char: str | None, bullet_color: str | None, bullet_font: str | None) -> str` — [строка 562](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pptx_to_html/_renderer.py#L562)
- `render_run(r: float) -> str` — [строка 666](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pptx_to_html/_renderer.py#L666)
- `run_style(rpr: Any) -> str` — [строка 674](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pptx_to_html/_renderer.py#L674)
- `html_escape(s: str) -> str` — [строка 726](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pptx_to_html/_renderer.py#L726)
- `render_slide(slide: Any, slide_num: int, media_index: dict[str, str], slide_rels: dict[str, str], slide_size_in: tuple[float, float]) -> str` — [строка 733](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pptx_to_html/_renderer.py#L733)
- `render_background(bg: Any, slide_rels: dict[str, str], media_index: dict[str, str], slide_size_in: tuple[float, float]) -> str` — [строка 799](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pptx_to_html/_renderer.py#L799)
- `render_sp(sp: Any, media_index: dict[str, str], slide_rels: dict[str, str], slide: Any=None) -> str` — [строка 825](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pptx_to_html/_renderer.py#L825)
- `render_pic(pic: Any, media_index: dict[str, str], slide_rels: dict[str, str], slide: Any=None) -> str` — [строка 877](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pptx_to_html/_renderer.py#L877)
- `render_grpSp(grp: Any, media_index: dict[str, str], slide_rels: dict[str, str], slide: Any=None) -> str` — [строка 900](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pptx_to_html/_renderer.py#L900)
- `render_graphicFrame(gf: Any, media_index: dict[str, str], slide_rels: dict[str, str], slide: Any=None) -> str` — [строка 982](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pptx_to_html/_renderer.py#L982)
- `render_table(tbl: Any, pos: str, w: float, h: float) -> str` — [строка 1015](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pptx_to_html/_renderer.py#L1015)
- `get_slide_rels(pptx_path: Path, slide_part: Any) -> dict[str, str]` — [строка 1056](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pptx_to_html/_renderer.py#L1056)
- `get_placeholder_xfrm(slide: Any) -> dict[tuple[str, int | None], tuple[float, float, float, float, float]]` — [строка 1066](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pptx_to_html/_renderer.py#L1066)
- `ph_type_to_xml(ph_type: Any) -> str` — [строка 1119](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pptx_to_html/_renderer.py#L1119)
- `convert_pptx(pptx_path: str | Path, out_dir: str | Path) -> None` — [строка 1135](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pptx_to_html/_renderer.py#L1135)
- `extract_title(slide: Any) -> str` — [строка 1185](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pptx_to_html/_renderer.py#L1185)
- `write_index(out: Path, slides_html: list[str], titles: list[str], size: tuple[float, float]) -> None` — [строка 1723](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pptx_to_html/_renderer.py#L1723)
- `write_css(out: Path) -> None` — [строка 1781](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pptx_to_html/_renderer.py#L1781)
- `write_js(out: Path) -> None` — [строка 1785](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pptx_to_html/_renderer.py#L1785)

Импорты: `PIL`, `__future__`, `_omml`, `_pptx_lib`, `lxml`, `opendoc_formats.support.io`, `opendoc_model.units`, `pathlib`, `pptx`, `pptx.enum.shapes`, `typing`

## src/opendoc_formats/writers/pptx_to_html/converter.py

Конвертация .pptx в автономный HTML-просмотрщик.

- `PptxToHtmlConverter` — [строка 32](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pptx_to_html/converter.py#L32)
- `__init__(self, copy_assets: bool=True) -> None` — [строка 46](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pptx_to_html/converter.py#L46)
- `convert(self, input_path: str | Path, output_path: str | Path) -> ConversionResult` — [строка 49](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pptx_to_html/converter.py#L49)
- `convert(input_path: str | Path, output_path: str | Path, **kwargs: Any) -> ConversionResult` — [строка 97](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pptx_to_html/converter.py#L97)

Импорты: `__future__`, `_renderer`, `opendoc_formats.support.artifacts`, `opendoc_formats.support.io`, `opendoc_formats.writers.base`, `pathlib`, `typing`

## src/opendoc_formats/writers/pptx_writer.py

DocumentModel → editable PPTX. One model section becomes one slide.

- `write_pptx_model(document: DocumentModel, output_path: str | Path, *, limits: DocumentLimits | None=None) -> ConversionReport` — [строка 21](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/pptx_writer.py#L21)

Импорты: `__future__`, `opendoc_formats.writers.color_inheritance`, `opendoc_formats.writers.color_preflight`, `opendoc_formats.writers.pptx_chart_writer`, `opendoc_formats.writers.pptx_geometry_writer`, `opendoc_formats.writers.pptx_image_writer`, `opendoc_formats.writers.pptx_objects_writer`, `opendoc_formats.writers.pptx_scene_writer`, `opendoc_formats.writers.pptx_text_writer`, `opendoc_model.diagnostics`, `opendoc_model.document_model`, `opendoc_model.limits`, `pathlib`, `pptx`, `pptx.util`, `typing`

Тесты: [test_pptx_visual_roundtrip.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/readers/test_pptx_visual_roundtrip.py#L1), [test_mathml_decorations.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_mathml_decorations.py#L1), [test_mathml_pptx.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_mathml_pptx.py#L1), [test_pptx_chart_roundtrip.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_pptx_chart_roundtrip.py#L1), [test_pptx_combo_roundtrip.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_pptx_combo_roundtrip.py#L1), [test_pptx_custom_errors.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_pptx_custom_errors.py#L1), [test_pptx_error_directions.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_pptx_error_directions.py#L1), [test_pptx_geometry_roundtrip.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_pptx_geometry_roundtrip.py#L1), [test_pptx_label_roundtrip.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_pptx_label_roundtrip.py#L1), [test_pptx_multiple_trends.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_pptx_multiple_trends.py#L1), [test_pptx_office_regressions.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_pptx_office_regressions.py#L1), [test_pptx_placeholder_roundtrip.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_pptx_placeholder_roundtrip.py#L1), [test_pptx_plot_roundtrip.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_pptx_plot_roundtrip.py#L1), [test_pptx_point_roundtrip.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_pptx_point_roundtrip.py#L1), [test_pptx_statistics_roundtrip.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_pptx_statistics_roundtrip.py#L1), [test_pptx_table_roundtrip.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_pptx_table_roundtrip.py#L1), [test_pptx_text_roundtrip.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_pptx_text_roundtrip.py#L1), [test_pptx_theme_fonts.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_pptx_theme_fonts.py#L1), [test_pptx_trend_forecast.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_pptx_trend_forecast.py#L1), [test_pptx_writer.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_pptx_writer.py#L1)

## src/opendoc_formats/writers/protocols.py

Public protocols for executable document conversion components.

- `DocumentImporter` — [строка 15](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/protocols.py#L15)
- `read(self, input_path: Path) -> DocumentModel` — [строка 18](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/protocols.py#L18)
- `DocumentExporter` — [строка 22](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/protocols.py#L22)
- `write(self, document: DocumentModel, output_path: Path) -> ConversionReport` — [строка 25](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/protocols.py#L25)
- `PathConverter` — [строка 29](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/protocols.py#L29)
- `convert(self, input_path: Path, output_path: Path) -> ConversionReport` — [строка 32](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/protocols.py#L32)
- `ConversionBackend` — [строка 36](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/protocols.py#L36)
- `execute(self, value: ConversionValue, output_path: Path) -> tuple[ConversionValue, ConversionReport | None]` — [строка 39](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/protocols.py#L39)

Импорты: `__future__`, `opendoc_model.diagnostics`, `opendoc_model.document_model`, `pathlib`, `typing`

## src/opendoc_formats/writers/stages.py

Типизированные контракты стадий конверсионного конвейера.

- `StageKind` — [строка 17](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/stages.py#L17)
- `StageContext` — [строка 29](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/stages.py#L29)
- `StageResult` — [строка 37](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/stages.py#L37)
- `ConversionStage` — [строка 45](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/stages.py#L45)
- `execute(self, value: StageValue, context: StageContext) -> StageResult` — [строка 51](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/stages.py#L51)
- `FormatExtension` — [строка 55](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/stages.py#L55)
- `apply_to(self, properties: dict[str, Any]) -> dict[str, Any]` — [строка 65](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/stages.py#L65)
- `from_properties(cls, properties: Any, namespace: str) -> FormatExtension | None` — [строка 69](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/stages.py#L69)

Импорты: `__future__`, `dataclasses`, `enum`, `opendoc_model.diagnostics`, `opendoc_model.document_model`, `pathlib`, `typing`

Тесты: [test_html_layout.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_html_layout.py#L1), [test_html_normalize.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_html_normalize.py#L1), [test_html_resources.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_html_resources.py#L1), [test_pdf_resources.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_pdf_resources.py#L1), [test_pdf_svg_mapping.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_pdf_svg_mapping.py#L1), [test_stages.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/writers/test_stages.py#L1)

## src/opendoc_formats/writers/text_render.py

Text extraction-result rendering, independent of application operations.

- `render_latex(*, text: Text, title: str='Document', author: str='Author') -> str` — [строка 16](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/text_render.py#L16)
- `render_latex_pandoc(*, text: Text, input_path: Union[str, Path, None]=None) -> str` — [строка 79](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/text_render.py#L79)
- `render_docx(*, text: Text, output_path: Union[str, Path]) -> Path` — [строка 121](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/text_render.py#L121)

Импорты: `__future__`, `docx`, `opendoc_formats.support.artifacts`, `opendoc_formats.support.io`, `opendoc_formats.support.latex`, `opendoc_formats.types`, `pathlib`, `typing`

Тесты: [test_full_contract.py](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/tests/test_full_contract.py#L1)

## src/opendoc_formats/writers/txt_writer.py

UTF-8 plain-text export with explicit flattening diagnostics.

- `write_txt_model(document: od.DocumentModel, output_path: str | Path, *, profile: TextProfile | None=None) -> od.ConversionReport` — [строка 16](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/writers/txt_writer.py#L16)

Импорты: `__future__`, `collections.abc`, `opendoc_formats.support.io`, `opendoc_formats.text_profile`, `opendoc_model.diagnostics`, `opendoc_model.document_model`, `pathlib`
