# Полнота обработки исходных форматов

«Поддержан» означает наличие конкретного маршрута, а не полный разбор спецификации.
Ни один внешний формат сейчас не имеет гарантии полного семантического импорта и
обратного воспроизведения исходного файла. Нативный JSON сохраняет выразимые данные
модели из `opendoc-model`; он не восстанавливает сведения, потерянные до сериализации.

## Покрытие

| Исходный формат | Реализовано | Неполнота | Задачи |
| --- | --- | --- | --- |
| LaTeX `.tex` | Source-v1 lexer/parser; нативная запись текста, заголовков, структурных списков и TeX-формул без extras; исходные bytes и spans через JSON | Include, macros, таблицы, numbered math, изображения и bibliography вне профиля; DOCX bridge для остальных объектов; неподдержанные списки/формулы отклоняются | OF04 |
| DOCX | Абзацы, runs, стили, таблицы, формулы, ссылки, сноски, колонтитулы, ресурсы и PackageGraph; нативные ограниченные правки | Инвентаризация comments, revisions, content controls, SmartArt/OLE и других сложных объектов не равна их семантической модели и редактированию. Перенос непрозрачных частей имеет ограничения | OF05 |
| PPTX | Текст, таблицы, выбранные диаграммы, фигуры, группы с материализацией координат, фоны, заметки, разрешение части theme/master/layout | Импорт не сохраняет исходный PackageGraph. Нет полного переноса анимаций, аудио/видео, переходов, embedded objects, редактируемой иерархии групп и всего оформления; экспорт создаёт новую презентацию | OF06 |
| PDF | Текст, геометрия, растр, конечный векторный профиль, внедряемый OCR; URI links/notes/highlights/text fields, outline и PageGeometry | Structure tree/tagged PDF, layers, остальные annotations/forms и полный graphics state вне принятого профиля; логический порядок и формулы не гарантированы | OF07 |
| EPUB | Spine с явным режимом nonlinear chapters; абзацы/заголовки/списки/ссылки/изображения, таблицы/MathML, finite CSS; исходные OPF/nav/NCX, font/media assets и SVG удерживаются opaque; собственный конечный EPUB 3 writer | Полная семантика nav/OPF/fixed layout/CSS и media playback не восстановлена. Writer создаёт XHTML spine item на секцию; исходный package не реконструирует. Собственные fixtures проходят pinned EPUBCheck в CI | OF08; конечный writer profile проверен |
| HTML/CSS | Статическая структура, таблицы, списки, ссылки, формулы, локальные ресурсы, ограниченный CSS с диагностикой | Нет полной модели cascade/layout, flex/grid, paged media и accessibility tree. Активное содержимое не выполняется; произвольный DOM после JavaScript не является входом этого парсера | OF10 |
| DjVu | Текст внешним `djvutxt` | Нет страниц, координат слов, растров и оглавления в модели; обратного экспорта нет | OF11 |
| TXT | Конечный TextProfile: UTF-8, UTF-16 LE/BE, явный CP1251; BOM/newlines через JSON и byte roundtrip | Произвольная кодировка не угадывается; это основной текст, без стилей и геометрии | Проверен выбранный профиль |
| JSON OpenDoc | Загрузка, валидация и запись модели, ресурсов и JSON-совместимых расширений | Не универсальный парсер произвольного JSON; данные вне контракта модели требуют явно зарегистрированных расширений | Контракт opendoc-model |
| ODT/ODP/ODS, RTF, DOC/XLS/PPT, XLSX | Офисный preview через LibreOffice для поддержанных расширений | Преобразование в PDF не даёт семантического читателя этих исходных документов | OF13 |
| Markdown / BibTeX | Нет маршрута в публичном реестре | `DocFormat.BIB` сам по себе не обеспечивает парсер библиографии | OF14 |

## Что доказывает сохранение

- **Семантическое:** объект представлен типами или документированным расширением OpenDoc,
  доступен для изменения и имеет проверенный экспорт.
