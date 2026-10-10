# Подтверждённые задачи

Полнота исходных форматов требует следующих задач. Это границы реализации,
а не утверждение о нарушении обещаний поддержки всей спецификации.

## Приоритет P0: валидность DOCX с SmartArt и OLE (OF19)

- Исправлены source relationship ID collisions, сохранение SmartArt drawing и VML
  preview, коллизии имён импортированных и созданных изображений. Неполный или
  отсутствующий граф opaque references теперь вызывает атомарный отказ.
  Два публичных цикла сохраняют выбранные payload bytes; результаты открываются
  в Word, сохраняют пять узлов SmartArt и OLE class. Правка узла SmartArt и текста
  копии документа сохраняется после повторного открытия.
- Колонтитулы имеют source part binding: зависимости opaque objects восстанавливаются
  в созданной редактируемой части, исходный XML не подменяет правки текста.
  Два цикла всех шести типов проверяют bytes, targets и текстовые правки;
  SmartArt/OLE в обычных верхнем и нижнем колонтитулах открываются в Word.
- Остаётся расширить проверку на native editing содержимого OLE,
  нативное отображение first/even running content, различные preview formats и повторный цикл нативно изменённых
  копий. Сохранение исходной книги побайтно не заменяет всю эту приёмку.
- На собственных документах подтверждён отказ Word открывать результат обоих
  DOCX → JSON → DOCX циклов в опубликованном профиле 0.18.0 / Model 0.7.2.
  Исходники открываются; расположенные LOSS не делают повреждённый результат допустимым.
- Проверить весь граф связанных частей, namespaces и ссылок: в результате SmartArt
  отсутствует `word/diagrams/drawing1.xml`, в результате OLE — preview `word/media/image1.emf`.
  Эти различия являются свидетельствами, а не доказанной единственной причиной.
- Исправить непрозрачное сохранение выбранных объектов со всеми необходимыми частями
  либо обеспечить валидное диагностированное упрощение или атомарный отказ.
  Не подменять проверку открываемости наличием ZIP-частей и целей `.rels`.
- Приёмка: собственный SmartArt с пятью узлами и встроенная книга `Excel.Sheet.12`
  без макросов и внешних связей; два публичных цикла; открытие в Word, проверка
  узлов/макета или содержимого книги; нативная правка копии, сохранение и повторное
  открытие. Проверить нулевой бюджет потерь, отмену, лимиты и неизменность исходника
  и прежнего файла при отказе. Исправление не требует нового контракта модели.

## Приоритет P0: диагностика импорта (OF15)

- Общий мост реализован: `ImportResult.issues` получает предупреждения всех читателей
  из metadata и typed preservation ledger OpenDoc, включая повторный импорт JSON.
  `assessment_complete` и `lossless` требуют явно завершённой оценки функций;
  пустой список предупреждений не доказывает отсутствие потерь.
- EPUB отмечает пропуски нелинейных/неподдержанных spine items, missing images,
  audio/video playback, object/script и ограничения table/MathML профиля.
  Inline SVG и исходные font/media assets теперь удерживаются opaque; standalone images импортируются.
  Ledger содержит reason и source provenance; оценка явно неполная.
- PPTX отмечает потери package graph, transitions/timing, иерархии групп, audio/video,
  3D settings и пропуски фигур/картинок. Неподдержанные graphic objects различают
  visual preview и lost; source XPath, part, shape ID и номер слайда сохраняются в JSON.
- DOCX отмечает complex fields, comments/revisions/content controls, text boxes/WordArt,
  SmartArt/OLE и protection по источнику: `opaque` требует сохранённого фрагмента/part,
  иначе `lost`. Учёт inventory не выдаётся за доказательство сохранения.
- PDF имеет typed finite links/notes/highlights/forms и partial ledger с page/xref;
  неподдержанные типы, tagged structure, layers/catalog actions сохраняются opaque
  в ограниченном source PDF. Геометрические/OCR warning ещё не полностью типизированы.
- HTML переносит выявленные profile losses в ledger со строкой/колонкой и привязкой
  к блоку. Исходные HTML bytes удерживаются как inert attachment; внешние assets
  не объявляются сохранёнными. Writer отмечает невоссозданные исходные функции.
- Остаётся: читатели EPUB/PDF и других форматов не диагностируют каждый пропуск;
  legacy warning без структурированной оценки не определяет состояние сохранности.
