# Нативный доступ к документам

Текстовые snapshots DOCX включают run tabs и `w:noBreakHyphen` как `-`;
настройки tab stops текстом не являются. Исходный no-break token сохраняется
при вставке перед ним или после него. Текст ячейки разделяет абзацы `\n`, включая
пустые; для структуры используйте `paragraph_ids` и merge flags.
Границы приёмки, строгий отказ и режим осмотра `.rels` без владельца описаны в
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

Достаточно extra `docx-native` (только lxml); extra `docx` также подходит.
`docx-native` не включает богатый импорт/экспорт Model через python-docx.
Условия lxml и его XSL-ресурсов остаются в силе:
[лицензии профиля](dependencies.md#лицензия-каждого-профиля).
Снимки содержат роли частей, порядок body, текст и диапазоны runs,
стили, таблицы/строки/ячейки, ширину сетки, объединения и признаки сложного содержимого.
`package.relationships` содержит неизменяемые `RelationshipSnapshot` в порядке
ZIP/XML: part, index в списке дочерних elements/comments/PI (с нуля), Id, Type, Target, эффективный
TargetMode, nominal_source_part, source_part, owner_status, target_part и tuple
всех XML attributes (namespace-qualified names). Attributes сохраняют отличие
отсутствующего TargetMode от явного Internal. Это значения XML infoset; точные
исходные XML bytes остаются в пакете.

`owner_status` различает package root, физически существующий part и missing.
Owner выводится из имени `.rels` в конечном физическом профиле; URI aliases не
восстанавливают его по похожему имени. Literal percent в физическом owner name
не декодируется повторно. Для External и missing-owner `target_part=None`:
инвентарь не выполняет URL и не объявляет неподтверждённую связь выбранной.
Обычный Internal с установленным owner имеет физическую цель конечного URI binder.
Это native source facts Formats, не переносимая ссылка/codec Model или полный
C-MAP-01. Правило source URI и отдельное разрешение Target —
[OPC Fundamentals, Microsoft](https://learn.microsoft.com/en-us/previous-versions/windows/desktop/opc/open-packaging-conventions-overview).

`DocxLimits.max_relationships` ограничивает суммарное число relationships всех
parts, включая package relationships (default 100000). Квота не сбрасывается на
каждой `.rels`; callback проверяется между объектами. Остальные input/XML/part
лимиты сохраняются. После close доступ через package закрыт; уже полученные
value snapshots остаются независимыми. Текстовая правка не меняет эти source facts.
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

Внутренние relationship targets декодируются из percent-escaped UTF-8 строго и
один раз. Некорректный escape даёт `InvalidDocumentError`; неизвестный non-UTF-8
профиль — `UnsupportedDocumentError`. Адрес ошибки содержит `.rels`, Id и `@Target`.
Повреждённая последовательность не заменяется символом `�` и не связывается с
другой ZIP-частью. Корректные Unicode escapes, `%25` и `%252F` сохраняют прежнюю
семантику одного декодирования; настоящий `�`, записанный `%EF%BF%BD`, допустим.
Правило действует и в inspection_only. External targets остаются инертными
метаданными и не становятся проверенными или загруженными URL. Это конечный
профиль нативного DOCX API, не полная нормализация всех OPC URI.

Главный officeDocument target и соответствующий content-type Override используют
тот же native resolver. Поддержаны однозначные UTF-8/percent aliases, literal
Unicode и относительные dot segments; escaped ZIP-имя может сохраняться буквально,
если decoded имя отсутствует. Например, `word/own%20doc.xml` связывается либо с
единственной `word/own doc.xml`, либо с единственной literal `word/own%20doc.xml`.
Если в архиве есть обе разные части, `UnsupportedDocumentError` сообщает ambiguity:
предпочтение одной формы не угадывается. Для выбранной главной части требуется
ровно один Override; duplicate aliases не перезаписывают друг друга.

Resolver сохраняет фактическое ZIP-имя в part/IDs и не переписывает ни URI, ни
имена архива. Native edit меняет только выбранную главную XML-часть; остальные
parts сохраняют bytes. Encoded `/` и `\\` остаются явным unsupported профилем,
decoded controls/scheme и выход за корень запрещены; external targets не открываются.
Root target, Override и обычные internal relationships имеют source locations
при отказе. Это не общий DTO Model и не полная OPC/IRI нормализация.

### Осмотр пакета с relationships без владельца

По умолчанию `.rels` без физического source part даёт `InvalidDocumentError`
с именем relationship part и отсутствующим владельцем. Для ограниченного чтения
такого оригинала доступен явный `inspection_only=True`:

```python
with DocxPackage("source.docx", inspection_only=True) as package:
    for issue in package.info.issues:
        print(issue.severity.value, issue.feature, issue.location, issue.message)
    paragraphs = package.paragraphs
    original_bytes = package.to_bytes()
```

`info.inspection_only` отмечает режим; `info.issues` — неизменяемый tuple общих
`opendoc_model.ConversionIssue`. Каждая orphan relationship part получает ERROR
`docx.orphan-relationships`, исходный location и сообщение с отсутствующим source.
Это отсутствующий физический owner в конечном профиле, не полная проверка URI-
эквивалентности/валидности OPC и не восстановление владельца. Связи не активируются
и не удаляются; snapshots остаются
физическими, исходный ZIP возвращается без правок.

В этом режиме `write()` запрещён даже без patches; `to_bytes(patches)` тоже
запрещён. Обычный пакет в inspection_only имеет тот же запрет — режим нельзя
обойти отсутствием замечаний. `to_bytes()` без patches доступен в прежнем output
budget. DTD/entities, некорректные `.rels`, Id/TargetMode, опасные/отсутствующие
internal targets, макросы без allow_macros, ZIP/XML policy, лимиты и отмена
остаются отказами. Внешние targets не загружаются. Богатый Model reader и
семантика редактирования повреждённого пакета этим режимом не заменяются.

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

Рабочий семантический PDF reader использует этот же ограниченный обработчик
для сопоставления FONT resources с нарисованным текстом. Отдельного обхода
MuPDF для этой привязки нет. Сохраняется конечная fill-only политика: совпасть
должны реальная программа, Unicode и округлённый до 0.001 pt origin; имя семейства
не является доказательством. Совпадающие программы в разных ресурсах не выбираются
произвольно. Stroke/clip/ignore не превращаются в fill-привязку.
Этот потребитель получает матрицы без вычисления glyph outlines; полный
`PdfDocument.page_text_placements` сохраняет прежние `glyph_bbox` observations.

Для static standalone OTF с одной CFF1 программой допускается точное совпадение
native buffer с таблицей `CFF ` внутри ресурса: собственный sfnt reader подтверждает
границы и SHA-256 таблицы, CFF1 header/Name INDEX ограничивают профиль одним font.
Variable/CFF2 и несколько подходящих контейнеров остаются неподтверждёнными.
Это связь исходных bytes и glyph ID, не полная валидация CFF или shaping.

В этом рабочем пути на каждой странице `DocumentLimits.max_nodes` ограничивает число native spans,
`max_bytes` применяется отдельно к glyph records/metadata и native font-buffer copies,
`max_embedded_bytes` — исходные FONT payload. Для таблиц OTF действует также предел
`min(4096, max_nodes)`. Превышения дают `ArtifactLimitError` с path/quota/maximum;
отмена проверяется внутри обработчика, поворот страницы восстанавливается при отказе.
Квоты не ограничивают внутренние выделения MuPDF до callback и не прерывают
произвольный native call в любой момент. Типизированные Model TextLayout создаются
только в явно выбранном режиме наблюдений; C-PDF-01 остаётся открытым.

### TextLayout в Model

```python
from opendoc_formats import ImportOptions, read_document, write_document
from opendoc_model import get_integration

result = read_document("source.pdf", options=ImportOptions(pdf_text_layouts=True))
if result.success:
    layouts = get_integration(result.document).text_layouts
    write_document(result.document, "observations.json")
```

Прямой reader принимает `read_pdf_model(path=..., capture_text_layouts=True)`.
По умолчанию оба режима выключены. Режим сохраняет отдельные native fill/stroke/
ignore/clip occurrences как публичные Model `TextLayout`, матрицы и доказанные
FONT/face. Для standalone static TTF и однозначного OTF/CFF известен face 0;
отсутствующий или неоднозначный источник, variable/font-set face не угадываются.
Неизвестный glyph ID записывается как None, а не как допустимый номер другого face.

При точном единственном совпадении исходного Unicode, позиции, полного стиля
и явно выбранной FONT-программы создаются logical ranges/clusters и snapshot
`state="verified"`, `binding_version=2`. Лигатура `fi` связывает один физический
глиф с двумя кодовыми точками. Native continuation `-1` принимается только после
физического глифа с той же матрицей; неизвестный Unicode, близкая позиция,
изменённый стиль, отсутствующая FONT-ссылка или несколько владельцев остаются
`unknown`, без выдуманной связи. Это подтверждение logical mapping, а полный
paint/visibility state остаётся `unassessed`.

Native sentinel/Unicode continuation не становится вторым физическим глифом:
исходный PDF сохраняется как ATTACHMENT с SHA-256,
в extra layout остаются source resource ID и индексы физических native records.
Оригинальный PDF и низкоуровневый Formats API сохраняют неподтверждённые Unicode,
sentinels, clip/group/paint данные. В Model не вводится отдельный private glyph codec.

Для известной геометрии `layout.transform` переводит crop-local координаты MuPDF
в общий page frame `x=PDF x, y=-PDF y`. Rotation хранится в PageGeometry отдельно.
Для неподтверждённого frame (например, UserUnit вне поддержанного профиля)
`page_id=None`; остаются native local matrices и provenance, без выдуманного
преобразования к странице. Имена backend/version и причина неизвестного binding
сохраняются как форматные extra. Это не доказательство reading order или видимости.

Снимок источника и FONT payload вместе подчиняются `max_embedded_bytes`.
Native spans/records ограничены `max_nodes` на странице и совокупно; полный
Model budget проверяется публичными setters. Нативные allocations до callback
по-прежнему не являются жёстко ограниченными. Возвращается подготовленная копия;
отмена или ошибка не оставляют частично добавленный layout в исходной модели.
Повторный захват того же источника не дублирует pages, layouts или snapshot.
Anchors/ranges и неизвестные extra сохраняются. После правки текста или стиля
публичный getter Model возвращает `stale`; повторное чтение исходного PDF
не подтверждает изменённого владельца и заменяет свою связь на `unknown`.
Связи других producers проходят обычную проверку Model и не инвалидируются молча.
Некорректные общие диапазоны после сокращения/удаления текста требуют отдельной
правки или remap; захват не удаляет их ради обхода validation.

JSON переносит наблюдения через публичный codec Model. PDF/DOCX/HTML и другие
writer без поддержки TextLayout возвращают `export.text-layout` до замены файла.
Для обычной конвертации используется стандартный импорт без этого режима.
Remap после split/merge, остальные logical profiles и native writer projection
остаются в C-PDF-01. [Проверки режима](../development/pdf-text-layout-capture-evidence.json).

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