- **Непрозрачное:** сохранены оригинальные байты части пакета; межформатное преобразование
  и редактирование её содержимого из этого не следуют.
- **Визуальное:** `VisualSurrogate` воспроизводит вид, а `Provenance` объясняет замену;
  исходная семантика может быть недоступна.
- **Потерянное:** сведения пропущены или упрощены; диагностический отчёт должен это отражать.

`ImportResult.issues` переносит предупреждения всех читателей и typed ledger OpenDoc.
EPUB уже отмечает конкретные пропуски с reason и source provenance.
Успешный импорт без issues **не доказывает отсутствие потерь**:
`assessment_complete` и `lossless` требуют явной оценки заявленных функций.
Полнота диагностики внутри читателей остаётся задачей OF15.

## Проверяемые основания

Маршруты: `api.default_registry`, `export.default_exporter_registry`.
LaTeX source: `readers/tex_source.py`, `readers/tex_model.py`;
`writers/latex_writer.py` выбирает нативный профиль или DOCX bridge для остальных объектов.
EPUB: `readers/epub_model.py`, ограниченный `_BLOCKS`, фильтр spine и сбор ресурсов.
PPTX: `readers/pptx.py::read_pptx_model` создаёт модель без `package`;
`writers/pptx_writer.py` диагностирует потерю исходного пакета, если он передан.
DOCX: `readers/docx.py` и инвентаризация в `readers/docx_features.py`.
PDF: `readers/pdf.py`, `readers/pdf_images.py`; DjVu: `readers/djvu.py`.

Воспроизводимые проверки существующих границ:
`tests/native/test_format_audit.py` и `tests/test_source_coverage.py`.
Полнота каждого сложного объекта требует собственных fixtures и сравнения после
повторного чтения; эти критерии записаны в [TODO](../development/todo.md).
Происхождение тестовых документов — в [описании корпуса](../development/corpus.md).

Рекомендации для общей модели находятся в [предложениях к OpenDoc](../development/opendoc-proposals.md).

## Диагностика и сохранность

`ImportResult.issues` объединяет metadata warnings всех читателей и typed
preservation ledger OpenDoc, включая повторный импорт JSON. Assessment и lossless
требуют явной завершённой оценки функций; отсутствие warnings её не заменяет.

EPUB сообщает о неподдержанных/нелинейных spine items, missing images,
audio/video playback, object/script и выходах за table/MathML/CSS профиль.
PPTX различает visual preview и lost для неподдержанных объектов и хранит
source XPath, part, shape ID и номер слайда через JSON; отдельно отмечаются
package graph, transitions/timing, группы, media, 3D и пропущенные shapes/images.
DOCX различает opaque и lost для complex fields, comments/revisions/content
controls, text boxes/WordArt, SmartArt/OLE и protection: opaque требует сохранённого
фрагмента или part. Инвентаризация сама по себе не доказывает сохранность.

