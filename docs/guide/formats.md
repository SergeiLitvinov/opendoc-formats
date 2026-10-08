# Форматы и ограничения

## Реестры

| ID | Чтение | Запись | Что сохраняется и где возможны потери |
| --- | --- | --- | --- |
| `txt` | UTF-8, UTF-16 LE/BE, явный CP1251; BOM и пустые строки | Выбранный `TextProfile`; по умолчанию UTF-8/LF без BOM | Исходные encoding/BOM/newlines сохраняются для выбранного byte roundtrip; стили и геометрия теряются |
| `json` | Нативный JSON OpenDoc Model | Нативный JSON OpenDoc Model | Полная модель, JSON-совместимые дополнительные поля и встроенные ресурсы |
| `html` | Статический HTML и ограниченный CSS | HTML, встроенные ресурсы | Абзацы, таблицы, списки, ссылки, изображения, формулы; неподдержанный CSS диагностируется |
| `docx` | OOXML через python-docx | OOXML через python-docx | Текст, стили, таблицы, формулы и ресурсы; непрозрачные части пакета имеют отдельные границы переноса |
| `pptx` | OOXML через python-pptx | Редактируемые слайды | Одна секция — один слайд; поддерживаются таблицы, геометрия и выбранные диаграммы; темы, анимации и 3D упрощаются |
| `pdf` | Геометрия и текстовый слой PyMuPDF | PyMuPDF | Позиционирование, текст, изображения; структура восстанавливается эвристически, редактируемость исходника не гарантируется |
| `epub` | Собственный ZIP/OPF/spine/nav/NCX слой и BeautifulSoup; необязательный EbookLib backend | — | Текст, ссылки и изображения; ограниченный CSS, нелинейные главы пропускаются |
| `djvu` | Текст через внешний `djvutxt` | — | Только извлечённый текст |
| `latex` | — | Через DOCX-мост | TeX из структуры DOCX; сложные объекты и точная геометрия не гарантируются |

Неизвестный ID возвращает `import.unsupported-format` / `export.unsupported-format`.
Отсутствие Python-движка — `*.backend-unavailable`. Для TXT/JSON движки не нужны.
`DocFormat` в низкоуровневом извлечении текста перечисляет и идентификаторы низкоуровневых маршрутов;
перечисление само по себе не означает наличие маршрута в реестре.

## Проверка результата

### Профиль TXT

```python
from opendoc_formats import ExportOptions, ImportOptions, TextProfile, read_document, write_document

# CP1251 без BOM требует явного выбора.
result = read_document("source.txt", options=ImportOptions(txt_profile=TextProfile("cp1251")))
if result.success:
    # auto на записи использует сохранённые encoding/BOM/newlines исходного TXT.
    report = write_document(result.document, "copy.txt", options=ExportOptions(txt_profile=TextProfile()))
```

`TextProfile.encoding`: `auto`, `utf-8`, `utf-16-le`, `utf-16-be`, `cp1251`.
Автоматическое чтение распознаёт UTF-8/UTF-16 BOM; без BOM применяется строгий UTF-8.
Это конечная политика, не распознавание произвольной кодировки. Legacy text и UTF-16
без BOM требуют явного выбора. Невалидные bytes, UTF-32, NUL, конфликтующий/запрещённый
или обязательный отсутствующий BOM отклоняются с `import.txt-encoding` и машинным `reason`.
CP1251 не имеет BOM. Декодирование и кодирование не заменяют ошибочные символы.

`bom`: `auto`, `require`, `forbid`. На записи `auto` берёт BOM исходного профиля,
если он сохранён; для новой модели BOM отсутствует. `newline`: `preserve`, `lf`, `crlf`, `cr`.
Модель хранит логические абзацы независимо от физических разделителей; низкоуровневый
`read_txt` применяет выбранную newline policy к тексту. Writer применяет её к выходным bytes.
`preserve` использует исходную последовательность разделителей, включая смешанные CRLF/LF/CR.
При изменении числа границ writer выбирает LF и сообщает `LOSS: txt-newlines`.
Без `ExportOptions.txt_profile` сохраняется прежний UTF-8/LF без BOM.

