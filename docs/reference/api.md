# Публичный API

Создан автоматически из AST `api.py` и `export.py`.
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

### AdapterSpec

[Исходник, строка 55](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/api.py#L55)

| Поле | Тип | Значение по умолчанию |
| --- | --- | --- |
| `id` | `str` | `обязательное` |
| `extensions` | `tuple[str, ...]` | `обязательное` |
| `reader` | `Reader` | `обязательное` |
| `requirements` | `tuple[str, ...]` | `()` |

### AdapterRegistry

[Исходник, строка 75](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/api.py#L75)

### AdapterRegistry.__init__

[Исходник, строка 76](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/api.py#L76)

```python
__init__(self) -> None
```

### AdapterRegistry.register

[Исходник, строка 80](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/api.py#L80)

```python
register(self, adapter: AdapterSpec) -> None
```

### AdapterRegistry.adapters

[Исходник, строка 88](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/api.py#L88)

```python
adapters(self) -> tuple[AdapterSpec, ...]
```

### AdapterRegistry.read

[Исходник, строка 91](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/api.py#L91)

```python
read(self, path: str | Path, *, format_id: str | None=None, options: ImportOptions | None=None) -> ImportResult
```

### default_registry

[Исходник, строка 146](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/api.py#L146)

```python
default_registry() -> AdapterRegistry
```

### read_document

[Исходник, строка 159](https://github.com/SergeiLitvinov/opendoc-formats/blob/main/src/opendoc_formats/api.py#L159)

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
