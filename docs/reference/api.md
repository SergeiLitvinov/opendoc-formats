# Публичный API

Создан автоматически из AST публичных модулей библиотеки.
Модель и отчёты определены в обязательном пакете OpenDoc.

## opendoc_formats.api

### ImportOptions

[Исходник, строка 17](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/api.py#L17)

| Поле | Тип | Значение по умолчанию |
| --- | --- | --- |
| `max_input_bytes` | `int` | `10 * 1024 * 1024` |
| `resource_root` | `str &#124; Path &#124; None` | `None` |
| `document_limits` | `DocumentLimits` | `field(default_factory=DocumentLimits)` |
| `pdf_mode` | `str` | `'fast'` |
| `ocr_engine_factory` | `Callable[..., object] &#124; None` | `None` |
| `cancelled` | `Callable[[], bool] &#124; None` | `None` |

### ImportResult

[Исходник, строка 41](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/api.py#L41)

| Поле | Тип | Значение по умолчанию |
| --- | --- | --- |
| `document` | `DocumentModel &#124; None` | `обязательное` |
| `format_id` | `str` | `обязательное` |
| `issues` | `tuple[DiagnosticIssue, ...]` | `()` |

### ImportResult.success

[Исходник, строка 47](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/api.py#L47)

```python
success(self) -> bool
```

### ImportResult.assessment_complete

[Исходник, строка 51](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/api.py#L51)

```python
assessment_complete(self) -> bool
```

### ImportResult.lossless

[Исходник, строка 62](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/api.py#L62)

```python
lossless(self) -> bool
```

### AdapterSpec

[Исходник, строка 79](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/api.py#L79)

| Поле | Тип | Значение по умолчанию |
| --- | --- | --- |
| `id` | `str` | `обязательное` |
| `extensions` | `tuple[str, ...]` | `обязательное` |
| `reader` | `Reader` | `обязательное` |
| `requirements` | `tuple[str, ...]` | `()` |

### AdapterRegistry

[Исходник, строка 99](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/api.py#L99)

### AdapterRegistry.__init__

[Исходник, строка 100](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/api.py#L100)

```python
__init__(self) -> None
```

### AdapterRegistry.register

[Исходник, строка 104](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/api.py#L104)

```python
register(self, adapter: AdapterSpec) -> None
```

### AdapterRegistry.adapters

[Исходник, строка 112](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/api.py#L112)

```python
adapters(self) -> tuple[AdapterSpec, ...]
```

### AdapterRegistry.read

[Исходник, строка 115](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/api.py#L115)

```python
read(self, path: str | Path, *, format_id: str | None=None, options: ImportOptions | None=None) -> ImportResult
```

### default_registry

[Исходник, строка 202](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/api.py#L202)

```python
default_registry() -> AdapterRegistry
```

### read_document

[Исходник, строка 215](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/api.py#L215)

```python
read_document(path: str | Path, *, format_id: str | None=None, options: ImportOptions | None=None) -> ImportResult
```

## opendoc_formats.export

### ExportOptions

[Исходник, строка 19](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/export.py#L19)

| Поле | Тип | Значение по умолчанию |
| --- | --- | --- |
| `document_limits` | `DocumentLimits` | `field(default_factory=DocumentLimits)` |
| `cancelled` | `Callable[[], bool] &#124; None` | `None` |
| `verify_output` | `bool` | `True` |

### ExporterSpec

[Исходник, строка 38](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/export.py#L38)

| Поле | Тип | Значение по умолчанию |
| --- | --- | --- |
| `id` | `str` | `обязательное` |
| `extensions` | `tuple[str, ...]` | `обязательное` |
| `writer` | `Writer` | `обязательное` |
| `requirements` | `tuple[str, ...]` | `()` |
| `validator` | `OutputValidator &#124; None` | `None` |

### ExporterRegistry

[Исходник, строка 61](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/export.py#L61)

### ExporterRegistry.__init__

[Исходник, строка 62](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/export.py#L62)

```python
__init__(self) -> None
```

### ExporterRegistry.register

[Исходник, строка 66](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/export.py#L66)

```python
register(self, exporter: ExporterSpec) -> None
```

### ExporterRegistry.exporters

[Исходник, строка 74](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/export.py#L74)

```python
exporters(self) -> tuple[ExporterSpec, ...]
```

### ExporterRegistry.write

[Исходник, строка 77](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/export.py#L77)

```python
write(self, document: DocumentModel, path: str | Path, *, format_id: str | None=None, options: ExportOptions | None=None) -> ConversionReport
```

### default_exporter_registry

[Исходник, строка 157](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/export.py#L157)

```python
default_exporter_registry() -> ExporterRegistry
```

### write_document

[Исходник, строка 180](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/export.py#L180)

```python
write_document(document: DocumentModel, path: str | Path, *, format_id: str | None=None, options: ExportOptions | None=None) -> ConversionReport
```

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

[Исходник, строка 22](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/pdf.py#L22)

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

### PdfPageInfo

[Исходник, строка 38](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/pdf.py#L38)

| Поле | Тип | Значение по умолчанию |
| --- | --- | --- |
| `index` | `int` | `обязательное` |
| `width` | `float` | `обязательное` |
| `height` | `float` | `обязательное` |
| `rotation` | `int` | `обязательное` |
| `text` | `str` | `обязательное` |

### RenderedPage

[Исходник, строка 47](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/pdf.py#L47)

| Поле | Тип | Значение по умолчанию |
| --- | --- | --- |
| `index` | `int` | `обязательное` |
| `png` | `bytes` | `обязательное` |
| `width` | `int` | `обязательное` |
| `height` | `int` | `обязательное` |
| `effective_scale` | `float` | `обязательное` |

### PdfDocument

[Исходник, строка 55](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/pdf.py#L55)

### PdfDocument.__init__

[Исходник, строка 58](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/pdf.py#L58)

```python
__init__(self, source: Source, *, limits: PdfLimits=PdfLimits(), cancelled: Cancellation | None=None) -> None
```

### PdfDocument.close

[Исходник, строка 98](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/pdf.py#L98)

```python
close(self) -> None
```

### PdfDocument.closed

[Исходник, строка 106](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/pdf.py#L106)

```python
closed(self) -> bool
```

### PdfDocument.page_count

[Исходник, строка 115](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/pdf.py#L115)

```python
page_count(self) -> int
```

### PdfDocument.page_info

[Исходник, строка 130](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/pdf.py#L130)

```python
page_info(self, index: int) -> PdfPageInfo
```

### PdfDocument.render_page

[Исходник, строка 142](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/pdf.py#L142)

```python
render_page(self, index: int, *, dpi: float | None=None, scale: float | None=None, max_dimension: int | None=None, rotation: float=0) -> RenderedPage
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
