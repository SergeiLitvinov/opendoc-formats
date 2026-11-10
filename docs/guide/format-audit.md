# Полнота обработки исходных форматов

«Поддержан» означает наличие конкретного маршрута, а не полный разбор спецификации.
Ни один внешний формат сейчас не имеет гарантии полного семантического импорта и
обратного воспроизведения исходного файла. Нативный JSON сохраняет выразимые данные
модели из `opendoc-model`; он не восстанавливает сведения, потерянные до сериализации.

## Покрытие

| Исходный формат | Реализовано | Неполнота | Задачи |
| --- | --- | --- | --- |
| LaTeX `.tex` | Source-v1 lexer/parser; текст, заголовки, структурные списки, TeX-формулы и tabular с l/c/r, p с буквальной шириной и hline/cline без extras; исходные bytes и spans через JSON | Include, macros, сложные таблицы, numbered math, изображения и bibliography вне профиля; DOCX bridge для остальных объектов; неподдержанные списки/формулы отклоняются | OF04 |
| DOCX | Абзацы, runs, стили, таблицы, формулы, ссылки, сноски, колонтитулы, ресурсы и PackageGraph; нативные ограниченные правки | Инвентаризация comments, revisions, content controls, SmartArt/OLE и других сложных объектов не равна их семантической модели и редактированию. Перенос непрозрачных частей имеет ограничения | OF05 |
| PPTX | Текст, таблицы, выбранные диаграммы, фигуры, группы с материализацией координат, фоны, заметки, разрешение части theme/master/layout; физический исходный PackageGraph с точными байтами всех частей через JSON; source export привязанного текста, конечных cell edits, frames и image crop с неизменёнными соседями | Исходные части удерживаются opaque, а не как полная семантика. Нет полной проекции правок анимаций, аудио/видео, переходов, embedded objects и всего оформления. Rebuild создаёт новую презентацию; source profile отклоняет правки за пределами принятых bindings и не сохраняет ZIP storage metadata | OF06 |
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
PPTX: `readers/pptx.py::read_pptx_model` сохраняет физический `PackageGraph`
через `readers/pptx_package.py`. `writers/pptx_source_writer.py` применяет
принятые source-правки текста, cell slots, frames и image crop; rebuild-профиль создаёт новую презентацию и
не является восстановлением всех исходных объектов.
DOCX: `readers/docx.py` и инвентаризация в `readers/docx_features.py`.
PDF: `readers/pdf.py`, `readers/pdf_images.py`; DjVu: `readers/djvu.py`.

Воспроизводимые проверки существующих границ:
`tests/native/test_format_audit.py` и `tests/test_source_coverage.py`.
Полнота каждого сложного объекта требует собственных fixtures и сравнения после
повторного чтения; эти критерии записаны в [TODO](../development/todo.md).
Происхождение тестовых документов — в [описании корпуса](../development/corpus.md).

Рекомендации для общей модели находятся в [предложениях к OpenDoc](../development/opendoc-proposals.md).

## Реализованные профили и оставшиеся границы

| Область | Подтверждённое поведение | Что ещё не подтверждено |
| --- | --- | --- |
| Исходный PDF без движка | Classic/stream xref, ограниченные фильтры и predictors, ObjStm и Extends; исторический и текущий выбор объявлений, indirect scalar witnesses; точные decoded ranges/SHA косвенных ссылок | Владение диапазонами и разрешение целевых bodies; совпадение xref declaration не доказывает идентичность целевого member |
| DOCX Custom XML | Данные, props, dependency closure и непрозрачный `w:dataBinding` через JSON/DOCX; различение opaque/lost для известных и неизвестных связей | Вычисление XPath, синхронизация bound text, полная оценка всех relationship profiles |
| Объединённые таблицы DOCX | Конечный flow-профиль, исходные occurrences, crop и source-grid binding; replay одинаковой связи без дублирования props; общий обход shared parts | Произвольные split/merge, перестановки и правки сетки за пределами принятого профиля |
| EPUB targets | Общий source-реестр путей/fragments, строгий UTF-8 URI-профиль; inline anchors, MathML/SVG/изображения, два JSON-цикла и HTML export | Внутренние targets MathML/SVG, отсутствующие/неоднозначные IDs, повторные spine occurrences и полный source-package roundtrip |
| CFBF | Конечный физический аудит указателей, имён/порядка, directory/header fields; отдельные MUST/SHOULD findings | Полное соответствие CFBF и семантика вложенных application-specific контейнеров |
| Шрифты | Собственный статический sfnt-профиль, метрики/имена/cmap и конечные GSUB-проверки; полная программа TTF/OTF без обязательного subsetting | Полный shaping, variable/CFF-профили и равноценная замена fontTools subsetting |