Исходные encoding/BOM/newlines, SHA-256 и размер находятся в `metadata.txt`;
сводка профиля — в provenance секции. JSON сохраняет оба представления.
Неизменённый TXT после JSON и записи с `TextProfile()` проверен байт-в-байт для всех
перечисленных кодировок. Непредставимые в выбранной кодировке символы отклоняют экспорт
до замены предыдущего файла. Проверка результата использует фактическую кодировку writer.
TXT сохраняет только основной текст; byte roundtrip не обещан для произвольной сложной модели.

### Отчёт импорта

EPUB использует конечный CSS profile: простые element/class/id selectors и текстовые
свойства font-family/font-size/font-weight/font-style/text-decoration/vertical-align,
color/background-color. Неподдержанные selectors/properties, at-rules/nesting,
malformed source, invalid font-size, var/calc/URL/important values и missing/remote
stylesheets диагностируются как `epub.css`. Поддержанные плоские правила сохраняются
рядом с неподдержанными группами; содержимое `@media` не применяется безусловно.
Linked CSS удерживается в raw resource (`opaque` с `resource_id`), ограничения inline
CSS отмечаются `lost` с исходным ID/строкой. Это частичная оценка, не полный CSS parser
или browser layout. Внешний stylesheet URL не загружается и не заменяется локальным файлом.

EPUB удерживает оригинальные `META-INF/container.xml`, OPF и manifest nav/NCX
как XML attachments. `metadata["epub"]["source_xml_resources"]` связывает действительное
имя части ZIP с resource ID; исходные байты и provenance сохраняются через JSON.
`epub.metadata_entries` содержит все дочерние OPF metadata XML entries, включая
повторяющиеся поля и `refines`, а `epub.package_properties` — атрибуты package.
Это исходные данные, не выполняемые инструкции. Ledger `epub.package` отмечает
`opaque` и проверенный ресурс. Иерархия навигации и rendition hints удерживаются
в источнике, но не являются полной редактируемой моделью nav или fixed-layout.

Нелинейные главы EPUB импортируются при явном выборе:

```python
from opendoc_formats import ImportOptions, read_document

result = read_document("book.epub", options=ImportOptions(epub_include_nonlinear=True))
```

Для прямого reader доступен `read_epub_model("book.epub", include_nonlinear=True)`.
По умолчанию `linear=no` пропускается с `nonlinear-spine` diagnostic. При включении
главы импортируются в порядке исходного spine; признак сохраняется в
`section.properties["epub"]["linear"]`. Metadata `epub.source_spine` содержит все
исходные idref/href/linear, а `epub.include_nonlinear` — выбранный режим, включая JSON.
Режим не добавляет поддержку nav или других неподдержанных spine item types;
оценка EPUB по-прежнему явно неполная.

EPUB также импортирует изображения вне абзацев и inline SVG в исходном порядке.
SVG очищается общим безопасным XML-путём и хранится как vector image resource;
ledger отмечает `opaque` с `resource_id`, поскольку редактируемые фигуры не построены.
Scripts, обработчики событий и внешние ссылки SVG не исполняются и не загружаются;
удаление из SVG диагностируется. Одинаковые SVG используют общий ресурс, а совпадение
ID с исходным manifest asset не приводит к его перезаписи.

Исходные font/audio/video assets удерживаются как `ResourceKind.ATTACHMENT` с
`opaque` record `epub.asset`: точные байты и provenance сохраняются через JSON.
Это не активация шрифта, обработка его обфускации, воспроизведение или гарантия
прав на сам asset; его лицензию следует учитывать отдельно от лицензии адаптера.
HTML export встраивает изображения и безопасный SVG, сообщает о невоссозданных
функциях EPUB и не активирует inert assets. `img` использует только локальный
image item из manifest; внешние URL и ссылки на файлы иных media types диагностируются.

