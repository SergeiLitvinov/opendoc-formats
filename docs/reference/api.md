# Публичный API

Создан автоматически из AST публичных модулей библиотеки.
Модель и отчёты преобразования определены в обязательном пакете OpenDoc.
Нативные снимки и результаты препарирования принадлежат Formats.

## opendoc_formats.api

### ImportOptions

[Исходник, строка 19](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/api.py#L19)

| Поле | Тип | Значение по умолчанию |
| --- | --- | --- |
| `max_input_bytes` | `int` | `10 * 1024 * 1024` |
| `resource_root` | `str &#124; Path &#124; None` | `None` |
| `document_limits` | `DocumentLimits` | `field(default_factory=DocumentLimits)` |
| `pdf_mode` | `str` | `'fast'` |
| `ocr_engine_factory` | `Callable[..., object] &#124; None` | `None` |
| `cancelled` | `Callable[[], bool] &#124; None` | `None` |
| `txt_profile` | `TextProfile` | `field(default_factory=TextProfile)` |
| `epub_include_nonlinear` | `bool` | `False` |

### ImportResult

[Исходник, строка 49](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/api.py#L49)

| Поле | Тип | Значение по умолчанию |
| --- | --- | --- |
| `document` | `DocumentModel &#124; None` | `обязательное` |
| `format_id` | `str` | `обязательное` |
| `issues` | `tuple[DiagnosticIssue, ...]` | `()` |
| `document_limits` | `DocumentLimits` | `field(default_factory=DocumentLimits, repr=False, compare=False)` |

### ImportResult.success

[Исходник, строка 56](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/api.py#L56)

```python
success(self) -> bool
```

### ImportResult.assessment_complete

[Исходник, строка 60](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/api.py#L60)

```python
assessment_complete(self) -> bool
```

### ImportResult.lossless

[Исходник, строка 71](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/api.py#L71)

```python
lossless(self) -> bool
```

### AdapterSpec

[Исходник, строка 88](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/api.py#L88)

| Поле | Тип | Значение по умолчанию |
| --- | --- | --- |
| `id` | `str` | `обязательное` |
| `extensions` | `tuple[str, ...]` | `обязательное` |
| `reader` | `Reader` | `обязательное` |
| `requirements` | `tuple[str, ...]` | `()` |

### AdapterRegistry

[Исходник, строка 108](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/api.py#L108)

### AdapterRegistry.__init__

[Исходник, строка 109](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/api.py#L109)

```python
__init__(self) -> None
```

### AdapterRegistry.register

[Исходник, строка 113](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/api.py#L113)

```python
register(self, adapter: AdapterSpec) -> None
```

### AdapterRegistry.adapters

[Исходник, строка 121](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/api.py#L121)

```python
adapters(self) -> tuple[AdapterSpec, ...]
```

### AdapterRegistry.read

[Исходник, строка 124](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/api.py#L124)

```python
read(self, path: str | Path, *, format_id: str | None=None, options: ImportOptions | None=None) -> ImportResult
```

### default_registry

[Исходник, строка 235](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/api.py#L235)

```python
default_registry() -> AdapterRegistry
```

### read_document

[Исходник, строка 249](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/api.py#L249)

```python
read_document(path: str | Path, *, format_id: str | None=None, options: ImportOptions | None=None) -> ImportResult
```

## opendoc_formats.export

### ExportOptions

[Исходник, строка 23](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/export.py#L23)

| Поле | Тип | Значение по умолчанию |
| --- | --- | --- |
| `document_limits` | `DocumentLimits` | `field(default_factory=DocumentLimits)` |
| `cancelled` | `Callable[[], bool] &#124; None` | `None` |
| `verify_output` | `bool` | `True` |
| `txt_profile` | `TextProfile &#124; None` | `None` |
| `quality_gate` | `Callable[[ConversionReport, Path], bool] &#124; None` | `None` |
| `docx_profile` | `DocxProfile &#124; None` | `None` |

### ExporterSpec

[Исходник, строка 71](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/export.py#L71)

| Поле | Тип | Значение по умолчанию |
| --- | --- | --- |
| `id` | `str` | `обязательное` |
| `extensions` | `tuple[str, ...]` | `обязательное` |
| `writer` | `Writer` | `обязательное` |
| `requirements` | `tuple[str, ...]` | `()` |
| `validator` | `OutputValidator &#124; None` | `None` |

### ExporterRegistry

[Исходник, строка 94](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/export.py#L94)

### ExporterRegistry.__init__

[Исходник, строка 95](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/export.py#L95)

```python
__init__(self) -> None
```

### ExporterRegistry.register

[Исходник, строка 99](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/export.py#L99)

```python
register(self, exporter: ExporterSpec) -> None
```

### ExporterRegistry.exporters

[Исходник, строка 107](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/export.py#L107)

```python
exporters(self) -> tuple[ExporterSpec, ...]
```

### ExporterRegistry.write

[Исходник, строка 110](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/export.py#L110)

```python
write(self, document: DocumentModel, path: str | Path, *, format_id: str | None=None, options: ExportOptions | None=None) -> ConversionReport
```

### default_exporter_registry

[Исходник, строка 354](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/export.py#L354)

```python
default_exporter_registry() -> ExporterRegistry
```

### write_document

[Исходник, строка 378](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/export.py#L378)

```python
write_document(document: DocumentModel, path: str | Path, *, format_id: str | None=None, options: ExportOptions | None=None) -> ConversionReport
```

## opendoc_formats.text_profile

### TextProfile

[Исходник, строка 17](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/text_profile.py#L17)

| Поле | Тип | Значение по умолчанию |
| --- | --- | --- |
| `encoding` | `str` | `'auto'` |
| `bom` | `str` | `'auto'` |
| `newline` | `str` | `'preserve'` |

### TextEncodingError

[Исходник, строка 35](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/text_profile.py#L35)

### TextEncodingError.__init__

[Исходник, строка 36](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/text_profile.py#L36)

```python
__init__(self, reason: str, message: str) -> None
```

### decode_text

[Исходник, строка 41](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/text_profile.py#L41)

```python
decode_text(data: bytes, profile: TextProfile) -> tuple[str, str, bool]
```

### normalize_newlines

[Исходник, строка 69](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/text_profile.py#L69)

```python
normalize_newlines(text: str) -> str
```

### source_profile

[Исходник, строка 74](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/text_profile.py#L74)

```python
source_profile(text: str, encoding: str, bom: bool) -> dict[str, Any]
```

### encode_text

[Исходник, строка 79](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/text_profile.py#L79)

```python
encode_text(text: str, profile: TextProfile, original: dict[str, Any]) -> tuple[bytes, dict[str, Any], bool]
```

## opendoc_formats.docx_profile

### DocxProfile

[Исходник, строка 7](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/docx_profile.py#L7)

| Поле | Тип | Значение по умолчанию |
| --- | --- | --- |
| `layout` | `str` | `'preserve'` |

## opendoc_formats.docx

### DocxLimits

[Исходник, строка 17](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/docx.py#L17)

| Поле | Тип | Значение по умолчанию |
| --- | --- | --- |
| `max_input_bytes` | `int` | `100 * 1024 * 1024` |
| `max_output_bytes` | `int` | `128 * 1024 * 1024` |
| `max_entries` | `int` | `3000` |
| `max_uncompressed_bytes` | `int` | `200 * 1024 * 1024` |
| `max_part_bytes` | `int` | `32 * 1024 * 1024` |
| `max_compression_ratio` | `int` | `1000` |
| `max_paragraphs` | `int` | `100000` |
| `max_patches` | `int` | `10000` |
| `max_text_chars` | `int` | `4000000` |

### RunStyle

[Исходник, строка 34](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/docx.py#L34)

| Поле | Тип | Значение по умолчанию |
| --- | --- | --- |
| `bold` | `bool &#124; None` | `None` |
| `italic` | `bool &#124; None` | `None` |
| `underline` | `bool &#124; None` | `None` |
| `font_family` | `str &#124; None` | `None` |
| `font_size` | `float &#124; None` | `None` |
| `style_id` | `str &#124; None` | `None` |

### RunSnapshot

[Исходник, строка 44](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/docx.py#L44)

| Поле | Тип | Значение по умолчанию |
| --- | --- | --- |
| `start` | `int` | `обязательное` |
| `end` | `int` | `обязательное` |
| `text` | `str` | `обязательное` |
| `style` | `RunStyle` | `обязательное` |

### ParagraphSnapshot

[Исходник, строка 52](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/docx.py#L52)

| Поле | Тип | Значение по умолчанию |
| --- | --- | --- |
| `id` | `str` | `обязательное` |
| `part` | `str` | `обязательное` |
| `role` | `PartRole` | `обязательное` |
| `index` | `int` | `обязательное` |
| `text` | `str` | `обязательное` |
| `runs` | `tuple[RunSnapshot, ...]` | `обязательное` |
| `is_body` | `bool` | `обязательное` |
| `table_id` | `str &#124; None` | `обязательное` |
| `cell_id` | `str &#124; None` | `обязательное` |
| `has_image` | `bool` | `обязательное` |
| `has_section_break` | `bool` | `обязательное` |
| `has_nested_paragraphs` | `bool` | `обязательное` |
| `has_fields` | `bool` | `обязательное` |
| `has_revisions` | `bool` | `обязательное` |
| `has_embedded_objects` | `bool` | `обязательное` |
| `style_id` | `str &#124; None` | `обязательное` |

### ParagraphSnapshot.in_table

[Исходник, строка 71](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/docx.py#L71)

```python
in_table(self) -> bool
```

### BodyItem

[Исходник, строка 76](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/docx.py#L76)

| Поле | Тип | Значение по умолчанию |
| --- | --- | --- |
| `index` | `int` | `обязательное` |
| `kind` | `Literal['paragraph', 'table', 'section', 'other']` | `обязательное` |
| `paragraph_id` | `str &#124; None` | `обязательное` |
| `table_id` | `str &#124; None` | `обязательное` |
| `text` | `str` | `обязательное` |

### CellSnapshot

[Исходник, строка 85](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/docx.py#L85)

| Поле | Тип | Значение по умолчанию |
| --- | --- | --- |
| `id` | `str` | `обязательное` |
| `index` | `int` | `обязательное` |
| `text` | `str` | `обязательное` |
| `paragraph_ids` | `tuple[str, ...]` | `обязательное` |
| `grid_span` | `int` | `обязательное` |
| `vertical_merge` | `bool` | `обязательное` |
| `horizontal_merge` | `bool` | `обязательное` |
| `has_nested_tables` | `bool` | `обязательное` |

### RowSnapshot

[Исходник, строка 97](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/docx.py#L97)

| Поле | Тип | Значение по умолчанию |
| --- | --- | --- |
| `id` | `str` | `обязательное` |
| `index` | `int` | `обязательное` |
| `cells` | `tuple[CellSnapshot, ...]` | `обязательное` |
| `text` | `str` | `обязательное` |
| `paragraph_ids` | `tuple[str, ...]` | `обязательное` |
| `has_merge` | `bool` | `обязательное` |
| `has_nested_tables` | `bool` | `обязательное` |
| `has_section_break` | `bool` | `обязательное` |
| `simple` | `bool` | `обязательное` |

### TableSnapshot

[Исходник, строка 110](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/docx.py#L110)

| Поле | Тип | Значение по умолчанию |
| --- | --- | --- |
| `id` | `str` | `обязательное` |
| `part` | `str` | `обязательное` |
| `role` | `PartRole` | `обязательное` |
| `index` | `int` | `обязательное` |
| `grid_columns` | `int` | `обязательное` |
| `rows` | `tuple[RowSnapshot, ...]` | `обязательное` |
| `is_body` | `bool` | `обязательное` |
| `parent_cell_id` | `str &#124; None` | `обязательное` |

### PackagePartInfo

[Исходник, строка 122](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/docx.py#L122)

| Поле | Тип | Значение по умолчанию |
| --- | --- | --- |
| `name` | `str` | `обязательное` |
| `role` | `PartRole` | `обязательное` |
| `size` | `int` | `обязательное` |
| `sha256` | `str` | `обязательное` |

### DocxPackageInfo

[Исходник, строка 130](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/docx.py#L130)

| Поле | Тип | Значение по умолчанию |
| --- | --- | --- |
| `sha256` | `str` | `обязательное` |
| `parts` | `tuple[PackagePartInfo, ...]` | `обязательное` |
| `has_macros` | `bool` | `обязательное` |
| `has_signatures` | `bool` | `обязательное` |

### ReplaceTextSpan

[Исходник, строка 138](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/docx.py#L138)

| Поле | Тип | Значение по умолчанию |
| --- | --- | --- |
| `paragraph_id` | `str` | `обязательное` |
| `start` | `int` | `обязательное` |
| `end` | `int` | `обязательное` |
| `text` | `str` | `обязательное` |

### SetParagraphText

[Исходник, строка 146](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/docx.py#L146)

| Поле | Тип | Значение по умолчанию |
| --- | --- | --- |
| `paragraph_id` | `str` | `обязательное` |
| `text` | `str` | `обязательное` |
| `append` | `bool` | `False` |

### InsertParagraph

[Исходник, строка 153](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/docx.py#L153)

| Поле | Тип | Значение по умолчанию |
| --- | --- | --- |
| `anchor_id` | `str` | `обязательное` |
| `text` | `str` | `обязательное` |
| `position` | `Position` | `'before'` |

### InsertTableRow

[Исходник, строка 160](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/docx.py#L160)

| Поле | Тип | Значение по умолчанию |
| --- | --- | --- |
| `anchor_row_id` | `str` | `обязательное` |
| `text` | `str` | `обязательное` |
| `position` | `Position` | `'before'` |

### SetTableRowText

[Исходник, строка 167](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/docx.py#L167)

| Поле | Тип | Значение по умолчанию |
| --- | --- | --- |
| `row_id` | `str` | `обязательное` |
| `text` | `str` | `обязательное` |

### DocxEditResult

[Исходник, строка 176](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/docx.py#L176)

| Поле | Тип | Значение по умолчанию |
| --- | --- | --- |
| `output` | `Path` | `обязательное` |
| `sha256` | `str` | `обязательное` |
| `bytes_written` | `int` | `обязательное` |
| `changed_parts` | `tuple[str, ...]` | `обязательное` |

### DocxPackage

[Исходник, строка 183](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/docx.py#L183)

### DocxPackage.__init__

[Исходник, строка 186](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/docx.py#L186)

```python
__init__(self, source: Source, *, limits: DocxLimits=DocxLimits(), allow_macros: bool=False, cancelled: Cancellation | None=None) -> None
```

### DocxPackage.close

[Исходник, строка 211](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/docx.py#L211)

```python
close(self) -> None
```

### DocxPackage.closed

[Исходник, строка 215](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/docx.py#L215)

```python
closed(self) -> bool
```

### DocxPackage.paragraphs

[Исходник, строка 219](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/docx.py#L219)

```python
paragraphs(self) -> tuple[ParagraphSnapshot, ...]
```

### DocxPackage.body

[Исходник, строка 224](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/docx.py#L224)

```python
body(self) -> tuple[BodyItem, ...]
```

### DocxPackage.tables

[Исходник, строка 229](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/docx.py#L229)

```python
tables(self) -> tuple[TableSnapshot, ...]
```

### DocxPackage.info

[Исходник, строка 234](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/docx.py#L234)

```python
info(self) -> DocxPackageInfo
```

### DocxPackage.to_bytes

[Исходник, строка 238](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/docx.py#L238)

```python
to_bytes(self, patches: Sequence[DocxPatch]=()) -> bytes
```

### DocxPackage.write

[Исходник, строка 242](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/docx.py#L242)

```python
write(self, output: str | Path, patches: Sequence[DocxPatch]=()) -> DocxEditResult
```

## opendoc_formats.pdf

### PdfLimits

[Исходник, строка 24](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/pdf.py#L24)

| Поле | Тип | Значение по умолчанию |
| --- | --- | --- |
| `max_input_bytes` | `int` | `128 * 1024 * 1024` |
| `max_pages` | `int` | `10000` |
| `max_dimension` | `int` | `8192` |
| `max_pixels` | `int` | `16000000` |
| `max_png_bytes` | `int` | `32 * 1024 * 1024` |
| `max_text_chars` | `int` | `4000000` |
| `cache_bytes` | `int` | `32 * 1024 * 1024` |
| `cache_pages` | `int` | `8` |
| `max_objects` | `int` | `100000` |
| `max_object_bytes` | `int` | `32 * 1024 * 1024` |
| `max_inspection_bytes` | `int` | `256 * 1024 * 1024` |
| `max_text_spans` | `int` | `100000` |
| `max_text_metadata_bytes` | `int` | `8 * 1024 * 1024` |

### PdfPageInfo

[Исходник, строка 45](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/pdf.py#L45)

| Поле | Тип | Значение по умолчанию |
| --- | --- | --- |
| `index` | `int` | `обязательное` |
| `width` | `float` | `обязательное` |
| `height` | `float` | `обязательное` |
| `rotation` | `int` | `обязательное` |
| `text` | `str` | `обязательное` |

### RenderedPage

[Исходник, строка 54](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/pdf.py#L54)

| Поле | Тип | Значение по умолчанию |
| --- | --- | --- |
| `index` | `int` | `обязательное` |
| `png` | `bytes` | `обязательное` |
| `width` | `int` | `обязательное` |
| `height` | `int` | `обязательное` |
| `effective_scale` | `float` | `обязательное` |

### PdfGlyphInfo

[Исходник, строка 63](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/pdf.py#L63)

| Поле | Тип | Значение по умолчанию |
| --- | --- | --- |
| `unicode` | `int` | `обязательное` |
| `glyph_id` | `int` | `обязательное` |
| `origin` | `tuple[float, float]` | `обязательное` |
| `bbox` | `tuple[float, float, float, float]` | `обязательное` |

### PdfTextSpan

[Исходник, строка 75](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/pdf.py#L75)

| Поле | Тип | Значение по умолчанию |
| --- | --- | --- |
| `page_index` | `int` | `обязательное` |
| `span_index` | `int` | `обязательное` |
| `seqno` | `int` | `обязательное` |
| `paint_type` | `int` | `обязательное` |
| `font` | `str` | `обязательное` |
| `font_size` | `float` | `обязательное` |
| `bbox` | `tuple[float, float, float, float]` | `обязательное` |
| `direction` | `tuple[float, float]` | `обязательное` |
| `opacity` | `float` | `обязательное` |
| `glyphs` | `tuple[PdfGlyphInfo, ...]` | `обязательное` |
| `metadata` | `tuple[tuple[str, PdfTextValue], ...]` | `()` |

### PdfTextSpan.text

[Исходник, строка 89](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/pdf.py#L89)

```python
text(self) -> str | None
```

### PdfObjectInfo

[Исходник, строка 97](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/pdf.py#L97)

| Поле | Тип | Значение по умолчанию |
| --- | --- | --- |
| `xref` | `int` | `обязательное` |
| `dictionary` | `str` | `обязательное` |
| `raw_stream` | `bytes &#124; None` | `обязательное` |

### PdfDocument

[Исходник, строка 105](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/pdf.py#L105)

### PdfDocument.__init__

[Исходник, строка 108](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/pdf.py#L108)

```python
__init__(self, source: Source, *, limits: PdfLimits=PdfLimits(), cancelled: Cancellation | None=None) -> None
```

### PdfDocument.close

[Исходник, строка 148](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/pdf.py#L148)

```python
close(self) -> None
```

### PdfDocument.closed

[Исходник, строка 156](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/pdf.py#L156)

```python
closed(self) -> bool
```

### PdfDocument.page_count

[Исходник, строка 165](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/pdf.py#L165)

```python
page_count(self) -> int
```

### PdfDocument.object_count

[Исходник, строка 170](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/pdf.py#L170)

```python
object_count(self) -> int
```

### PdfDocument.trailer

[Исходник, строка 179](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/pdf.py#L179)

```python
trailer(self) -> str
```

### PdfDocument.repaired

[Исходник, строка 188](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/pdf.py#L188)

```python
repaired(self) -> bool
```

### PdfDocument.iter_objects

[Исходник, строка 192](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/pdf.py#L192)

```python
iter_objects(self) -> Iterator[PdfObjectInfo]
```

### PdfDocument.page_info

[Исходник, строка 231](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/pdf.py#L231)

```python
page_info(self, index: int) -> PdfPageInfo
```

### PdfDocument.page_text_spans

[Исходник, строка 246](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/pdf.py#L246)

```python
page_text_spans(self, index: int) -> tuple[PdfTextSpan, ...]
```

### PdfDocument.render_page

[Исходник, строка 278](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/pdf.py#L278)

```python
render_page(self, index: int, *, dpi: float | None=None, scale: float | None=None, max_dimension: int | None=None, rotation: float=0) -> RenderedPage
```

## opendoc_formats.anatomy

### AnatomyLimits

[Исходник, строка 31](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/anatomy.py#L31)

| Поле | Тип | Значение по умолчанию |
| --- | --- | --- |
| `max_input_bytes` | `int` | `128 * 1024 * 1024` |
| `max_items` | `int` | `100000` |
| `max_part_bytes` | `int` | `32 * 1024 * 1024` |
| `max_total_bytes` | `int` | `256 * 1024 * 1024` |
| `max_ratio` | `int` | `200` |
| `max_xml_nodes` | `int` | `100000` |
| `max_xml_depth` | `int` | `128` |
| `max_xml_name_chars` | `int` | `2048` |
| `max_xml_characters` | `int` | `32 * 1024 * 1024` |

### XmlNodeInfo

[Исходник, строка 48](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/anatomy.py#L48)

| Поле | Тип | Значение по умолчанию |
| --- | --- | --- |
| `path` | `str` | `обязательное` |
| `tag` | `str` | `обязательное` |
| `attributes` | `tuple[tuple[str, str], ...]` | `обязательное` |
| `text_sha256` | `str` | `обязательное` |
| `text_characters` | `int` | `0` |
| `start_byte` | `int` | `0` |
| `end_event_byte` | `int` | `0` |

### BinaryItem

[Исходник, строка 59](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/anatomy.py#L59)

| Поле | Тип | Значение по умолчанию |
| --- | --- | --- |
| `locator` | `str` | `обязательное` |
| `kind` | `str` | `обязательное` |
| `size` | `int` | `обязательное` |
| `sha256` | `str` | `обязательное` |
| `storage_sha256` | `str &#124; None` | `None` |
| `details` | `tuple[tuple[str, Any], ...]` | `()` |
| `xml_nodes` | `tuple[XmlNodeInfo, ...]` | `()` |
| `payload` | `bytes &#124; None` | `field(default=None, repr=False, compare=False)` |

### OpcRelationship

[Исходник, строка 71](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/anatomy.py#L71)

| Поле | Тип | Значение по умолчанию |
| --- | --- | --- |
| `location` | `str` | `обязательное` |
| `relationship_part` | `str` | `обязательное` |
| `owner` | `str &#124; None` | `обязательное` |
| `attributes` | `tuple[tuple[str, str], ...]` | `обязательное` |
| `resolved_target` | `str &#124; None` | `обязательное` |
| `status` | `str` | `обязательное` |

### OpcFinding

[Исходник, строка 81](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/anatomy.py#L81)

| Поле | Тип | Значение по умолчанию |
| --- | --- | --- |
| `code` | `str` | `обязательное` |
| `location` | `str` | `обязательное` |
| `message` | `str` | `обязательное` |

### OpcAudit

[Исходник, строка 88](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/anatomy.py#L88)

| Поле | Тип | Значение по умолчанию |
| --- | --- | --- |
| `relationships` | `tuple[OpcRelationship, ...]` | `обязательное` |
| `findings` | `tuple[OpcFinding, ...]` | `обязательное` |
| `reachable_parts` | `tuple[str, ...]` | `обязательное` |
| `unreached_parts` | `tuple[str, ...]` | `обязательное` |
| `unreachable_parts` | `tuple[str, ...]` | `обязательное` |
| `reachability_complete` | `bool` | `обязательное` |

### OpcAudit.to_dict

[Исходник, строка 96](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/anatomy.py#L96)

```python
to_dict(self) -> dict[str, Any]
```

### EpubManifestReference

[Исходник, строка 108](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/anatomy.py#L108)

| Поле | Тип | Значение по умолчанию |
| --- | --- | --- |
| `location` | `str` | `обязательное` |
| `package` | `str` | `обязательное` |
| `identifier` | `str` | `обязательное` |
| `href` | `str` | `обязательное` |
| `media_type` | `str` | `обязательное` |
| `resolved_target` | `str &#124; None` | `обязательное` |
| `status` | `str` | `обязательное` |
| `attributes` | `tuple[tuple[str, str], ...]` | `обязательное` |

### EpubAudit

[Исходник, строка 120](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/anatomy.py#L120)

| Поле | Тип | Значение по умолчанию |
| --- | --- | --- |
| `references` | `tuple[EpubManifestReference, ...]` | `обязательное` |

### EpubAudit.to_dict

[Исходник, строка 123](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/anatomy.py#L123)

```python
to_dict(self) -> dict[str, Any]
```

### BinarySnapshot

[Исходник, строка 132](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/anatomy.py#L132)

| Поле | Тип | Значение по умолчанию |
| --- | --- | --- |
| `container` | `str` | `обязательное` |
| `source_sha256` | `str` | `обязательное` |
| `source_size` | `int` | `обязательное` |
| `items` | `tuple[BinaryItem, ...]` | `обязательное` |
| `details` | `tuple[tuple[str, Any], ...]` | `()` |
| `opc` | `OpcAudit &#124; None` | `None` |
| `epub` | `EpubAudit &#124; None` | `None` |

### BinarySnapshot.to_dict

[Исходник, строка 141](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/anatomy.py#L141)

```python
to_dict(self) -> dict[str, Any]
```

### compare_snapshots

[Исходник, строка 160](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/anatomy.py#L160)

```python
compare_snapshots(before: BinarySnapshot, after: BinarySnapshot) -> dict[str, Any]
```

### inspect_binary

[Исходник, строка 401](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/anatomy.py#L401)

```python
inspect_binary(source: Source, *, container: str | None=None, limits: AnatomyLimits=AnatomyLimits(), parse_xml: bool=True, capture: bool=False, cancelled: Callable[[], bool] | None=None) -> BinarySnapshot
```

## opendoc_formats.office

### OfficeLimits

[Исходник, строка 41](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/office.py#L41)

| Поле | Тип | Значение по умолчанию |
| --- | --- | --- |
| `max_input_bytes` | `int` | `100 * 1024 * 1024` |
| `max_output_bytes` | `int` | `128 * 1024 * 1024` |
| `max_pages` | `int` | `10000` |

### OfficeConversionResult

[Исходник, строка 52](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/office.py#L52)

| Поле | Тип | Значение по умолчанию |
| --- | --- | --- |
| `output` | `Path` | `обязательное` |
| `page_count` | `int` | `обязательное` |
| `bytes_written` | `int` | `обязательное` |
| `sha256` | `str` | `обязательное` |

### find_libreoffice

[Исходник, строка 59](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/office.py#L59)

```python
find_libreoffice() -> Path | None
```

### convert_office_to_pdf

[Исходник, строка 88](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/office.py#L88)

```python
convert_office_to_pdf(source: str | Path, output: str | Path, *, executable: str | Path | None=None, timeout: float=180, limits: OfficeLimits=OfficeLimits(), cancelled: Cancellation | None=None) -> OfficeConversionResult
```

## opendoc_formats.package_resources

### assemble_docx_package_resources

[Исходник, строка 47](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/package_resources.py#L47)

```python
assemble_docx_package_resources(document: DocumentModel, resource_roles: Mapping[str, DocxResourceRole], *, consume_resources: bool=False, max_bytes: int=128 * 1024 * 1024, cancelled: Cancellation | None=None) -> DocumentModel
```

## opendoc_formats.errors

### FormatError

[Исходник, строка 4](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/errors.py#L4)

### ExtractError

[Исходник, строка 8](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/errors.py#L8)

### ConvertError

[Исходник, строка 12](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/errors.py#L12)

### NativeAccessError

[Исходник, строка 16](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/errors.py#L16)

### BackendUnavailableError

[Исходник, строка 22](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/errors.py#L22)

### InvalidDocumentError

[Исходник, строка 28](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/errors.py#L28)

### EncryptedDocumentError

[Исходник, строка 34](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/errors.py#L34)

### UnsupportedDocumentError

[Исходник, строка 40](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/errors.py#L40)

### ResourceLimitError

[Исходник, строка 46](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/errors.py#L46)

### OperationCancelledError

[Исходник, строка 52](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/errors.py#L52)

### DocumentClosedError

[Исходник, строка 58](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/errors.py#L58)

### PageIndexError

[Исходник, строка 64](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/errors.py#L64)

### PatchConflictError

[Исходник, строка 70](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/errors.py#L70)

### OfficeTimeoutError

[Исходник, строка 76](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/errors.py#L76)
