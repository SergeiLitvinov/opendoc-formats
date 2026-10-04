# Свои обработчики

Реестры создаются отдельно для каждого потребителя; глобального изменяемого реестра нет.
ID и расширения должны быть уникальны, расширения — с точкой и в нижнем регистре.
`requirements` перечисляет имена импортируемых Python-модулей движка.

## Импорт

```python
from pathlib import Path
from opendoc import DocumentModel, Paragraph, Section, TextRun
from opendoc_formats import AdapterSpec, ImportOptions, default_registry

def read_note(path: Path, options: ImportOptions) -> DocumentModel:
    return DocumentModel(sections=[Section(blocks=[Paragraph([TextRun(path.read_text(encoding="utf-8"))])])])

registry = default_registry()
registry.register(AdapterSpec("note", (".note",), read_note))
result = registry.read("message.note")
```

Обработчик возвращает именно `DocumentModel`. Реестр валидирует результат с выбранными лимитами.
Дополнительные свойства модели должны быть JSON-совместимыми; NaN, бинарные данные и объекты
сторонних библиотек нельзя класть в metadata/properties. Ресурсы помещаются в ресурсы модели.

## Экспорт

```python
from pathlib import Path
from opendoc import ConversionReport, DocumentModel
from opendoc_formats import ExporterSpec, default_exporter_registry

def write_note(document: DocumentModel, path: Path) -> ConversionReport:
    text = "\n".join(block.plain_text for section in document.sections for block in section.blocks if hasattr(block, "plain_text"))
    path.write_text(text, encoding="utf-8")
    return ConversionReport(path)

def verify_note(path: Path) -> None:
    path.read_text(encoding="utf-8")

registry = default_exporter_registry()
registry.register(ExporterSpec("note", (".note",), write_note, validator=verify_note))
```

Писатель получает путь временного файла в каталоге назначения. Он должен создать **один файл**
и вернуть `ConversionReport`; потери добавляются как `IssueSeverity.LOSS`.
Validator возвращает None при успехе и поднимает исключение при ошибке.
Реестр отвечает за валидацию входной модели, отмену и атомарную публикацию.
Для каталогов и нескольких артефактов используйте отдельный конвертер со своим контрактом.