Native EPUB также импортирует XHTML `table`/`caption`/`tr`/`td`/`th` в Table:
`rowspan` и `colspan` поддерживаются в диапазоне 1–100, недопустимые значения
заменяются единицей с loss diagnostic. Сохраняются вложенные таблицы и порядок
текста вокруг блоков в ячейках. Таблица внутри текстового блока (`p`, `li`,
`blockquote` и т. п.) пока уплощается с явным issue. Профиль ограничен
10 000 ячейками на таблицу, 16 уровнями таблиц и 64 уровнями контейнеров ячейки.
MathML сохраняется как Formula с inline/display признаком; опасные элементы и
атрибуты удаляются с диагностикой, JavaScript не исполняется. Provenance использует
реальное имя части ZIP, включая папку OPF. JSON и HTML export сохраняют проверенную
структуру; полный EPUB/CSS и writer EPUB остаются задачами. Профиль `epub` использует
собственный контейнер, стандартный XML и BeautifulSoup, без EbookLib/lxml.

HTML дополнительно записывает выявленные ограничения статического профиля в
`opendoc.integration`: `lost` относится к неперенесённой семантике, CSS или ресурсу,
а отдельный `opaque` record `html.source` — к оригинальному файлу HTML.
При наличии предупреждений его байты сохраняются в attachment
`html-original-source`; это не подтверждает загрузку внешних assets и не означает
сохранение browser behavior. JavaScript и обработчики событий не исполняются.
Ledger содержит исходный файл, строку/колонку при наличии, ID элемента и
`extra.block_location` для связи с прежними HTML diagnostics. HTML → JSON сохраняет
оба представления; HTML writer сообщает о невоссозданных исходных функциях и
не вставляет source attachment в страницу. Копия ограничена 10 MiB, предупреждения —
10 000 объектами. Пустой ledger не является полной оценкой HTML/CSS.

`ImportResult.issues` объединяет предупреждения читателя из `metadata.warnings`
и `metadata.<format>.warnings` с записями `opendoc.integration`.
Строковые предупреждения получают код `<format>.warning` и путь к исходному файлу
с адресом записи в metadata; структурированные HTML-предупреждения сохраняют свой код
и location. Исходная metadata остаётся в модели и сохраняется через JSON.

Для typed ledger состояния `opaque`, `visual` и `lost` дают `LOSS`,
`rejected` — `ERROR`; reason, location и измерения сохраняются.
Отказ в сохранении объекта делает `success=False`, но прочитанная модель остаётся
доступной для анализа. `assessment_complete=True` требует явно завершённой оценки
и отчёта для каждой заявленной функции. `lossless=True` дополнительно требует
семантического сохранения всех оценённых функций и отсутствия `LOSS`/`ERROR`.
Это оценка заявленного профиля, а не всей спецификации формата.
Без ledger импорт может быть успешным, однако не считается проверенным без потерь.
Строковые предупреждения не превращаются автоматически в оценку сохранности:
полнота диагностики внутри читателей остаётся задачей [OF15](../development/todo.md).

EPUB reader записывает частичную оценку в `opendoc.integration`: пропущенные
нелинейные/неподдержанные spine items, выходы за профиль таблиц/MathML,
изображения без локального image ресурса и audio/video playback, object/script.
Это состояние `lost`,
даже когда часть текста или alt сохранилась. `reason` описывает конкретную потерю;
`location` содержит исходный файл, часть архива и ID элемента либо строку/колонку XHTML.
Provenance сохраняет исходную часть и ID. Исходные font/media assets и inline SVG
удерживаются `opaque` с проверенным ресурсом; их байты не объявляются потерянными.
Полный CSS, OPF metadata, accessibility
и другие функции ещё не оценены: `assessment_complete` остаётся `False` для EPUB.