PDF ledger содержит page/xref и конечные typed interactions; неподдержанные
типы, tagged structure, layers и catalog actions удерживаются opaque в bounded
source PDF. HTML связывает profile losses со строкой/колонкой и блоком, хранит
исходные bytes inert и сообщает о невоссозданных функциях при экспорте.
Внешние assets не объявляются сохранёнными без соответствующих ресурсов.
Полнота диагностики остаётся в OF15; формат отчёта — в
[руководстве](formats.md#отчёт-импорта).

## Нативный TeX

Собственные bounded lexer/parser и writer работают без TeX engine и Office extras.
UTF-8/BOM, текст/акценты/локальные стили, заголовки, списки и inline/display
Formula LATEX проходят JSON вместе с source spans, provenance и точным inert
оригиналом. Неподдержанные commands/environments имеют located opaque diagnostics.

Нативный writer сохраняет обычные абзацы, прямые bold/italic/underline,
Heading 1–5 и нумерованный/ненумерованный вариант исходных section-команд.
Правка и снятие Heading не возвращают legacy роль; спецсимволы остаются текстом.
Официальный C-LIST-02 Model 0.17.0 сохраняет родителей, продолжения без нового
номера, пустые/child-only пункты, start/restart и стабильные ID. Три независимых
оригинала и по два цикла имеют попиксельно одинаковые страницы без изображений.

Formula сохраняет точное выражение, inline/display, fallback, положение среди
текста и самостоятельный block. Правка и удаление проходят два JSON/TeX цикла;
четыре независимых компилируемых примера совпадают попиксельно без image XObjects.
Существующего Formula Model достаточно; TeX syntax/annotations и приёмка
принадлежат Formats. Неподдержанные списки/формулы отказывают без DOCX bridge.
Общая assessment остаётся неполной, точная компоновка произвольного документа
не заявляется. Полный профиль и примеры — в [руководстве LaTeX](latex-source.md).

## Нативный DOCX

Latin theme reference имеет приоритет над literal fallback на одном уровне
каскада; прямое оформление и character style сохраняют свой приоритет.
Собственный заголовок Calibri 12 bold проходит два цикла в Word.
Конечные auto/RGB/unset, defaults/basedOn/paragraph/character, правка и удаление
цвета приняты. LineSpacing сохраняет direct/inherited/defaults для положительных
auto/atLeast/exact; два цикла, нативные правки Word, полные страницы и нулевой
бюджет проверены. Неизвестные объявления дают расположенный отказ.

Три оси paragraph indent, before/after spacing и
keepLines/keepNext/pageBreakBefore/widowControl сохраняют direct/inherited/defaults,
правки, удаления, явные 0/false. Два DOCX/JSON цикла и нативная правка Word
совпадают с оригиналами и независимыми references на полных страницах.
Неизвестные units/направления и непредставимые величины отклоняются по адресу.

Border/BorderSet удерживает шесть сторон таблицы, внешние/диагональные стороны
ячейки, none/nil, правки и удаление. Два цикла сохраняют native attributes;
Word подтверждает шесть single borders, правку double/red и следующий цикл.
WidthMeasure записывает preferred widths таблицы/ячейки с исходными единицами,
правками/удалением и миграцией legacy JSON при публичном импорте. Собственные
таблицы dxa/pct/auto/nil сохраняют текст, страницу и колонки 10/80/10 в Word.
Текст внутри smartTag проходит два цикла; сам smartTag остаётся opaque.

Heading 1–9 переносится через outline levels, наследование и основной текст;
два цикла, смена/снятие роли и сохранение производных стилей проверены в Word.
Header/footer сохраняют source part bindings и редактируемый текст; bytes/targets
всех шести типов проходят два цикла, обычные header/footer открываются в Word.
Конечный opaque SmartArt/OLE профиль удерживает payload parts, previews и
relationship IDs, а неполный граф отклоняет атомарно. Собственные пять узлов
SmartArt и Excel.Sheet.12 проверены в Word 16.0 build 16.0.17932: два цикла,
правка узла/A1, повторное открытие и нулевой бюджет потерь.

Это конечные профили, а не вся семантика сложного DOCX. Детали — в
[компоновке DOCX](docx-layout.md), [описании форматов](formats.md) и
[тестовом корпусе](../development/corpus.md).

## Нативный PPTX

Effective solid background slide/layout/master, редактируемые осевые freeform
paths и отсутствие пустого solidFill для наследуемого текста подтверждены двумя
JSON roundtrip и нативными свойствами PowerPoint. Материализация отдельных
свойств не означает сохранение исходной иерархии фона и полного package graph.
Профиль — в [описании форматов](formats.md#наследуемые-свойства-и-осевые-линии-pptx).

## Нативный PDF

Публичная инспекция native text flow использует измеренный профиль OpenDoc,
нулевой бюджет и явные unknown; pypdf для неё не требуется. Текст маленькой
страницы проходит два PDF/JSON цикла относительно оригинала; native plain text
проверяется перед публикацией, пропуски дают атомарный отказ. Reflow сообщает
LOSS компоновки. Для однозначных OpenType-лигатур ToUnicode восстанавливается
из встроенного GSUB без изменения shaping/пикселей; собственный синтетический
шрифт проверен нативно, неоднозначные соответствия не угадываются.

Конечный vector Form XObject clip сохраняет стек прямоугольных областей через
JSON и native drawing streams. CropBox и четыре поворота дают точный RGB в
MuPDF/Poppler; limits и отмена проверены. Непринятые clips/groups имеют located
LOSS/opaque source и без проверенного surrogate отклоняются.
Annotations/widgets исключаются из page vectors в отдельной несохраняемой копии:
interaction ledger учитывает их отдельно, source bytes не меняются.

URI links, Text notes, highlights и text fields проходят два публичных цикла,
native/typed edit/delete и отмену на восьми вариантах геометрии. Canonical field
tree имеет bounded audit parents/orphans, links/cycles/depth и located opaque
свойств. Строковый DV, repeated fields и default limit проверены; отдельный P
сохраняет различимость widgets при native deduplication. Это аудит конечного
профиля, не полная реконструкция иерархии/inheritance.

Outline сохраняет иерархию, page/external destinations, native extension и opaque
source. Writer сохраняет page points/zoom, базовый вид, безопасные URI и body
paragraph anchors по действительному потоку; правки/удаления управляют записью.
PageGeometry удерживает media/crop до поворота, source coordinate convention,
четвертьобороты и typed crop/rotation edits/deletions. Два цикла сохраняют исходные
области и RGB viewport, включая ненулевые/отрицательные origins; непривязанные
pages и repagination диагностируются.

Позиционированный растр сохраняет повторные xref/inline occurrences, soft mask,
геометрию до viewport crop, четвертьобороты и отдельный масштаб осей. Конечный
affine с shear/reflection и single-image quadrilateral clip проходит два цикла
с точным RGB. Inline image следует потоку; нулевые offsets paragraph anchor
имеют flow fallback с located LOSS для floating wrap. Mixed paint order диагностируется.
Подробности и границы — в [описании форматов](formats.md) и
[корпусе PDF](../development/corpus.md#pdf-размещения-растра-и-обрезка).

## PDF → OpenDoc → DOCX

Кандидат использует общий SDK без переноса форматной логики в Model.
Конечные собственные примеры подтверждают редактируемый текст, встроенный
неустановленный шрифт, два DOCX/JSON цикла и восемь сочетаний поворотов текста
и страницы в Word относительно исходника. Нативная правка и Word compatibility
replica не дублируют текст. Профиль включает native merges/borders,
многострочные/безрамочные cells, повороты/отражения/alpha/repeated raster,
JPEG без перекодирования, сканы и измеренные наложения; он используется общим Model writer.

Form XObject хранит отдельные paint scopes, вложенные rectangular/cubic clips,
even-odd holes и повторные transforms. Raster bytes/alpha сохраняются;
сложная обрезка имеет отдельный SVG без растра страницы. C-GRAPHICS-01/02
подключены через официальный scene API: clip/group/color-space edits/deletions
не восстанавливаются из native properties, частично скрытая строка хранится целиком.

Конечные RGB opacity и 12 separable blend режимов прямоугольных групп имеют
аналитическую SVG-проекцию. В DOCX это один visual object, поэтому LOSS структуры
сохраняется и строгий конвертер отказывает. Конечный WPC/WPG профиль сохраняет
одноуровневые RGB-прямоугольники, children/order, собственную alpha и осевые
transforms; Word подтверждает отдельную правку CanvasItems/GroupItems.
Независимый Word-оригинал и два цикла после нативной правки совпадают попиксельно
без image XObjects. Произвольные группы этим не приняты.

C-FONT-01 связывает глифы с программами по native bytes, DOCX восстанавливает
ссылки из font table. Одинаковые family/variant, правка, наследование и два цикла
проверены. SDK владеет codec/validation/cascade; PDF extraction, Word relationships
и внутренние имена остаются в Formats. Профиль и ограничения редактора — в
[руководстве кандидата](docx-layout.md#pdf-opendoc-docx-рабочий-кандидат).
Удаление pdf2docx требует всей приёмки OF17; принятые частные случаи её не заменяют.

## EPUB, HTML и DjVu

EPUB переносит tables/captions/rowspan/colspan/nested tables и MathML Formula,
сохраняя mixed cell порядок через JSON и HTML. Standalone images импортируются;
SVG и исходные font/audio/video bytes удерживаются inert. Явный include_nonlinear
сохраняет linear=no, source spine descriptor и линейность разделов. Container/OPF/
nav/NCX bytes, все metadata XML entries и package attributes проходят JSON opaque.
Конечные плоские CSS rules сохраняются; linked CSS подтверждён raw resource.
Selectors/declarations, at-rules/nesting, var/calc/important/URL, invalid font-size
и missing/remote stylesheet вне профиля имеют диагностику.

HTML lang, caption с inline styles/links, th/td, scope, headers/IDs, row/column
groups и logical colgroup intervals проходят два цикла с merges/правками/удалением.
Общие Table/Row/Cell semantics и caption_ids управляют результатом; перенос
несоседней/пустой подписи и удаление связи сохраняются, legacy данные её не возвращают.
Неоднозначные ассоциации и неизвестные caption blocks остаются в source profile
с диагностикой. Chromium 151 подтверждает имя таблицы, columnheader/rowheader
и навигацию при 375/1280; узкий viewport сохраняет горизонтальную прокрутку.
Общие borders проецируются в конечный CSS-профиль HTML/EPUB с межформатным LOSS.

Текстовый DjVu профиль проверен на двух собственных страницах с Unicode и без
скрытого текста. UTF-8 не зависит от locale; stdout/stderr ограничены,
timeout/отмена останавливают процесс. Координаты и структурный writer этим не приняты.
Подробности — в [описании форматов](formats.md),
[корпусе](../development/corpus.md) и [ресурсных ограничениях](resources.md).

## Ресурсы и карты объектов

Выбранный DocumentLimits проходит через integration импорта DOCX/PPTX/HTML/EPUB/
LaTeX/PDF, JSON, экспорт, Model operations и inspection. Собственный PPTX
35 slides/6720 runs проходит два JSON/native цикла с max_nodes=200000 и точным
текстом; default 100000 даёт адресный quota/maximum отказ. Большая модель шести
форматов принята с 300000, частный большой DOCX — с 500000. Nodes/depth/bytes/
embedded bytes, входной размер, поздний отказ и неизвестная квота backend
сохраняют исходник/назначение; defaults не повышаются. Inspection проверяет SHA256
до/после, отмена отбрасывает измерения, неполный PDF scope обозначен явно.

C-MAP-01 хранит typed source→provided PNG→measured PDF target и vector→PNG
с отдельными occurrences, known/unknown locators, полнотой, reason/code и статусом
публикации. Quality/cancel/bytes-change/publication rollback снимают actual target claims.
SVG→PNG, target resources, потоковое/нативное размещение, перестановки, удаления
и повторный импорт проходят два PDF/JSON цикла. Явные bridge relations и connected
split/merge композируются с unknown связями и частичной потерей. Полная автоматическая
связь произвольных snapshots не заявляется. Правила — в
[картах объектов](object-mapping.md) и [бюджете инспекции](formats.md#бюджет-файловой-инспекции).

Стандартный PDF-профиль использует один PyMuPDF; pypdf, pdfplumber и pdf2docx
с их цепочками выбираются отдельными extras. Небольшие проверки и Info metadata
используют собственный слой на выбранном движке. Условия каждого профиля — в
[зависимостях](dependencies.md), лицензионные доказательства — в
[аудите](../development/licenses.md).
