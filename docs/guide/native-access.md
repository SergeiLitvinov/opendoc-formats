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

Текстовые API восстанавливают исходный ключ `Rotate`, включая отсутствие
и наследование, даже после ошибки backend. Снимки принадлежат Formats;
автоматическая семантическая проекция глифов в Model и полный C-PDF-01 остаются
в [TODO](../development/todo.md).

### Исходные матрицы размещения

`pdf.page_text_placements(index)` возвращает неизменяемый `tuple[PdfTextPlacement, ...]`
из native text device. Каждый occurrence сохраняет `operation` (`fill`, `stroke`,
`ignore`, `clip`, `clip-stroke`), font name, SHA-256 использованных движком font
program bytes либо null, локальную opacity callback и `PdfPlacedGlyph`.
`occurrence_index` нумерует только выбранные text span observations; это не общий
PDF paint seqno. Раздельные fill/stroke и Unicode continuations не объединяются.

Глиф содержит исходные `unicode`, `glyph_id`, точную affine-матрицу `transform`
и `glyph_bbox`. Матрица переводит native glyph-local координаты в неповёрнутые
координаты страницы MuPDF в пунктах: `x'=a*x+c*y+e`, `y'=b*x+d*y+f`.
Она уже включает text matrix, CTM и Form XObject matrix; восстановление по bbox
или font size не выполняется. Нормализацию glyph-local пространства при переносе
в другой движок должен подтвердить потребитель для соответствующей программы шрифта.

`glyph_bbox` — граница формы, вычисленная движком с этой матрицей; stroke extents,
clipping, группы и итоговая видимость не входят в неё. Native glyph id `<0`
сохраняется как sentinel и имеет `glyph_bbox=null`; он не становится вторым
физическим глифом или предположенным ID предыдущего символа. Определение кластеров
и семантических диапазонов — отдельная работа адаптера. SHA-256 относится к
программе, реально использованной MuPDF, включая возможную встроенную/замещённую;
он не доказывает наличие этих bytes во входном PDF или известный face index.
Автоматической привязки по имени семейства нет.

Метод наблюдает `page contents`, без annotation appearances. Callback opacity не
является суммарной прозрачностью групп; порядок callback не объявляется порядком
чтения. Цвет, stroke state, clip/group/layer и полная семантика PDF остаются
отдельными наблюдениями/задачами. Метод не добавляет зависимости к extra `pdf`.

`max_text_spans` ограничивает число occurrences, `max_text_chars` — число native
glyph records, включая continuations. `max_text_metadata_bytes` ограничивает сумму
UTF-8 compact JSON записей: `[page, occurrence, operation, font, digest, opacity]`
и `[unicode, glyph_id, transform, glyph_bbox]` для каждого glyph. Проверка glyph/
metadata budget выполняется до копирования программы шрифта. `max_object_bytes`
ограничивает одну font buffer copy и снимок page dictionary; `max_inspection_bytes`
ограничивает сумму разных font program copies за вызов. Повторная программа
хешируется один раз; native FONT wrapper удерживается только до завершения вызова.

Отмена проверяется в callback между span/глифами и до/после native call. Ошибки
переносятся за C callback boundary без сохранения заимствованных span/item ссылок;
частичный результат не возвращается, Rotate восстанавливается. Квоты ограничивают
собственную обработку/копирование; native интерпретатор может продолжать работу
после отказа callback, поэтому это не жёсткий лимит его времени или памяти.

Проекция `PdfTextPlacement` в общие Model layouts и использование их writer
остаются в C-PDF-01. Импорт PDF использует `PdfTextSpan` для привязки текстовых
фрагментов к операциям рисования. Требуется единственное точное совпадение текста,
исходной позиции и подходящего шрифта. Два совпадения, например отдельные fill/stroke
одного текста, не объединяются в одно доказательство. Отсутствующий или неверный
Unicode, включая U+FFFD, не восстанавливается предположением.

Если привязка не подтверждена, свойства фрагмента содержат `pdf_paint_unknown=true`
и `pdf_paint_unknown_reason`: `empty-semantic-text`, `no-exact-native-match`,
`unmapped-native-unicode` либо `ambiguous-native-match`. Причина сохраняется через
JSON. Повторное сопоставление снимает прежние признаки paint, прежде чем записать
новый результат; остальные свойства фрагмента сохраняются. Ссылка на FONT
назначается только при однозначной привязке всех сопоставленных символов к одной
программе шрифта. Это проверка происхождения paint-признаков, а не полная карта
семантического соответствия и не доказательство итоговой видимости текста.

Для этой стадии `DocumentLimits.max_nodes` ограничивает число нативных span,
а `max_bytes` — число glyph records и отдельно объём их metadata в compact JSON.
Это конечные квоты обработки, а не оценка памяти backend. Отмена проверяется
внутри обхода глифов, кандидатов и привязок шрифтов; превышение квоты сообщает
адрес `$.sections[index].pdf_text_paint`. Нативный вызов получения trace остаётся
непрерываемым внутри backend.

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
