# Нативный доступ к документам

Текстовые snapshots DOCX включают run tabs и `w:noBreakHyphen` как `-`;
настройки tab stops текстом не являются. Исходный no-break token сохраняется
при вставке перед ним или после него. Текст ячейки разделяет абзацы `\n`, включая
пустые; для структуры используйте `paragraph_ids` и merge flags.
Границы приёмки и отказ на `.rels` без владельца описаны в
[C-DOCX-NATIVE-TEXT-01](../development/format-requests.md#c-docx-native-text-01).

Библиотека предоставляет операции над исходным DOCX и страницами PDF.
Они нужны, когда переход через модель OpenDoc изменил бы исходное оформление.
Публичные результаты — неизменяемые типизированные снимки и байты PNG;
объекты движков, ZIP и XML остаются внутри библиотеки.

## DOCX: снимки и транзакция

```python
from opendoc_formats.docx import DocxPackage, ReplaceTextSpan

with DocxPackage("source.docx") as package:
    paragraph = next(p for p in package.paragraphs if p.is_body and "Hello" in p.text)
    start = paragraph.text.index("Hello")
    patch = ReplaceTextSpan(paragraph.id, start, start + 5, "Привет\nмир")
    result = package.write("edited.docx", [patch])
    print(result.changed_parts, result.sha256)
```

Нужен extra `docx`. Снимки содержат роли частей, порядок body, текст и диапазоны runs,
стили, таблицы/строки/ячейки, ширину сетки, объединения и признаки сложного содержимого.
ID и Unicode-диапазоны относятся к первоначальному состоянию пакета. Несколько правок
применяются одной транзакцией; пересечения и неоднозначные вставки отвергаются.

`SetParagraphText` заменяет или дописывает текст с сохранением свойств абзаца и первого run.
`InsertParagraph` вставляет обычный body-абзац. `InsertTableRow` создаёт строку из одной
ячейки на всю ширину сетки; `SetTableRowText` обновляет такую строку.
Строки с фигурными скобками — обычный текст. Распознавание маркеров принадлежит потребителю.
Поля, revisions и вложенные абзацы защищены от небезопасной замены. Полная замена абзаца
с рисунком, формулой или другим сложным markup отклоняется; допустимый текстовый span
можно изменить, сохранив соседний объект.

Без правок `to_bytes()` возвращает исходный архив побайтно. При правках неизменённые
части сохраняют содержимое и SHA-256, порядок, метаданные записей ZIP и комментарий.
Сжатое представление контейнера может измениться. Подписанный пакет можно прочитать,
но редактирование отклоняется. Макросы запрещены по умолчанию; `allow_macros=True`
разрешает сохранение без выполнения. DTD/entities запрещены, сетевые обращения отсутствуют.
Проверяются OPC-отношения, пути, CRC, дубликаты, размеры и коэффициент сжатия.

## PDF: один контекст для страниц

```python
from opendoc_formats.pdf import PdfDocument

with PdfDocument("source.pdf") as pdf:
    info = pdf.page_info(0)
    rendered = pdf.render_page(0, dpi=144, max_dimension=2048)
    print(info.text, rendered.width, rendered.height, rendered.effective_scale)
```

Нужен extra `pdf`. Источник — путь или bytes. Индексы нулевые; размеры страницы в PDF-points.
`dpi` и `scale` взаимоисключающие; дополнительный поворот задаётся `rotation`.
Размер и число пикселей ограничиваются до рендера. `effective_scale` — фактические пиксели
на point: при OCR без дополнительного поворота координаты делятся на это значение.
При дополнительном повороте потребителю также нужно учитывать преобразование координат.
Ограниченный кэш удерживает только заданное количество PNG и байтов; закрытие освобождает его.
Библиотека не выполняет OCR и не оценивает визуальное качество.

Extra `pdf-text` устанавливает только pypdf для текстового маршрута `readers.pdf.read_pdf`.
Для геометрии, `PdfDocument` и рендера нужен `pdf` или эквивалентный `pdf-rich` с одним PyMuPDF.

### Исходные глифы и paint spans

`pdf.page_text_spans(index)` возвращает неизменяемый `tuple[PdfTextSpan, ...]`.
Каждый span содержит номер страницы/наблюдения, native `seqno`, тип отрисовки,
font name/size, bbox, direction, opacity и `PdfGlyphInfo` с Unicode codepoint,
font-dependent glyph id, origin и bbox. Координаты наблюдаются на неповёрнутой
странице; поворот не применяется к ним повторно. Остальные scalar/flat-sequence
метаданные backend, включая color, flags, wmode, bidi, layer и linewidth,
сохраняются в неизменяемом `metadata`; вложенные объекты вне профиля дают отказ.

`span.text` — только последовательность Unicode backend. Недопустимый scalar
даёт null; U+FFFD сохраняется, а отсутствующий Unicode не угадывается.
Ligature continuation с glyph id `-1` и нулевым bbox не удаляется. Наблюдения
filled/stroked одного текста не объединяются. Порядок span/глифов не объявляется
порядком чтения, а bbox/opacity не доказывают окончательную видимость с учётом
clipping, layers, compositing или последующих paint operations. Метод наблюдает
страницу в scope backend, не объявляя её исключительно основным текстом без appearances.

`PdfLimits.max_text_spans` ограничивает число span, `max_text_chars` — сумму
glyph records страницы. `max_text_metadata_bytes` ограничивает сумму UTF-8 bytes
compact JSON metadata объектов без `chars`, включая основные поля span;
`max_object_bytes` — снимок словаря страницы для восстановления rotation.
Проверки отмены действуют между span/глифами и до/после native call.
Backend сначала материализует trace: эти квоты не являются жёстким ограничением
его памяти, времени или возможностью прервать native call посередине.

Оба текстовых API восстанавливают исходный ключ `Rotate`, включая отсутствие
и наследование, даже после ошибки backend. Снимки принадлежат Formats;
автоматическая семантическая проекция глифов в Model и полный C-PDF-01 остаются
в [TODO](../development/todo.md).

## Офис → PDF

```python
from opendoc_formats.office import convert_office_to_pdf, find_libreoffice

if find_libreoffice() is not None:
    result = convert_office_to_pdf("source.docx", "preview.pdf", timeout=60)
```

LibreOffice устанавливается отдельно; для проверки результата нужен extra `pdf`.
Поддерживаются DOC/DOCX/DOTX, ODT/RTF, PPT/PPTX/ODP, XLS/XLSX/ODS.
Каждый запуск получает временный каталог и собственный профиль. Профиль выключает
макросы и активное содержимое согласно настройкам
[LibreOffice](https://raw.githubusercontent.com/LibreOffice/core/master/officecfg/registry/schema/org/openoffice/Office/Common.xcs).
Это изоляция профиля, а не файловая или сетевая песочница процесса.
При отмене/таймауте завершается собственное дерево процессов, временные файлы удаляются.
Готовый PDF проверяется перед атомарной заменой назначения; ошибка сохраняет прежний файл.
Кэши приложения и политика качества преобразования принадлежат потребителю.

## Ресурсы и ошибки

`assemble_docx_package_resources` принимает официальную `DocumentModel` и отображение
ID ресурсов в стандартные роли DOCX. Возвращает копию; существующий граф сохраняется.
Выбранные встроенные байты и отношения собираются в граф OpenDoc без схемы приложения,
загрузки URI и выполнения содержимого. Это сборка ресурсов, а не проверка семантики XML.

`DocxLimits`, `PdfLimits`, `OfficeLimits` задают конечные бюджеты; точные defaults — в
[справочнике API](../reference/api.md). `NativeAccessError` объединяет ошибки с полем `code`:
движок недоступен, документ повреждён/зашифрован, содержимое не поддержано, лимит,
отмена, закрытый документ, индекс, конфликт правок и таймаут.
Callback `cancelled` проверяется между операциями и непосредственно перед публикацией.
Он не прерывает выполняющийся внутри вызова сторонний парсер или рендерер.
Текст/PNG ограничиваются после получения от движка; размеры растра — до получения.

[Контракт](../development/native-access-contract.md) ·
[Проверенные возможности](format-audit.md) · [Оставшиеся задачи](../development/todo.md)
