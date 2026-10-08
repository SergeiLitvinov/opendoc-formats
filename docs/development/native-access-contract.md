# Контракт нативного доступа

Владелец операций форматов — OpenDoc Formats. Общая модель используется из OpenDoc Model 0.7.2.
Пакет не принимает схемы приложения, условия шаблонов, задачи или настройки Web.
Любая строка, включая фигурные скобки, является обычным текстом.

## PDF: `opendoc_formats.pdf`

- `PdfDocument(source: str | Path | bytes, *, limits=PdfLimits(), cancelled=None)` —
  контекстный менеджер; движок импортируется при открытии. `close()` идемпотентен.
- `page_count: int`; `page_info(index: int) -> PdfPageInfo`:
  `index`, `width`, `height`, `rotation`, `text`.
- `render_page(index, *, dpi=None, scale=None, max_dimension=None, rotation=0)
  -> RenderedPage`: `png: bytes`, `width: int`, `height: int`, `index: int`,
  `effective_scale: float` — фактические пиксели на PDF-point после ограничения размера.
  Для OCR без дополнительного поворота координаты делятся на `effective_scale`.
  Индексы нулевые. DPI и scale взаимоисключающие. Размер ограничивается до рендера.
  Один открытый документ допускает текст/растры одной страницы без повторного открытия;
  ограниченный кэш повторного рендера принадлежит контексту, освобождается при закрытии.
- Нет публичных объектов PyMuPDF. Есть различимые ошибки отсутствующего движка,
  повреждения, шифрования, индекса, лимита, отмены и закрытого документа.
  Проверки отмены проходят перед/после вызова движка, не прерывают его внутри.

## Офис → PDF: `opendoc_formats.office`

- `find_libreoffice() -> Path | None`.
- `convert_office_to_pdf(source, output, *, executable=None, timeout=180,
  limits=OfficeLimits(), cancelled=None) -> OfficeConversionResult`.
- Отдельные временные каталог и профиль, ограниченный ввод/вывод, проверка PDF,
  атомарная замена результата после проверки и отмены. Нет кэша задач приложения.
  Ошибки движка/времени/повреждения диагностируются библиотекой.

## DOCX: `opendoc_formats.docx`

- `DocxPackage(source: str | Path | bytes, *, limits=DocxLimits(),
  allow_macros=False, cancelled=None)` — контекстный менеджер, снимки неизменяемы.
- `paragraphs: tuple[ParagraphSnapshot, ...]`: `id`, `part`, `index`, `text`, `runs`,
  привязка к таблице/ячейке, признаки body, изображений, разрыва секции и вложенных абзацев.
  Идентификатор — исходная часть и порядковый индекс; действителен для одной ревизии пакета.
- `body: tuple[BodyItem, ...]`: порядок и тип элемента, ID абзаца/таблицы, текст.
- `tables: tuple[TableSnapshot, ...]`: ID/часть/индекс, сетка, строки и ячейки,
  ID абзацев, текст, объединения, вложенные таблицы и разрывы секций.
- Снимки содержат только строки, числа, bool и типизированные неизменяемые структуры.
  ZIP, XML, namespace и backend objects не входят в контракт.

Точные определения типов уже находятся в `src/opendoc_formats/docx.py`, PDF — в `pdf.py`.
Каждый снимок абзаца/таблицы имеет семантическую `role`: `body`, `header`, `footer`,
`footnote`, `endnote`, `other`. Потребителю не нужно распознавать пути частей.
Абзац: `has_image`, `has_section_break`, `has_nested_paragraphs`, `has_fields`,
`has_revisions`, `has_embedded_objects`, `is_body`, `in_table`.
Строка: `simple`, `has_merge`, `has_nested_tables`, `has_section_break`, `paragraph_ids`.
`BackendUnavailableError` является `ImportError`; ошибки документа/лимитов/неподдержанного
содержимого являются `ValueError`. Все ошибки принадлежат `opendoc_formats.errors`,
имеют стабильное поле `code`.
- `ReplaceTextSpan(paragraph_id, start, end, text)` заменяет диапазон исходного текста,
  включая split runs; стиль вне диапазона сохраняется, вставка наследует первый run диапазона.
- `SetParagraphText(paragraph_id, text, append=False)` сохраняет свойства абзаца
  и стиль первого run. Полная замена сложного содержимого отвергается, а не теряет его молча.
- `InsertParagraph(anchor_id, text, position='before')` вставляет обычный body-абзац
  перед/после выбранного; обновление существующего выполняется `SetParagraphText`.
- `InsertTableRow(anchor_row_id, text, position='before')` вставляет простую строку
  из одной ячейки на ширину сетки. `SetTableRowText(row_id, text)` обновляет такую строку.
  Библиотека не распознаёт смысл маркеров; выбор и проверка их содержимого — у потребителя.
- `to_bytes(patches=()) -> bytes`; `write(output, patches=()) -> DocxEditResult`.
  Все patches относятся к исходным снимкам и применяются одной транзакцией. Исходник не меняется.
  Непересекающиеся span patches применяются справа налево; неоднозначные/конфликтующие правки
  отвергаются. Нет частичного результата при ошибке или отмене.
- Без правок возвращаются исходные байты. При правках неизменённые части сохраняются побайтно,
  информация записей ZIP и комментарий пакета сохраняются. Сжатый контейнер может отличаться.
  Макросы запрещены по умолчанию; при явном разрешении сохраняются без выполнения.
  XML разбирается без DTD/entities/network. Валидируются пути, дубликаты, CRC, размеры,
  коэффициент сжатия и пригодность частей до атомарной записи.

## Ресурсы DOCX: `opendoc_formats.package_resources`

`assemble_docx_package_resources(document, resource_roles, *, consume_resources=False,
max_bytes=128*1024*1024, cancelled=None) -> DocumentModel` возвращает копию официальной модели.
`resource_roles` — отображение `{resource_id: role}`, где role: `footnotes`, `endnotes`,
`numbering`, `styles`, `theme`, `media`. Стандартные пути и URI отношений выбирает библиотека.
Существующий package graph сохраняется. `consume_resources=True` удаляет из копии ресурсы,
переданные в граф; исходный документ не меняется. Необязательные native metadata `partname`
и `relationships` обрабатываются внутри библиотеки; формат/версия JSON потребителя не принимаются.
Невстроенные/неизвестные ресурсы, конфликт частей, некорректные связи или лимит — ошибка.
Ничего не скачивается и не выполняется.

## Приёмка и граница интеграции

Реальные PDF/DOCX fixtures и созданные сложные документы проверяют split runs,
колонтитулы, таблицы/объединения, многострочный текст, рисунки/формулы, SHA-256 частей,
свойства ZIP, ошибки/лимиты/отмену. Изолированная установка без extras проверяет ленивость.
Документ фиксирует контракт нативных операций. Сигнатуры генерируются из исходников в
[API](../reference/api.md); примеры и ограничения — в [руководстве](../guide/native-access.md).
Владелец оставшихся запросов: [реестр OF01–OF05](format-requests.md),
[подтверждённые задачи](todo.md), [исследования](research.md).
Разделение приложения проверяется в его собственном проекте.