Это границы конкретных маршрутов, а не заявление о полном покрытии форматов.
Подробности: [исходные структуры](document-anatomy.md),
[ресурсы и диагностика](resources.md), [карты объектов](object-mapping.md),
[компоновка DOCX](docx-layout.md). Fixtures и область независимой приёмки
перечислены в [корпусе](../development/corpus.md); незавершённая работа — в
[TODO](../development/todo.md).

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

Rich PDF переносит warnings всех OCR page results, включая результаты без блоков,
в metadata, публичный отчёт и JSON. В structure/scan недоступность OCR,
ошибка backend и пустой список page results имеют коды `pdf.ocr-unavailable`,
`pdf.ocr-failed`, `pdf.ocr-empty`. Предупреждения provider имеют
`pdf.ocr-provider-warning`, reason, provenance исходного PDF и адрес страницы.
Состояние OPAQUE обозначает непроверенную сохранность OCR, не доказанное отсутствие
текста. Содержание сообщения не используется для угадывания причины или состояния.
Текстовые warnings сохраняются для совместимости; явная ссылка на их индекс
исключает дублирование в публичном отчёте и после JSON. Fast не вызывает OCR.
Диагностика геометрии и текстовых legacy-маршрутов остаётся в OF15.

Исключения нативного поиска таблиц имеют `pdf.table-analysis-failed`, reason,
адрес страницы и название стратегии (`lines_strict`/`text`). Enrichment не теряет
эти записи; общий ledger и JSON сохраняют OPAQUE и provenance. Это непроверенный
результат анализа, а не доказательство отсутствия или потери таблицы. Лимит и
отмена прерывают обработку и не превращаются в best-effort предупреждение.

Отсутствие байтов изображения имеет `pdf.image-bytes-missing` и LOST: конкретный
painted occurrence пропущен. Повторные вхождения одного xref различаются адресом
страницы и номером изображения. Сбой `get_drawings` имеет
`pdf.vector-extraction-failed` и OPAQUE: состав графики страницы не подтверждён.
`pdf.cell-layout-unresolved` сохраняет OPAQUE для компоновки ячейки, исходный
текст и адрес `.rows[…].cells[…]` вместе с native row/column в measurement.
Reason и provenance создаются в месте события. Индексы legacy warnings явно
связываются с общим metadata-списком после объединения геометрии, OCR и ресурсов;
сообщения не разбираются для угадывания состояния. JSON сохраняет записи и
публичный отчёт без повторного вывода тех же предупреждений.
Низкоуровневые `extract_pdf_images`/`extract_pdf_vector_drawings` сохраняют прежний
tuple результата и принимают необязательный `diagnostics` collector общих Model
records. В нём `warning_index` относится к возвращённому локальному списку warnings;
rich reader явно привязывает его к итоговому `metadata.warnings`.

## Нативный TeX

Собственные bounded lexer/parser и writer работают без TeX engine и Office extras.
UTF-8/BOM, текст/акценты/локальные стили, заголовки, списки и inline/display
Formula LATEX проходят JSON вместе с source spans, provenance и точным inert
оригиналом. Неподдержанные commands/environments имеют located opaque diagnostics.

Нативный writer сохраняет обычные абзацы, прямые bold/italic/underline,
Heading 1–5 и нумерованный/ненумерованный вариант исходных section-команд.
Текстовые superscript/subscript используют общие поля TextStyle, без Office.
Границы native TeX scopes и варианты font declarations сохраняют расстояния
между соседними индексами и italic correction. Пять независимых оригиналов
проходят два JSON/TeX цикла и оглавление с попиксельным совпадением без image XObjects.
Изменение/снятие роли не восстанавливает legacy hints; неподдержанные индексы
отклоняются без DOCX-моста.
Правка и снятие Heading не возвращают legacy роль; спецсимволы остаются текстом.
Inline TeX-формулы в заголовках проходят два JSON/TeX цикла, правку/удаление роли
и независимую компиляцию с оглавлением и тремя проходами auxiliary files.
Официальный C-LIST-02 Model 0.1.0 сохраняет родителей, продолжения без нового
номера, пустые/child-only пункты, start/restart и стабильные ID. Три независимых
оригинала и по два цикла имеют попиксельно одинаковые страницы без изображений.