- Реализовать общий контракт feature/location/severity для каждого читателя:
  семантический разбор, native opaque, visual surrogate, потеря и отказ.
- Приёмка: по fixture каждого непереносимого объекта issue указывает источник;
  JSON сохраняет provenance/расширения; пустой отчёт не выдаётся за доказательство lossless.
  Отсутствующий backend, отмена и превышение лимитов остаются различимы.

## Приоритет P1: чтение исходного LaTeX (OF04)

- Базовый `.tex` reader зарегистрирован: собственный bounded lexer/parser без engine,
  UTF-8/BOM, body/абзацы/стили/заголовки/списки/простые акценты, inline/display
  Formula LATEX и label/ref. Source spans/provenance и оригинальные inert bytes
  проходят JSON; unsupported commands/environments имеют located opaque diagnostics.
  Assessment остаётся неполной; source-v1 не выполняет file commands и macros.
- Остаются таблицы, math environments, изображения, local include/bibliography,
  ограниченные macros и проверенный семантический source → JSON → TeX roundtrip.
  Экспорт пока использует DOCX bridge; задача открыта до всей приёмки ниже.
- Реализовать безопасный парсер опубликованного подмножества TeX: преамбула, секции,
  текст/акценты/комментарии, списки, таблицы, inline/display math, рисунки,
  labels/refs/citations, локальные `input/include` и ограниченные пользовательские макросы.
- Не исполнять TeX, shell escape или сетевые include. Ограничить размер/глубину/
  раскрытие макросов, циклы include и чтение вне resource root.
- Приёмка: собственный `.tex` с `.bib` и изображением → OpenDoc → JSON → TeX;
  семантическое сравнение, source spans, явные unknown-node/loss diagnostics.
  Отдельные fixtures для циклов, неизвестных пакетов и исчерпания лимитов.
  Полнота произвольного программируемого TeX не должна обещаться.

## Приоритет P1: семантика сложного DOCX (OF05)

- Основание: native OOXML inventory и сохранение package не дают семантического
  представления comments/revisions/content controls/SmartArt/OLE.
- Проверены два JSON roundtrip для текста в `smartTag` и preferred widths
  таблиц/ячеек (`dxa`, `pct`, `auto`, `nil`). Собственные документы проверены в Word:
  текст, одна страница и колонки 10/80/10 сохраняются. `smartTag` остаётся opaque.
- Формальная роль Heading 1–9 переносится через нативные outline levels,
  включая наследование и основной текст. Два JSON цикла и явная смена/удаление
  роли проверены в Word; производные стили сохраняются в package.
- DOCX заполняет общие preferred widths таблиц и ячеек; обратная запись сохраняет
  исходные единицы, явные правки и удаление. Старые JSON мигрируют при публичном
  импорте; абсолютные и относительные значения проверены в двух циклах.
- Подзадачи с отдельными fixtures: диапазоны комментариев и ответов; tracked changes
  с режимами отображения; fields и ссылочные поля; content controls;
  text boxes/SmartArt/embedded objects с документированным fallback.
- Приёмка: DOCX → JSON → DOCX сохраняет связанные IDs/диапазоны и неизменённые части;
  межформатный экспорт сообщает, какие объекты превратились в surrogate/opaque.
  Подписи, макросы, лимиты и запрет исполнения содержимого соблюдаются.

## Приоритет P1: исходная структура PPTX (OF06)

- Основание: `read_pptx_model` не заполняет `DocumentModel.package`; группы уплощаются,
  анимация/медиа/transition не имеют семантического маршрута.
- Проверены effective solid background slide/layout/master, редактируемые осевые
  freeform paths и отсутствие пустого `solidFill` для наследуемого текста.
  Два JSON roundtrip подтверждены нативными свойствами PowerPoint.
  Исходная иерархия фона, style matrix/bgRef и полный table/theme inheritance остаются.
- Сохранить original package и связи; отдельно моделировать группы, master/layout/theme,
  embedded workbooks/OLE, transition/timing и audio/video без запуска содержимого.
- Приёмка: набор с группами, наследованием темы, диаграммой, анимацией и медиа → JSON
  → PPTX; сравнить дерево объектов, связи, оформление и непрозрачные части.
  Для каждой неподдержанной функции — issue и bounded surrogate/opaque, а не исчезновение.

## Приоритет P1: семантика и graphics state PDF (OF07)