PPTX reader сохраняет частичную оценку: исходный package graph не перенесён,
transition/timing, иерархия групп, audio/video playback и 3D settings потеряны;
фигуры без разрешимой геометрии/положительного extent и картинки без ресурса
отмечены как пропущенные. Для неподдержанного graphic object (включая OLE/диаграмму
SmartArt) `visual` означает фактически сохранённую картинку предпросмотра с `resource_id`;
`lost` — отсутствие такой картинки. Payload OLE и исходные связи из этого не следуют.
Диагностика содержит source path, фактический part name, XPath, source shape ID
и номер слайда. Путь к части не вычисляется из номера слайда, поэтому перестановка
слайдов не искажает адрес. JSON сохраняет ledger и provenance.
Полнота тем, master/layout, chart data и других функций ещё не оценена;
`assessment_complete` остаётся `False`, а OF06/OF15 остаются открытыми.

DOCX reader оценивает сложные исходные объекты: comments/revisions/content controls,
fields, text boxes/WordArt, SmartArt/OLE, protection и соответствующие связи.
`opaque` означает проверенное совпадение сохранённого XML-фрагмента либо сохранение
части в PackageGraph; это не полноценная семантическая модель диапазона, объекта или поля.
Проверка фрагментов учитывает их кратность и каноническое XML-представление;
байтовая идентичность всего исходного DOCX из этого не следует. Отсутствующий фрагмент
отмечается `lost`, даже если inventory раньше классифицировал тип как `native-ooxml`.
Поле `docx_features.assessment_scope` явно отделяет учёт типов от доказательства
сохранности в `opendoc.integration`.

Для связанного непрозрачного объекта проверяются байты target part и соответствующая
связь в PackageGraph; внешняя OLE-ссылка не считается перенесённой и не загружается.
Issue содержит исходную часть, XPath или relationship ID, provenance — source path и ID.
JSON сохраняет эти сведения. Импорт и экспорт не исполняют embedded payload или поля.
Оценка остаётся неполной (`assessment_complete=False`); OF05/OF15 открыты.

### Интерактивный профиль PDF

`opendoc.integration` содержит `DocumentPage`, `Annotation` и `FormControl`:
links с inert destination, Text/FreeText notes, highlights с исходными vertices,
text/checkbox/choice/button widgets с именем, value, choices и flags. Scripts и
сырые `A`/`AA` сохраняются как строки/данные, не исполняются и не разыменовываются
во внешние файлы/URL. Это конечный профиль; сложное appearance и редактируемая
иерархия полей не обещаются. Outline сохранён в `extra.pdf_outline`, пока нет
общего typed outline контракта.

Неизвестные типы annotations/widgets, structure tree, layers и catalog actions
получают состояние `opaque`, а исходный PDF сохраняется в Attachment
`pdf-original-source` (до 10 MiB). Для профильных объектов эта копия тоже сохраняется,
чтобы удержать оставшиеся source references и appearance. Она не исполняется.
Plain PDF без таких объектов не получает дополнительную source-копию.
Лимиты профиля: 10 000 записей, 65 536 символов в извлекаемых строках;
ошибка лимита отклоняет чтение, а не возвращает пустую модель.

Page/xref provenance и backup сохраняются через JSON. `assessment_complete=False`:
наличие source-копии не означает полного семантического чтения PDF. Layout writer
пока не восстанавливает annotations/forms/outline и opaque features; сообщает `LOSS`.
Другие writer profiles не получают обещания переноса этих объектов.