Formula сохраняет точное выражение, inline/display, fallback, положение среди
текста и самостоятельный block. Правка и удаление проходят два JSON/TeX цикла;
четыре независимых компилируемых примера совпадают попиксельно без image XObjects.
Существующего Formula Model достаточно; TeX syntax/annotations и приёмка
принадлежат Formats. Неподдержанные списки/формулы отказывают без DOCX bridge.
Общая assessment остаётся неполной, точная компоновка произвольного документа
не заявляется. Полный профиль и примеры — в [руководстве LaTeX](latex-source.md).

Запись простых прямоугольных таблиц также нативная: один абзац на ячейку,
inline TeX-формулы, текстовые индексы и пустые ячейки, без вертикальных объединений и заданной
геометрии. `native-table-v1` не требует Office extra; независимый tabular оригинал
и два JSON-экспорта дают одинаковые полные страницы в pdflatex.
Reader также восстанавливает конечный tabular l/c/r+hline/cline: структуру, layout carrier
и исходные spans. Два TeX/Model/JSON цикла проверены на четырёх независимых originals.
Multicolumn использует общий column_span и форматный cell override l/c/r/vertical rules;
правка и снятие override не возвращают прежние данные. Четыре независимых merged
originals приняты в двух полных source/JSON/TeX циклах.
Частичные горизонтальные правила используют версию 2 native table carrier:
упорядоченные hline/cline сохраняют повторения, пересечения и индексы логических
колонок, включая multicolumn. Четыре originals и эталон правки диапазона/ячейки
прошли два цикла и десять точных полных сравнений в каждом из MuPDF и Poppler;
[доказательство](../development/latex-cline-evidence.json). Неверные объявления и
native tables за поддержанным профилем не заменяются уплощающим DOCX bridge.
Paragraph columns, row merging/nested/floating tables и остальные table profiles остаются в OF04.

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

Для фонового `p:bgRef` индекс выбирает заливку из фактических theme
`fillStyleLst` (1–999) или `bgFillStyleLst` (1001+); это не номер цвета.
Reader выбирает ближайшую декларацию slide/layout/master, тему master с
layout/slide overrides и эффективный color map. `phClr` получает цвет reference,
а затем собственные modifiers заливки. Tint/shade фона рассчитываются в linear light
без промежуточного округления; правила принадлежат Formats, не нейтральной Model.
Явные 0/1000/noFill становятся `background_fill="none"` и пишутся как noFill,
не заменяясь белой заливкой шаблона. Правка пары `background_fill/background_color`
управляет rebuild; source route сохраняет исходный пакет в пределах принятой политики.

