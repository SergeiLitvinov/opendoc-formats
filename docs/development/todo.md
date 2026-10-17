# Подтверждённые задачи

Полнота исходных форматов требует следующих задач. Это границы реализации,
а не утверждение о нарушении обещаний поддержки всей спецификации.

Приоритет согласованных конечных контрактов: C-PDF-01 и C-MAP-01,
затем C-DOCX-01/02. Подробная приёмка — в [реестре запросов](format-requests.md#конечные-контракты).

- Реализована конечная часть C-PDF-01: публичный native text flow с измеренным
  профилем OpenDoc, нулевым бюджетом и явными неизвестными состояниями.
  Проверка полного порядка чтения/OCR/инвентаря объектов этим не закрыта.
  pypdf удалён из нативной инспекции; минимальный pdf-rich проверяется отдельно.
- C-PDF-01 / OF07: native URI link/note/highlight/text widget, canonical field tree,
  правки/удаление, четыре поворота и маленькая страница; два цикла относительно
  оригинала. Подтверждённый native text flow в публичной инспекции без ложного
  полного object inventory; научный отчёт сохраняет текст либо отказывает по адресу.
- C-MAP-01 реализован частично: typed source→provided PNG→measured PDF target,
  отдельные occurrences и общий codec; quality/cancel/bytes-change/publication
  rollback убирают actual target claims. История деклараций подтверждена через
  два полных PDF/JSON цикла, перестановку, удаление и повторный импорт.
  Карта SVG→PNG подтверждена для нативного и потокового размещения,
  target resources и двух полных циклов. Композиция явных bridge relations и
  connected split/merge реализована, включая неизвестную связь и частичную потерю.
  Открыты автоматическое подтверждение связи произвольных intermediate snapshots,
  полный инвентарь объектов и нативные сценарии произвольного split/merge.
- C-MAP-01 / OF15: типизированная source → visual representation → actual target
  карта для vector→PNG с отдельными occurrences, подтверждёнными/unknown locators,
  полнотой, reason/code и статусом публикации; два цикла, перестановка и удаление.
- C-DOCX-03 / OF05: расширить цветовой каскад на условные стили таблиц, RTL,
  неизвестные тематические объявления и добавление произвольных новых стилей.
  Прямые auto/RGB/unset, defaults/basedOn/paragraph/character, правка и удаление
  приняты в конечном [профиле DOCX](../guide/docx-layout.md). Приёмка собственного
  примера не доказывает точность оформления произвольного документа.
- OF05: расширить профиль интервала на остальные допустимые нативные значения
  и полный условный каскад абзаца. Конечные положительные auto/atLeast/exact,
  C-DOCX-04, два DOCX/JSON цикла, нативная правка Word и нулевой бюджет приняты;
  неизвестные объявления остаются расположенным отказом до явного разрешения.
  Общий LineSpacing применяется в DOCX: direct/inherited/defaults, правка и
  удаление, сравнение Model и два цикла приняты; нативные правки и полные страницы
  проверены в Word. Остаются остальные native values и условный каскад.
- C-PPTX-01 / OF06: конечные собственные слайды для geometry/theme/style/groups/
  shapes/text; сравнить каждый результат с оригиналом в PowerPoint, затем принять
  два цикла и нативную правку. Стабильность второго упрощённого цикла не заменяет
  исходную визуальную приёмку; полный PPTX не объявляется поддержанным.
- C-LIMIT-01 частично реализован: выбранные DocumentLimits передаются в полный
  integration при импорте DOCX/PPTX/HTML/EPUB/LaTeX/PDF, JSON загрузку/экспорт/
  проверку и свойства ImportResult. Собственный PPTX 35 slides/6720 runs принимается
  с max_nodes=200000 и сохраняется через два JSON-цикла; default 100000 даёт
  расположенный отказ с quota/maximum и выбранным бюджетом. Проверены nodes/depth/
  bytes/embedded bytes, входной размер и отмена до чтения; defaults не повышены.
  Нативные DOCX/PPTX/HTML/EPUB/LaTeX/PDF и внутренние полнодокументные Model operations
  используют выбранный бюджет; собственный PPTX проходит два нативных цикла с
  200000 узлов и точным текстом. Шесть форматов принимают большую модель с 300000,
  частное представление большого DOCX — с 500000. Поздний отказ при подготовке и
  неизвестная квота стороннего обработчика сохраняют назначение и исходную модель;
  export.document-limit имеет адрес и выбранный бюджет. Структурированные
  path/quota/maximum Model 0.13 используются с совместимостью прежних ошибок.
  Отмена передаётся внутрь PDF.
  C-LIMIT-01.inspection принят: keyword-only options: ImportOptions передаёт
  выбранный бюджет чтению и инспекции Model. Собственный PPTX 35 slides/6720 runs
  и его JSON проходят с 200000, default 100000 даёт структурированный адресный
  отказ. SHA256 проверяется до/после, отмена отбрасывает измерения; native
  HTML/LaTeX/PDF scopes сохранены, неполный PDF явно обозначен. Подробности —
  в [бюджете инспекции](../guide/formats.md#бюджет-файловой-инспекции).
  Открыты ограничение работы/ресурсов внутри каждого парсера и всех преобразований,
  отмена во время разбора и во всех остальных нативных обработчиках.
- C-DOCX-05 / OF05: аудит остатка нативной компоновки на собственных примерах:
  прямые отступы и поток абзацев, геометрия и внутренние отступы таблиц,
  внутритекстовое расположение. Сначала воспроизводимый дефект и два полных
  сравнения с оригиналом в Word, затем правка и нативное редактирование.
  Совпадение текста, числа страниц, цветов и интервалов не доказывает точность
  всех страниц; C-DOCX-03/04 этим повторно не открываются. Общий контракт модели
  запрашивать только при доказанном пробеле существующего API.
  Конечные три оси paragraph indent приняты: direct/inherited/defaults, правка,
  удаление и нативная правка Word сохраняются через два DOCX/JSON цикла; полные
  страницы совпадают с оригиналом и независимыми native references. Неизвестные
  units/направления и непредставимые величины адресно отказывают. Конечные
  before/after spacing и keepLines/keepNext/pageBreakBefore/widowControl также
  сохраняют direct/inherited/defaults, правку и удаление; прямые 0/false не
  теряются. Два цикла, нативные правки Word и полные страницы приняты.
  Остаются геометрия/отступы таблиц, внутритекстовое размещение и полный условный каскад.
- C-HTML-01: публичный ограниченный профиль structural HTML preview с только
  используемыми font faces/glyphs. Subsetting соблюдает разрешение шрифта;
  иначе сохраняются полный шрифт или явный отказ. Проверить Unicode/styles/colors,
  output/memory limits/cancellation. Обычный export не меняется молча.

Общие границы уже проецируются в ограниченный CSS-профиль HTML/EPUB;
остаются семантический импорт исходных CSS borders, наследование и правила
конфликтов, диагонали и подтверждённая приёмка отображения в браузерах.
Эти ограничения входят в OF10/OF08; межформатный LOSS сохраняется.

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

- Исправлен приоритет Latin theme reference над literal fallback на одном уровне
  каскада. Собственный заголовок сохраняет Calibri 12 bold в Word через два
  DOCX/JSON цикла; прямое оформление и character style имеют свой приоритет.
  Остаются выбор font slots по Unicode/language/RTL, неизвестные и отсутствующие
  темы с адресной диагностикой, перенос без зависимости от установленных шрифтов
  конвертера и приёмка исходного визуального оформления всего документа.
  Подтверждение границ таблицы и общий font warning этого не доказывают.
- Прямые table/cell borders используют Border/BorderSet: шесть сторон таблицы,
  внешние/диагональные стороны ячейки, none/nil, правки и удаление. Два JSON цикла
  сохраняют исходные атрибуты; Word подтверждает все шесть single borders,
  нативную правку double/red и следующий цикл. Unsupported theme/native детали
  остаются с расположенной диагностикой; непредставимые значения дают отказ.
  Остаются вычисление inherited/conditional styles, конфликты соседних границ,
  RTL start/end, визуальная нормализация толщины Word и межформатное рисование.
- Исправлен конечный профиль opaque SmartArt/OLE: payload parts, previews и source
  relationship IDs удерживаются; неполный граф вызывает атомарный отказ.
  Собственные пять узлов SmartArt и Excel.Sheet.12 проверены в Word 16.0 build
  16.0.17932: два публичных цикла, нативная правка узла или A1, повторное открытие
  и следующий цикл, неизменность исходника и отказ при нулевом бюджете потерь.
  Это сохранение выбранных объектов, не полнота визуального оформления.
- Колонтитулы сохраняют source part bindings и редактируемый текст. Два цикла
  всех шести типов проверяют bytes/targets; обычные header/footer открываются
  в Word. Остаются native first/even content, другие OLE classes и previews,
  а также нативная правка объектов в колонтитулах.
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

- Текст небольшой страницы сохраняется в двух публичных PDF/JSON циклах
  относительно оригинала: извлечённые glyph bounds больше не обрезают поточный
  текст после изменения шрифта. Reflow имеет расположенный LOSS компоновки.
  Проверка native plain text до публикации обнаруживает пропуски и отказывает
  атомарно. Это не приёмка исходных glyph positions, reading order, видимости,
  native forms/annotations и всех математических/графических представлений.
  Остаётся полноценный text/layout profile с координатами, шрифтами и clip state.
- Сгенерированные PDF сохраняют однозначный текст OpenType-лигатур через
  восстановление ToUnicode из встроенного GSUB без изменения shaping/пикселей.
  Собственный синтетический шрифт проверен нативно; неоднозначные соответствия
  не угадываются. Полный Unicode/shaping и самостоятельный inspection text scope
  остаются частью OF07; проверка пропусков не ослаблена.
- Исправлен конечный vector Form XObject clip: стек прямоугольных областей
  сохраняется через JSON и применяется к собственным native drawing streams.
  Два цикла с CropBox и всеми поворотами совпадают по всем RGB в MuPDF и Poppler.
  Криволинейный vector clip и graphics groups имеют расположенный LOSS/opaque
  source PDF; без проверенного surrogate экспорт отказывает атомарно.
  Stack/coordinates/command limits и отмена проверены; полного graphics state
  текста/изображений, blend/масок и source-object → fallback mapping ещё нет.
- Рисунки аннотаций и widgets исключены из извлечения page vectors в отдельной
  несохраняемой копии PDF. Они учитываются interaction ledger, не дублируются
  как содержимое страницы; исходные bytes не меняются. Группы прозрачности
  самого page content по-прежнему требуют поддержки или явного отказа.
- Конечный writer URI links/Text notes/highlights/text fields проверен двумя
  публичными циклами относительно оригинала, canonical fields/widgets, native edit,
  typed edit/delete и отменой на восьми вариантах геометрии. Основной текст не
  дублирует widget appearances; рабочая копия не меняет source bytes.
  Остаются полное дерево полей (включая orphan/inherited/default values), дополнительные
  actions, полная приёмка лимитов/бюджетов и самостоятельный inspection text scope;
  весь C-PDF-01 не закрыт.
- Canonical field tree имеет самостоятельный bounded аудит parents/orphans,
  ссылок/cycles/depth и дополнительных свойств с расположенными opaque records.
  Строковый `/DV` обычного text field переносится; явные edit/delete, конфликт
  repeated fields и default limit проверены. Отдельный `/P` сохраняет различимость
  widgets при native object deduplication. Полная реконструкция иерархии/inheritance
  остаётся открытой; audit не заменяет её реализацию.
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
  ARIA/role/dir вне профиля диагностируются; полное дерево доступности,
  экранный диктор и responsive layout остаются открытыми.
- Общие Table/Row/Cell semantics заполняют роли, scope, headers и группы строк.
  Типизированные правки имеют приоритет; удаление не возвращает legacy атрибуты.
  Некорректные ассоциации остаются в source profile с расположенной диагностикой.
- Caption paragraphs и таблица имеют общие anchors; caption_ids задают явную
  привязку, включая перенос к несоседнему абзацу, удаление связи и пустую подпись.
  Текст/списки/ссылки сохранены; неизвестные caption blocks остаются в source profile.
- Column groups и `scope=colgroup` используют общие логические интервалы;
  два цикла с объединениями, правками/удалением и необъявленными столбцами проверены.
  Прежние HTML JSON мигрируют однократно; неоднозначные связи получают диагностику,
  удалённые общие данные не возвращаются из legacy расширений.
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

## Сокращение PDF-движков (OF17, P1)

- Стандартный `pdf` содержит только PyMuPDF. pypdf, pdfplumber и pdf2docx со своими
  цепочками исключены из этого профиля; узкие альтернативы подключаются явно.
  Небольшие проверки/Info metadata обслуживает собственный слой на выбранном
  установленном движке, без дополнительного парсера.
- Заменить основной прямой PDF → DOCX маршрут собственным rich PDF → OpenDoc →
  DOCX, затем убрать pdf2docx/OpenCV/NumPy/fire из рекомендуемого converter набора.
  Прежний backend до приёмки остаётся отдельным `pdf-docx`; его тихое удаление
  не считается заменой. Сравнить много колонок, таблицы с/без линий, рисунки,
  шрифты, формулы/вектор и сканы с оригинальным PDF в Word, два цикла и нативную
  правку. Известные потери и unknown остаются явными; собственный parser с парой
  regex не заменяет PDF text/graphics engine.
- Для альтернативного pdfplumber route подтвердить собственные table/reading-order
  алгоритмы на одном PyMuPDF по тому же корпусу. После доказанного покрытия
  пересмотреть необходимость `pdf-layout` и его pdfminer/PDFium/Pillow цепочки.
- Сохранить отдельный permissive `pdf-text` до равноценной замены: переход на
  PyMuPDF не объявляется расширением лицензионной свободы этого BSD-профиля.

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