Координаты — точки в неповёрнутом cropbox; rotation находится в page extra и
`section.properties.pdf.source_rotation`. Writer восстанавливает этот поворот
после layout, сохраняя согласованность размеров и геометрии.
API и координатный контракт движка: [Page](https://pymupdf.readthedocs.io/en/latest/page.html),
[Annot](https://pymupdf.readthedocs.io/en/latest/annot.html),
[Widget](https://pymupdf.readthedocs.io/en/latest/widget.html).

`ExportOptions.verify_output=True` включает проверку временного файла **до** замены результата:

| Формат | Проверка |
| --- | --- |
| TXT | Декодирование UTF-8; пустой документ допустим |
| JSON | Повторная загрузка и валидация модели OpenDoc |
| HTML | UTF-8 и наличие внешней структуры html/head/body |
| DOCX / PPTX | CRC ZIP, разбор основных XML-частей, повторное открытие выбранным движком |
| PDF | Открытие, отсутствие шифрования, наличие страниц, чтение их текста |
| LaTeX | UTF-8, begin/end document; без компиляции |

Ошибка — `export.invalid-output`; предыдущий файл сохраняется. Отмена проверяется ещё раз после проверки.
Проверка читаемости не измеряет визуальное совпадение или редактирование в Microsoft Office.
У пользовательского экспортёра проверки нет, пока он не предоставит `ExporterSpec.validator`.
Отключить проверку можно через `ExportOptions(verify_output=False)`.

## Шрифты

При экспорте доступные шрифты выбираются из системы. Если запрошенного семейства нет,
выбирается замена с учётом начертания и покрытия символов; имя в результате может отличаться
на Windows и Linux. Выбор записывается в `report.metrics["font_resolution"]`, замена —
предупреждение `font-substitution`. Исходная модель при этом сохраняется.
Встраивание учитывает разрешения шрифта; отсутствие подходящего шрифта или глифов
диагностируется как потеря. `report.lossless` допускает предупреждения и не гарантирует
одинаковое визуальное отображение на разных системах.

## Отдельные конвертеры

`writers.pdf_to_docx` предлагает прямые движки PDF → DOCX; Pandoc/LibreOffice используются
только соответствующими маршрутами и устанавливаются отдельно.
`writers.docx_to_latex.DocxToLatexConverter` и `readers.latex.docx_to_latex_pandoc`
работают с DOCX напрямую. Lua-фильтр поставляется в пакете.

`writers.pptx_to_html.convert(input_path, output_directory)` создаёт локальный просмотрщик
со слайдами, CSS/JS, изображениями и извлечёнными OLE-объектами. Формулы выводятся в MathML,
поддержка отображения зависит от браузера. MathJax из сети автоматически не подключается.
Извлечённые OLE-файлы не исполняются библиотекой; просмотрщик предназначен для доверенных презентаций,
а не для изоляции произвольного активного содержимого.

Низкоуровневые конвертеры имеют собственные параметры и диагностику.
Политику `ImportOptions` / `ExportOptions` обеспечивает именно вызов через реестр.

## Векторные ресурсы PDF

`application/pdf+vector` сохраняет команды `l`, `c`, `re`, `qu` и свойства paint.
PDF exporter выводит их нативно в координатах `Image.box` на первой странице секции;
векторные колонтитулы повторяются на её страницах. Поддерживается перенос и равномерное
масштабирование относительно исходного bbox; обводка и dash pattern масштабируются вместе.
Порядок наложения вектора следует порядку объектов модели поверх HTML-потока;
полное восстановление исходного PDF reading order, clipping/masks и ICC/blend остаётся OF07.

Предел — 50 000 команд на документ. Неизвестная команда, clip/mask/transform либо
неподдержанный paint требует явно заданного `Image.visual_surrogate` с PNG-ресурсом.
PNG ограничен 32 MiB, 8192 пикселями по стороне и 16 миллионами пикселей суммарно.
Такой fallback сообщает потерю редактируемости; без подходящего surrogate возвращается
ошибка без замены прежнего выходного файла. Исходная модель, команды и provenance
остаются доступны через JSON и не изменяются экспортёром.