- Реализовано: конечный import links/notes/highlights и simple forms, inert actions,
  общий `Outline` с иерархией и page/external destinations, native outline extension
  и opaque source для неподдержанных объектов; JSON и поворот страниц.
  Конечный native writer сохраняет закладки, page points/zoom, базовый вид,
  безопасные URI и body paragraph anchors по действительному потоку.
  Старые JSON мигрируют однократно; явные правки и удаление имеют приоритет.
- Проверен позиционированный растр: все повторные xref/inline размещения,
  soft mask, полная геометрия до viewport crop, четвертьобороты и отдельный масштаб
  осей. Два JSON roundtrip совпадают по RGB-рендеру на собственных страницах.
  Произвольный конечный affine (поворот, shear, reflection) и ограниченный
  single-image quadrilateral clip проходят два цикла с точным RGB совпадением.
  Inline-изображение следует действительному потоку страниц; paragraph anchor
  с нулевыми offsets имеет flow fallback с located LOSS для floating wrap.
  Смешанный paint order диагностируется; полный graphics state/clipping остаётся открытым.
- Остаётся: semantic structure tree и optional content; полный clipping/masks/blend,
  полный профиль outline actions/named destinations и anchors остальных узлов,
  полный профиль page boxes/UserUnit/inherited нестандартных областей и legacy
  JSON без исходных media dimensions (неизвестное не угадывается),
  XFA/signatures/radio groups и полный annotation appearance.
- Подзадачи: marked content и reading order; расширение форм/аннотаций и их writer;
  слои; clipping, transform, masks, blend и ICC/output intents с сохранением оригинала.
- Приёмка: tagged PDF и PDF с формой, слоями и обтравкой → JSON;
  сохраняемые данные проверены структурно, визуальные — рендером с допусками.
  OCR/эвристики обозначены в provenance; активные actions не исполняются.

Общий `PageGeometry` заполняется и нативно записывается: media/crop до поворота,
source coordinate convention, все четвертьобороты, typed crop/rotation edits и
удаление проверены. Два PDF/JSON цикла сохраняют исходные области и RGB viewport,
включая ненулевые и отрицательные native origins. Непривязанные pages и repagination
диагностируются; это не полный PDF graphics state и не восстановление скрытого текста.

## Приоритет P1: содержимое EPUB (OF08)

- Реализовано: конечный профиль XHTML tables/captions/rowspan/colspan/nested tables
  и MathML Formula; mixed cell text сохраняет порядок, JSON и HTML экспорт проверены.
- Реализовано: standalone images, безопасный inline SVG resource (opaque);
  исходные font/audio/video bytes удерживаются в inert attachments.
- Реализовано: явный `epub_include_nonlinear`/`include_nonlinear` для глав `linear=no`,
  source spine descriptor и линейность разделов сохраняются через JSON.
- Реализовано: исходные container/OPF/nav/NCX bytes удерживаются opaque;
  все metadata XML entries и package attributes сохраняются через JSON.
- Реализовано: диагностика выходов за конечный CSS profile для selectors/declarations,
  at-rules/nesting, var/calc/important/URL и invalid font-size; missing/remote stylesheet.
  Поддержанные плоские правила сохраняются; linked CSS подтверждён raw resource.
- Остаётся: семантика CSS font-face/обфускации шрифтов,
  редактируемые SVG shapes и playback/media contracts,
  семантика nav/OPF metadata, fixed-layout и полный CSS;
  таблицы внутри текстовых блоков диагностируются как flattened.
- Разбирать XHTML общим структурным путём: таблицы с объединениями, MathML, SVG,
  standalone media; сохранить весь spine/nav/OPF metadata, font assets и fixed-layout
  признаки. Нелинейные документы учитывать отдельным явным режимом.
- Приёмка: EPUB с таблицей, формулой, nonlinear chapter, nav, шрифтом и SVG → JSON;
  проверка количества/типа объектов, ссылок, порядка глав и исходных ресурсов.
  Сетевые URL не загружаются; unsupported media/CSS диагностируются.

## Приоритет P2: статический HTML/CSS (OF10)

- Основание: ограниченное подмножество CSS и отсутствие полного browser layout.
- Проверены два JSON roundtrip для lang, caption с inline styles/ссылками,
  th/td, scope col/row/rowgroup, headers/IDs и групп строк. Независимая приёмка
  в Chromium 151 подтверждает имя таблицы, columnheader/rowheader и навигацию
  в двух циклах при 375/1280; при 375 остаётся горизонтальная прокрутка.
  ARIA/role/dir вне профиля диагностируются; colgroup, полное дерево доступности,
  экранный диктор и responsive layout остаются открытыми.