Шесть собственных originals, два source/rebuild JSON-цикла и отдельная правка цвета
проверены через PowerPoint: 26 точных полностраничных сравнений отдельно в MuPDF
и Poppler при 108 dpi, без масок и допуска. Проверка наличия исходного цвета допускает
округление PDF-компонент на один канал; сравнения original/cycle остаются точными.
[Свидетельство](../development/pptx-background-evidence.json) содержит SHA исходников,
reference и циклов. Неподдержанные индексы, fills и transforms получают located
`pptx.background` с физическим owner part, XPath и consumer slide.
Тема кэшируется только внутри текущего импорта, её разбор и копирование выбранного
style расходуют общий бюджет expansion nodes и проверяют отмену.
Это материализация конечного solid-профиля; нативные gradient backgrounds имеют
отдельную приёмку ниже. Редактируемая shared hierarchy, bitmap/effects и весь
theme cascade остаются открытыми.
Семантика индексов — [BackgroundStyleReference, Microsoft](https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.presentation.backgroundstylereference?view=openxml-3.0.1),
операции tint/shade — [DrawingML Primer, Microsoft](https://download.microsoft.com/download/e/1/4/e14fb96f-83b8-4a2a-84db-7fa8acbe061a/Office%20Open%20XML%20Part%203%20-%20Primer.pdf).

Общий DrawingML resolver Formats применяет тот же linear-light tint/shade к
цветам текста, заливке фигур и series fill диаграмм. Порядок XML modifiers
сохраняется: shade→tint и tint→shade дают разные результаты; промежуточное
8-bit округление между ними не вводится. Alpha не сбрасывает цвет и порядок.
Нейтральные RGB transforms OpenDoc Model этим не переопределяются.
Четыре последовательности modifiers на восьми самостоятельных originals
(text+shape и text+chart) проходят два JSON/source и JSON/rebuild цикла:
32 точных полностраничных сравнения PowerPoint PDF в каждом из MuPDF/Poppler,
108 dpi, без масок и допуска. [Свидетельство](../development/pptx-color-evidence.json)
содержит SHA исходников и cycles. Явная правка цвета текста/фигуры/серии
проверена двумя структурными JSON/rebuild циклами: старые source modifiers
не возвращают прежний цвет. Приёмка конечного профиля цвета не означает
полной совместимости диаграмм, шрифтов и всего theme cascade. Luminance имеет
отдельный конечный профиль, описанный ниже; остальные color models/transforms
требуют отдельной нативной приёмки.

`lumMod/lumOff` меняют светлоту HSL с сохранением hue/saturation до достижения
чёрного/белого; это не умножение/сложение каналов RGB. Formats использует
стандартный `colorsys`, сохраняет XML-порядок и промежуточную точность, ограничивает
результат светлоты диапазоном 0–1 после каждой операции. Целочисленный signed-int32
профиль поддерживает отрицательный lumOff и lumMod за пределами 100%:
`200000` означает множитель 2, не 1. Другие lexical percentage profiles сюда не входят.
При возврате после clipping оттенок/насыщенность берутся из полученного RGB,
а финальная ахроматическая HSL-проекция использует подтверждённое округление Office
вниз до 8-bit. Alpha не сбрасывается. Нейтральный `ColorValue.transformed` Model
не используется для исполнения этих форматных правил.

Двенадцать последовательностей на 24 самостоятельных originals (text+shape и
text+chart), включая отрицательные/200% значения, порядок lumMod/lumOff,
смешение HSL с shade и повторные операции после clipping, проходят два JSON/source
и JSON/rebuild цикла. Все 96 полных сравнений PowerPoint PDF точны отдельно в
MuPDF и Poppler при 108 dpi, без масок и допуска.
[Свидетельство](../development/pptx-luminance-evidence.json) содержит source/cycle SHA
и цветовые controls. Нативная приёмка этого sRGB-профиля не доказывает поддержку
всех colour models, lexical percentages или других эффектов.
Определения — [LuminanceModulation](https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.drawing.luminancemodulation?view=openxml-3.0.1)
и [LuminanceOffset, Microsoft](https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.drawing.luminanceoffset?view=openxml-3.0.1).

Текст, фигуры, таблицы и серии диаграмм читают общую палитру слайда
из фактического master theme, затем layout/slide themeOverride и effective color map.
Палитра presentation или стандартный Office color table не подменяют тему
другого master. XML тем кэшируется по идентичности part внутри одного импорта;
одинаковые color names двух masters не смешиваются. Явный `masterClrMapping`
слайда сохраняет эффективную layout map в проверенных PowerPoint originals,
а `overrideClrMapping` задаёт собственное соответствие. Фон использует тот же слой.

Пятнадцать самостоятельных originals проверяют второй master, layout/slide
color-map overrides, наследование layout map, layout/slide themeOverride,
текст+shape, текст+chart и унаследованную master shape. Два JSON/source и
JSON/rebuild цикла дают 60 точных полностраничных сравнений в каждом из MuPDF
и Poppler через PowerPoint PDF, без масок и допуска при 108 dpi.
[Свидетельство](../development/pptx-theme-evidence.json) содержит source/cycle SHA
и независимые цветовые controls исходных страниц; на controls допускается только
округление PDF-компонент на один канал, полные сравнения остаются точными.
Отдельный структурный тест подтверждает два разных masters в одном импорте.
Отсутствующая эффективная схема получает located `pptx.theme` с причиной
`missing-effective-color-scheme`; reader сохраняет неизвестность named colors.
Chart-local font/effect/style overrides, остальные color scheme profiles и редактируемая shared
theme hierarchy остаются вне этого конечного профиля.
Правила структуры — [slide masters](https://learn.microsoft.com/en-us/office/open-xml/presentation/working-with-slide-masters)
и [slide layouts, Microsoft](https://learn.microsoft.com/en-us/office/open-xml/presentation/working-with-slide-layouts).

Для palette диаграммы дополнительно применяется её собственный themeOverride,
затем `c:clrMapOvr` из chartSpace. Карта применяется к исходной схеме после
всех palette overrides, поэтому переназначенный accent получает цвет локальной
темы, а не устаревший RGB из палитры слайда. Две диаграммы на одном слайде
сохраняют отдельные контексты; соседний текст не получает цвета локальной темы chart.
Для унаследованной диаграммы учитывается её физический owner: chart на master
не получает layout/slide overrides, chart на layout использует layout overrides.
Это соответствует проверенным оригиналам PowerPoint и отличается от материализации
обычной master shape с эффективными цветами потребительского слайда.

Девять независимых originals, включая две charts и master/layout chart owners,
проходят два JSON/source и JSON/rebuild цикла: 36 точных полностраничных сравнений
в каждом из MuPDF/Poppler через PowerPoint PDF при 108 dpi, без масок и допуска.
[Свидетельство](../development/pptx-chart-theme-evidence.json) содержит SHA источников,
cycles и проверки видимости исходных цветов. Локальные theme parts расходуют
тот же бюджет expansion nodes и кэш текущего импорта; отмена и поздняя квота
не меняют источник. Model API и пакетные зависимости не расширяются.
Речь о конечной palette/series-fill проекции; chart font/effect/style overrides,
неподтверждённые mappings и полная редактируемая shared hierarchy остаются в TODO.
Структура локальной карты — [ColorMapOverride, Microsoft](https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.drawing.charts.colormapoverride?view=openxml-3.0.1).

Редактируемые gradient backgrounds сохраняют linear geometry (ang/scaled),
path circle/rect/shape с fillToRect, tileRect/flip/rotWithShape, alpha и совпадающие
stop positions. Theme/phClr базы материализуются в native RGB с исходными
modifiers: это сохраняет точность интерполяции, которую может изменить округление
каждого stop до сплошного 8-bit цвета.

Форматный hint `opendoc_formats.pptx_background_gradient` имеет format/version,
проверяемый DrawingML XML и color witnesses. Он ограничен 256 KiB, 32768 XML nodes
и 4096 stops. DTD, внешние/неизвестные namespaces/attributes, неверный порядок
элементов и неподдержанные данные отклоняются. Это ограниченный native профиль
Formats, не общий gradient DTO/codec Model. Текущие
`background_gradient_colors` управляют stops: native_id связывает только hint
точности конкретного цвета. Правка цвета/position и удаление stop управляют выводом;
старые XML stops не восстанавливаются. Новые/изменённые цвета требуют plain 8-bit
sRGB и представимой alpha, positions — единиц 1/100000. Геометрию задаёт проверенный
XML hint; provenance/source package не подменяет явную правку.
Удаление списка gradient stops переключает вывод на текущую solid роль,
а `background_fill="none"` отключает градиент вместе с фоном. Неиспользованный
hint не исполняется и не возвращает удалённый фон.

Девять originals (slide/layout/master, linear/path, tile/flip, theme и alpha)
проходят два JSON/source и JSON/rebuild цикла. Отдельный authored reference
проверяет изменение цвета, позиции и направления с удалением среднего stop.
Все 38 полных сравнений PowerPoint PDF точны в каждом из MuPDF и Poppler,
108 dpi, без масок/допуска; фон остаётся editable DrawingML, без растеризации.
[Свидетельство](../development/pptx-gradient-evidence.json) содержит SHA исходников,
reference и cycles, включая проверку реальной неоднородности original backgrounds.
Повреждённый активный hint и отмена оставляют существующее назначение неизменным.
Legacy gradient colors без geometry hint сохраняют прежний диагностированный
solid fallback. HTML/DOCX/PDF явно сообщают LOSS background-gradient, пока общего
paint projection нет. Пробел API передан в
[C-BACKGROUND-GRADIENT-01](../development/gradient-background-contract.md);
Проекция общего paint API в эти writers остаётся отдельной задачей Formats.

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
Переполнение body-абзаца с inline изображением вызывает ограниченный перенос
на следующую страницу без изменения размера/обрезки/поворота; проверяются
геометрия, подписи и весь следующий текст. Изображения в обычных/объединённых
ячейках и вложенных таблицах имеют отдельную приёмку: измеренные пропорции колонок
передаются PDF-layout, растр проверяется относительно контейнера и области страницы.
При переполнении переносится внешняя таблица целиком; повторное переполнение
даёт отказ. Строка/ячейка не отделяется от своих spans. Crop/rotation сохраняют
исходные RGBA pixels без ресэмплинга. Диагностика `pdf-table-flow-layout` явно
отделяет этот flow от нативных row splits и точной пагинации Word.
Разбиение смешанного абзаца с несколькими изображениями остаётся в TODO.
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

Сигнал отмены проходит через страницы и объекты нативного PDF-импорта: content view,
geometry/tables, images/vectors, OCR merge, fonts, paint, interactions и scopes.
Реестр выдаёт import.cancelled без частичной модели, прямой reader выбрасывает
OperationCancelledError. Источник не сохраняется и не меняется; закрытие native
documents и повторное чтение проверены. Неактивный callback сохраняет полный JSON
собственного смешанного примера. Одиночные сторонние вызовы остаются непрерываемыми;
детали — в [ресурсах и отмене](resources.md#отмена).

HTML/EPUB проверяют отмену внутри нативного обхода блоков, таблиц, CSS
и ресурсов, а EPUB — также между чтениями ZIP и при разборе XML пакета.
Проверены отказ без частичной модели, закрытие архива, неизменность источника
и повторный импорт. Неактивный callback даёт тот же полный JSON.
Эти контрольные точки не прерывают одиночный сторонний вызов и не заменяют
ограничение времени и памяти отдельного процесса.

Богатые и текстовые DOCX/PPTX readers поддерживают отмену внутри нативного
обхода. Для DOCX покрыты package relationships, стили, абзацы/runs, поля,
вложенные таблицы, колонтитулы, ресурсы, группы, provenance и диагностика;
для PPTX — слайды, группы/фигуры, текст, таблицы, ресурсы, темы и chart caches.
Проверены неизменность исходного ZIP, повторный импорт и полный JSON без сигнала,
отмена при завершении и изоляция параллельных импортов. Одиночные вызовы
сторонних движков и Model не прерываются; контракт Model не изменён.

Нативный экспорт DOCX/PPTX передаёт отмену в обход объектов, таблиц, групп,
стилей, chart data, font/color preflight и восстановление DOCX package graph.
Проверки после сохранения ZIP и перед атомарной публикацией сохраняют прежнее
назначение. Direct writers выбрасывают OperationCancelledError, реестр даёт
export.cancelled; исходная Model не изменяется. Принята идентичность полного JSON
повторного импорта без сигнала. Общая отмена отдельных сторонних вызовов и всей
подготовки произвольного PDF → DOCX этим не подтверждается.

HTML/EPUB/TeX export поддерживает отмену внутри обхода и перед публикацией.
Для HTML проверены блоки/inline/images и финальная навигационная проверка;
для EPUB — вложенный HTML, XHTML callbacks, главы, XML и ZIP; для TeX — символы,
формулы, scopes списков и оставшийся DOCX-мост. Неактивный callback сохраняет
точные HTML/TeX bytes и содержимое частей EPUB. Отмена не изменяет исходную
модель и прежний файл назначения. Model и обязательный `opendoc-model` не меняются;
нативные EPUB/TeX профили сохраняют прежний состав зависимостей.

Подготовка PDF → DOCX поддерживает прямую отмену и наследует контекст writer.
Проверки проходят через scopes, строки/ячейки/borders, transforms, clipping,
native groups, композицию, paint order и поворот. Подтверждены полный JSON
Word view без сигнала, неизменность PDF/модели/назначения при отмене,
закрытие временного векторного renderer и повторная подготовка.
Приёмка визуального/редактируемого PDF-профиля остаётся отдельной: наличие
отмены не подтверждает lossless для непринятых графических возможностей.

Стандартный PDF-профиль использует один PyMuPDF; pypdf, pdfplumber и pdf2docx
с их цепочками выбираются отдельными extras. Небольшие проверки и Info metadata
используют собственный слой на выбранном движке. Условия каждого профиля — в
[зависимостях](dependencies.md), лицензионные доказательства — в
[аудите](../development/licenses.md).