- Использовать общие Table/Row/Cell semantics модели для уже проверенных caption,
  roles/headers и групп; сохранить чтение прежних форматных расширений и JSON.
- Опубликовать feature profile; расширять cascade/inheritance, CSS variables,
  table layout, flex/grid и paged media конечными подмножествами.
  Сохранять lang/alt/roles и смысл accessibility, оригинальный unsupported fragment.
- Приёмка: corpus CSS cases с эталоном браузера и семантическим сравнением;
  каждый выход за профиль диагностирован. JavaScript не выполняется;
  URL и локальные ресурсы подчиняются policy и лимитам.

## Приоритет P2: структурный DjVu (OF11)

- Основание: маршрут `djvutxt` возвращает только текст, writer отсутствует.
- Текстовый профиль проверен на двух собственных страницах с Unicode и без
  скрытого текста. UTF-8 не зависит от locale; stdout/stderr ограничены,
  timeout и отмена останавливают процесс. Структурная приёмка ниже остаётся открытой.
- Чтение страниц, word boxes, растра, outline и метаданных через контролируемый backend;
  alias расширений проверить по спецификации. Writer оценивать отдельным профилем
  после импорта, не обещать восстановление исходного кодирования.
- Приёмка: многостраничный собственный DjVu → JSON с текстом/координатами/растрами,
  отмена/timeout/отсутствующий backend диагностированы; никаких внешних действий.

## Расширение реестра: офисные исходники (OF13, P2)

- Основание: LibreOffice preview не является семантическим импортом.
- Отдельные подзадачи: ODT/RTF; ODP; XLSX/ODS с листами, типами ячеек, формулами,
  диапазонами/merge, стилями и chart data; legacy DOC/XLS/PPT через ограниченный маршрут.
- Приёмка каждого формата: registry capability + собственная fixture + JSON roundtrip
  + документированные потери; conversion-to-PDF не засчитывается как полный парсер.
  Оригинальные пакеты/opaque части сохранять согласно policy, macro/action не запускать.

## Расширение реестра: Markdown и BibTeX (OF14, P2)

- Основание: читателей `.md`/`.bib` нет, enum не является реализацией.
- Отдельные подзадачи: опубликованный Markdown dialect (таблицы, fenced code, ссылки,
  изображения, optional math); BibTeX entries/strings/crossref и связь с citations.
- Приёмка: текстовые fixtures → OpenDoc → JSON → исходный формат с семантическим
  сравнением; неизвестные конструкции сохраняются или диагностируются;
  include/network и раскрытие строк ограничены.

Каждая задача принадлежит OpenDoc Formats. Изменения общей модели согласуются по
[предложениям к OpenDoc](opendoc-proposals.md), парсеры и движки остаются здесь.

## Приоритет P1: разрешение на XSL-ресурсы lxml (OF16)

- Основание: lxml 6.1.3 `LICENSES.txt` прямо выделяет `RNG2Schtrn.xsl` и
  `XSD2Schtrn.xsl` как unlicensed; в их исходниках отсутствует license grant.
  Файлы входят в lxml wheel, хотя библиотека их не использует и не встраивает в свой wheel.
- Получить проверяемое разрешение правообладателей/upstream на конкретные файлы
  и подтвердить его для выбранного выпуска; публичные обращения делаются только
  с разрешения пользователя. До этого вопрос остаётся открытым.
- Если подтверждения нет: исследовать отдельную воспроизводимую сборку зависимости
  без ненужного `lxml.isoschematron`/ресурсов либо подходящий проверенный дистрибутив.
  Не удалять файлы из пользовательского/shared окружения и не выдавать изменённый
  wheel за официальный upstream. Замена всего XML-движка не является первым шагом.
- Приёмка: разрешение с охватом нужных прав **или** зафиксированный hash сборки без
  спорных ресурсов; проверка archive membership, сохранение остальных notices/source
  obligations; DOCX/PPTX/EPUB/PDF-конвертеры и XML policy проходят приёмку Windows/Linux.
  Чистота самого пакета Formats и комплекта зависимостей проверяются отдельно.
- Доказательства: [статус XSL](lxml-xslt.md), `lxml-xslt-evidence.json`.
