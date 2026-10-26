# Document quality corpus

## Захват PDF TextLayout

`tests/readers/test_pdf_text_layout.py`: 29 проверок режима
`ImportOptions(pdf_text_layouts=True)` и прямого reader. Проверены точные native
матрицы, отдельные fill/stroke/clip/ignore occurrences, source FONT/face, два
JSON-цикла, crop/rotation и отсутствие выдуманного page frame для UserUnit.
Sentinel не становится физическим глифом; исходный PDF сохраняется и даёт
прежний render после JSON. Неизвестные face/program и дубликаты остаются unknown.
Source/native/Model budgets и поздняя отмена не меняют исходную модель.
Повторный захват не дублирует pages, layouts, source snapshot или диагностику.
Проверены JSON transport и отказ неподдержанного writer без замены целевого файла.

`tests/readers/test_pdf_layout_bindings.py`: ещё 20 проверок точного logical mapping:
однозначный Unicode/origin/style/FONT, `fi` 2:1, snapshot v2, два JSON-цикла,
stale после правки и неизвестность при несовпадении или неоднозначности.
Повторный захват сохраняет anchors/ranges, extra и сторонние occurrences;
отмена после verify=True не меняет исходную модель. Оба capture модуля — 49 passed.

Совместно с PDF font binding/native placements/Model contracts/export guards,
API, PDF writer и отменой импорта — 221 passed. В установленном `pdf` extra только с PyMuPDF
публичный режим сохраняет TTF post-2/post-3 и OTF/CFF через два JSON-цикла без
fontTools/Office/HTML/Pillow. CI использует расширенный
`tools/pdf_ligature_smoke.py`: проверены verified logical clusters/ranges,
сохранение FONT payload, snapshot v2 и stale после изменения стиля.
Эти связи не подтверждают полный paint/visibility state или native writer projection.
[Хеши и границы](pdf-text-layout-capture-evidence.json).

## Общий gate экспорта и физического препарирования

Общий набор для защиты glyph layout при экспорте и аудита CFBF: 2304 passed,
3 skipped. Единственное предупреждение — намеренный duplicate ZIP fixture.
Дополнения sfnt приняты отдельно после сбора общего набора: 203 проверки
Anatomy/sfnt, включая 26 native sfnt и 13 общего API/CLI. Это не повторный полный
прогон всех writer на изменённом sfnt-профиле. Установленный актуальный базовый
wheel прошёл package smoke; все его Python-файлы совпадают с исходниками и
установленными файлами, дополнительных font/PDF движков в окружении нет.
SHA и границы проверки — в [машинном свидетельстве](binary-inspection-evidence.json).

## Привязки шрифтов PDF

Рабочая PDF font binding проверяется `tests/readers/test_pdf_font_bindings.py`:
43 проверки режимов рисования, поворота, Unicode continuation, точного font digest,
дубликатов, ограничений и отмены внутри native font copy. Сравниваются привязки
и пиксели до/после; отсутствующий backend не заменяется подбором по имени.
Static OTF/CFF связывается по точным bytes внутренней таблицы, а два контейнера
с одинаковой CFF, variable/CFF2 профили не угадываются. Полный затронутый набор
PDF/native/Model/DOCX и установленный минимальный PDF-профиль описаны
в [свидетельстве привязок](pdf-font-binding-evidence.json).
`tools/pdf_ligature_smoke.py` проверяет не только экспорт, но и повторный импорт
с JSON: TTF post-2/post-3 и OTF сохраняют исходную программу в явной FontReference
без fontTools/Office/Pillow и других PDF-движков.

## Контрольные суммы standalone sfnt


`tests/test_sfnt_checksums.py`: 27 проверок таблиц и `head.checkSumAdjustment`.
Собственные TTF/OTTO wrappers сравниваются с независимым `fontTools.calcChecksum`
для длин 0/1/2/3/4/7 и границ 64 KiB. Реальный собственный шрифт проходит аудит
без импорта fontTools. Повреждения payload, directory checksum, adjustment,
padding и trailing bytes различаются без исправления исходника. Проверены
отсутствие/усечение `head`, бюджеты и отмена внутри большой таблицы.
Совместно с sfnt inventory и Anatomy — 66 passed. Это конечный checksum-аудит,
а не полная проверка структуры шрифта или отображения.
Общий API принимает явный `sfnt_checksums=True`; CLI — `--sfnt-checksums`.
Дополнительно проверены opt-in/default, снимок с/без payload, строгий тип флага,
отказ для другого контейнера, прежние общие квоты, CLI comparison и отмена внутри
аудита с восстановлением scope. Прямой sfnt/Anatomy набор: 79 passed.
Общий набор Anatomy для ZIP/XML, OPC, EPUB, PDF, CFBF и sfnt: 243 passed.
Базовый установленный wheel проверяет checksum API без fontTools;
исходники, wheel и установленные Python-файлы совпадают. SHA и границы — в
[свидетельстве checksum-аудита](sfnt-checksum-evidence.json).

## Структурный аудит sfnt

`tests/test_sfnt_structure.py`: 21 проверка каталога, пробелов tags, search fields,
ненулевого/усечённого padding, общих и вложенных ranges, zero-length таблиц,
явного TTC face, quotas findings, поздней отмены, строгих options и CLI comparison.
Здоровые собственные таблицы и реальный шрифт проходят аудит без импорта fontTools;
unknown trailer сохраняется opaque, исходные bytes не меняются. При nested overlaps
проверяется представитель пересечения, а не обещание полного попарного графа.
Общий Anatomy/sfnt/TTC набор — 355 passed. Установленный base wheel только с
`opendoc-model` проверяет healthy и повреждённый padding через native/common API.
Хеши и границы — в [свидетельстве структуры](sfnt-structure-evidence.json).

## Ограниченное переиспользование subsets

`tests/test_font_subset_cache.py` и `tests/test_font_subset_cancellation.py`:
29 проверок точных bytes/символов/настроек, сохранения всех name notices, смены
программы и параметров, no-subsetting, LRU/byte/entry bounds, неизвестных options,
ошибки, rollback отменённой вставки и отмены на hit. Сохраняются прежние публичные
DOCX гарантии отмены и назначения. Потоковый доступ к кэшу проверен отдельно.
Холодный и повторный DOCX exports совпали по embedded fonts, font table и body XML;
PDF — по программам, тексту и MuPDF-пикселям. Повторный запрос дал ноль вызовов
subsetter, исходная Model не менялась. Отдельный установленный `fonts` extra
проверяет те же bytes/notices и повторное использование без document engines.
CI использует `tools/package_smoke.py --fonts`; запуск workflow не выполнялся.
Остальные шрифтовые профили и внутренняя память движка этим не сертифицируются.
Хеши и границы — в [свидетельстве кэша](font-subset-cache-evidence.json).

## Отмена сокращения шрифтов

`tests/test_font_subset_cancellation.py`: 15 проверок. Отмена после populate,
subset, save и close, в том числе вместе с ошибкой движка, завершается явным
`OperationCancelledError`; открытый шрифт закрывается. Обычный отказ сохраняет
полную исходную программу. Ранний сигнал не допускает чтение файла; пути без
сокращения не импортируют fontTools. Прямой и публичный DOCX writer проверены
с реальным сокращением собственного шрифта: отмена сохраняет входную модель,
исходный шрифт и прежний файл назначения, временный результат удаляется.
Настройки сокращения и сохранения лицензионных уведомлений не меняются.
Это контроль границ сторонних вызовов, а не прерывание их внутренних циклов.
Совместный прогон с отменой Office export, сложным PDF/DOCX, opaque fonts
и PDF Unicode: 76 passed. SHA и область приёмки — в
[свидетельстве отмены](font-subset-cancellation-evidence.json).

## Совместимость с OpenDoc Model 0.19.0

Официальный wheel и MIT LICENSE проверены по SHA-256. Код соответствует принятому
consumer5 после нормализации переводов строк и исключения номера версии.
Другие записи lockfile не изменены. 11 проверок TextLayout и 21 проверка защиты
экспорта проходят с официальным Model; отсутствие API больше не скрывается skip.
Совокупная регрессионная приёмка на Windows/Python 3.12.13 охватывает все 3149
актуальных сценариев: 3146 passed, 3 skipped. Результат составлен из общего
прогона и целевой перепроверки всего модуля PDF mapping (12 passed): отмена
проверяется по фазе готового результата, отдельно проверены entry/preparation.
Производственный код между этими проверками не менялся; список testcase IDs
точно совпал с текущей коллекцией. Пропущены два сценария DjVuLibre и реальный
POSIX fork, недоступные на этом Windows-хосте. Единственное предупреждение —
намеренный duplicate ZIP fixture. Все 11 проверок TextLayout входят в общий набор;
отдельно те же 32 contract/export проверки прошли
на установленном wheel с точными locked версиями тестовых движков.
Базовый установленный wheel и минимальный DOCX-профиль без fontTools/PDF/Pillow
прошли smoke. Повторная сборка из sdist совпадает с wheel по всем payload;
Python-файлы зафиксированного снимка совпадают с тремя установленными профилями.
Область приёмки и SHA — в [свидетельстве Model 0.19.0](model-019-acceptance.json).
Точные статусы команд и сведение актуальных тестов — в
[регрессионном свидетельстве](regression-evidence.json).
Расширение конечного glyph reader и проекция в native writers остаются C-PDF-01.

## Физические таблицы шрифтов

`tests/test_native_font_ligatures.py`: 189 проверок конечного GSUB/ToUnicode-профиля.
Независимые бинарные таблицы GSUB и реальный собственный TrueType с `post` 1/2/3
сравниваются с прежним `_ligature_map(fontTools)` для lookup 4/7, coverage 1/2,
алиасов, неоднозначных/неизвестных компонентов и уже кодированного результата.
Другие post profiles, flags и GSUB 1.1 с FeatureVariations сохраняют fallback. Проверены смещения/индексы,
лимиты bytes/lookups/повторной работы и отмена в parser и PDF pipeline.
При поддержанном профиле импорт fontTools запрещён тестом. Реальный Story PDF
с `fi ti fi` после ремонта ToUnicode и перезагрузки сохраняет извлекаемый текст
и прежние MuPDF-пиксели. Это сравнение до/после в одном рендерере, не полная
независимая приёмка произвольных шрифтов или всего PDF.
Целевой набор GSUB/Unicode/PDF FONT/native face: 211 passed. Установленный базовый
wheel читает GSUB без fontTools; отдельный установленный PDF-профиль с одним
PyMuPDF проходит Story/ToUnicode-проверку без fontTools/Pillow/Office/HTML движков.
CI запускает `python -I tools/pdf_ligature_smoke.py` в свежем установленном `pdf`
профиле. Собственный `tests/native/data/ligature-post3.ttf` (MIT, 1320 bytes)
имеет фиксированные timestamps, copyright/license name records и SHA
`002ab3822db7196c8ba23fa443d5d4e7026301fdee7f89883045d6b4f70528ad`;
его генератор — `tests.test_native_font_ligatures.program`. Шрифт и gate входят в sdist.
SHA и границы этой проверки — в [свидетельстве GSUB](font-ligature-evidence.json).
Смешанные lookup 1/4 и 7→1/4 сравниваются с прежним reader, включая оба SingleSubst
formats, coverage 1/2, порядок lookups и отрицательный delta modulo 65536.
Повреждённые offsets/counts/glyph IDs и смешанные типы одного extension lookup
не дают частичную native mapping. Подстановки не исполняются этим reader.
Собственный MIT `tests/native/data/ligature-mixed.ttf` (1344 bytes) воспроизводится
`program(..., table=mixed_gsub(single_substitution(delta=0)))`; glyph outlines,
copyright и license records принадлежат проекту. Установленный `pdf` gate без
fontTools проверяет тот же шрифт через public writer, повторный импорт и JSON.
Текущий целевой набор шрифтов/PDF — 451 проверка; область и SHA описаны в
[свидетельстве смешанного GSUB](font-mixed-gsub-evidence.json).
Для post-2 дополнительно проверены повторяющиеся standard/custom имена,
коллизии с генерируемыми glyph names и пустые legacy names: результат совпадает
с прежним reader по числовым glyph IDs. Ошибочный numGlyphs и обрезанные Pascal
strings не дают частичной native mapping; сохранён fallback для engine recovery.
Собственный MIT `tests/native/data/ligature-post2.ttf` (1340 bytes) воспроизводится
`tests.test_native_font_ligatures.program(post3=False)`, с фиксированными timestamps
и copyright/license name records. SHA —
`fe20d45d0138c607e22dac6526ad414fb37d30b5b10a1185f790003100c85e1e`.
В установленном `pdf` extra без fontTools публичный writer сохраняет его полную
программу, извлекаемый текст и пиксели через два JSON-цикла. Текущий post-2 профиль
и исходные хеши — в [свидетельстве post-2](font-post2-evidence.json).

Собственный MIT `tests/native/data/ligature-post4.ttf` (1336 bytes) воспроизводится
`test_owned_post4_fixture_is_reproducible`. SHA —
`335485e769416135ca5e87dee7bee5b96b9be004ff2fbeb8e9e16d558aa3d31a`.
Проверяются числовая связь cmap/GSUB при повторяющихся printer codes,
неоднозначность и engine recovery при несовпадающем размере `post`.
В установленном `pdf` extra без fontTools проверяются полная программа, текст,
пиксели, повторный импорт и JSON-циклы; отдельные Story-тесты подтверждают,
что встроенная программа остаётся `post` 4, а исправление ToUnicode не меняет пиксели.
Границы — в [свидетельстве post-4 GSUB](font-post4-gsub-evidence.json).

`tests/test_native_font_reverse_gsub.py` проверяет соседний GSUB type 8/7→8:
coverage 1/2, пустые/односторонние/двусторонние контексты, общий storage,
порядок lookups, числовые glyph IDs и равенство прежнему fontTools reader.
Импорт fontTools на принятом пути запрещён тестом; проверяются повреждения,
все усечения собственной таблицы, квота повторных ссылок и отмена внутри coverage.
Reverse substitution не выполняется и не создаёт Unicode mappings.
Собственный MIT `tests/native/data/ligature-reverse.ttf` (1368 bytes) воспроизводится
`test_owned_reverse_fixture_is_reproducible`; SHA-256:
`e92a9b8819c68d89506ecac9e2bc06d3d616cd17e17ffbe94efc1f5913b76767`.
Минимальный установленный PDF-профиль проверяет полную программу, текст,
пиксели, повторный импорт и два JSON-цикла. Реальные Story-тесты для GSUB 1.0/1.1
и post 1/2/3/4 проверяют исправление ToUnicode без изменения пикселей.
Результаты — в [свидетельстве type 8](font-reverse-gsub-evidence.json).

`tests/test_native_font_context_gsub.py` проверяет GSUB types 5/6 format 3 и 7→5/6:
coverage 1/2, общий storage, порядок lookups и SequenceLookupRecords,
прямые/обёрнутые таблицы, отказы для повреждений и всех усечений собственных
таблиц. Ссылки на вложенные lookups проверяются без рекурсивного обхода и выполнения;
общие coverage повторно расходуют бюджет, отмена не попадает в fallback.
Собственные MIT `ligature-context5.ttf` (1360 bytes) и `ligature-context6.ttf`
(1384 bytes) воспроизводятся `test_owned_context_fixture_is_reproducible`.
Их полные программы, текст и пиксели проверяются в установленном PDF extra
без fontTools через два JSON-цикла; GSUB 1.0/1.1 и post 1/2/3/4 приняты
также реальными Story PDF с неизменностью пикселей после ToUnicode repair.
SHA, результаты и границы — в [свидетельстве контекстов](font-context-gsub-evidence.json).

`tests/test_native_font_context_rules.py` проверяет types 5/6 format 1 и 7→5/6:
числовые glyph IDs, coverage 1/2, NULL/shared RuleSet, повторные правила,
порядок lookups, граничные длины последовательностей и записи действий.
Повреждения, все усечения, общий лимит повторных ссылок и отмена проверяются
без частичного результата. Нативный путь запрещает импорт fontTools и совпадает
с его прежним reader. Два собственных MIT fixtures `ligature-rules5.ttf`
(1376 bytes) и `ligature-rules6.ttf` (1392 bytes) воспроизводимы тестом;
установленный PDF extra проверяет полные программы, текст, пиксели и два
JSON-цикла без fontTools. Реальные Story PDF охватывают GSUB 1.0/1.1 и post 1/2/3/4.
Подробности — в [свидетельстве правил](font-context-rules-evidence.json).

`tests/test_native_font_context_classes.py` проверяет types 5/6 format 2,
extension 7→5/6 и оба ClassDef formats: coverage 1/2, shared definitions,
class 0, неописанные glyph IDs, class labels за пределами числа глифов,
порядок lookups и совпадение с прежним fontTools mapping без его импорта.
Все усечения, повреждённые offsets/counts/IDs, overlap/order диапазонов,
общая квота и отмена внутри ClassDef проверяются без частичного результата.
Собственные MIT `ligature-classes5.ttf` (1376 bytes) и `ligature-classes6.ttf`
(1412 bytes) воспроизводятся тестом. Минимальный установленный PDF-профиль
проверяет полные программы, текст, пиксели, повторный импорт и два JSON-цикла;
Story PDF покрывают GSUB 1.0/1.1 и post 1/2/3/4.
Результаты и SHA — в [свидетельстве классов](font-context-classes-evidence.json).

`tests/writers/test_pdf_resource_fonts.py` проверяет публичный и прямой PDF writer:
FontReference для standalone TTF/OTF, отсутствие системных шрифтов и subsetting,
унаследованный стиль, два JSON-цикла, неизменность модели, текста и пикселей,
идентичность полного font program и отдельных paint bindings для одноимённых fonts.
Отказы покрывают неверный face, TTC/raw CFF, повреждение, отсутствие glyph coverage,
права встраивания и подмену встроенных байтов при сохранённых именах. Проверены
квота до записи font resources, отмена и сохранность существующего целевого файла.
`tools/pdf_ligature_smoke.py` запускает публичный writer из установленного wheel
без fontTools/Pillow/Office/HTML и иных PDF-движков. Собственный MIT fixture
`tests/native/data/own-cff.otf` (904 bytes) воспроизводится функцией
`tests.writers.test_pdf_resource_fonts.cff_program`: геометрия создана в проекте,
сторонние glyph data отсутствуют, timestamps и license/name records фиксированы.
Результаты и границы — в [свидетельстве PDF-шрифтов](pdf-resource-font-evidence.json).
В целевом наборе прошло 356 шрифтовых/PDF/DOCX проверок, ещё 87 проверок
охватывают PDF pagination, interactions, page geometry, outlines и raster roundtrip;
всего 443. Строгая сборка документации, lint, типизация и проверка лицензионного
инвентаря также проходят. Это целевая приёмка изменения, не повтор полного набора.

Нативный GSUB 1.1 без FeatureVariations проверяется теми же независимыми бинарными
lookup/coverage fixtures и сравнением с fontTools; импорт engine на принятом пути
запрещён тестом. Дополнительно проверяются усечённый расширенный заголовок,
ссылки в его середину, неизвестные версии и fallback для ненулевого
featureVariationsOffset. Реальный Story PDF для обеих версий после изменения
ToUnicode и перезагрузки сохраняет текст и прежние пиксели. Целевой набор
GSUB/Unicode/public PDF FONT export: 106 passed, в том числе 67 проверок GSUB.
Хеши и границы — в [свидетельстве GSUB 1.1](font-gsub11-evidence.json).

`tests/writers/test_html_resource_fonts.py`: 40 проверок публичного/прямого
HTML writer, TTF/OTF, face None/0, унаследованных стилей, двух JSON-циклов,
точных байтов data URI и CSS bindings без импорта fontTools. Проверены
ошибки программы/face/coverage/прав, сохранность целевого файла, квота до записи
ресурса и отмена с очисткой. Общий затронутый набор — 358 passed; ещё 70 проверок
охватывают HTML stages, отмену web/TeX export и семантику таблиц.
Установленный базовый пакет проходит `python -I tools/html_font_smoke.py`
без всех необязательных движков; gate подключён к CI перед установкой extras.
В браузере два одноимённых TTF сохраняют отдельные aliases, загружаются и дают
ширины лигатур 0.5/0.9 em; собственный OTF/CFF для AB даёт 1.2 em.
Это проверка выбранных fixtures, не произвольных fonts или исходного shaping.
Состав и метрики — в [свидетельстве HTML-шрифтов](html-resource-font-evidence.json).

`tests/readers/test_html_fonts.py`: 31 проверка импорта статического data-URI
font-face, включая два реальных HTML/JSON-цикла, наследование и точные варианты,
две одноимённые программы с разными text bindings, дедупликацию и отказ от
неоднозначного/частичного выбора. Проверены неподдержанные descriptors и источники,
неверный wrapper/base64, budget до декодирования, 1024-rule предел и отмена.
Неизвестный профиль сохраняет исходный HTML и явные диагностические записи.
Целевой набор HTML reader/writer/cascade/table/accessibility/cancellation —
173 passed. `tools/html_profile_smoke.py` проверяет установленный extra `html`
без fontTools/Office/PDF/Pillow: TTF/OTF программы и FontReference сохраняются
через два полных цикла. Данные — в [свидетельстве HTML font import](html-font-import-evidence.json).

`tests/test_native_fvar.py`: 21 проверка таблицы fvar, Fixed 16.16, optional
PostScript name IDs, offsets, arrays, budgets и отмены. Базовые поля resolver
совпадают с прежним reader без выбора named instance. Совместный шрифтовой
и PDF/DOCX/Unicode прогон: 186 passed. На 24 системных TTF все базовые поля
совпали, включая variable Bahnschrift; все 24 прошли без импорта fontTools.
Произвольные instance coordinates и variation programs этой приёмкой не покрыты.
Базовый установленный wheel проверяет тот же путь без fontTools; hashes и
границы сохранены в [свидетельстве fvar](font-fvar-evidence.json).

Минимальный установленный DOCX-профиль принят без fontTools/PDF/Pillow/NumPy:
direct/public flow API, crop таблицы и source mapping; собственный статический TTF
побайтно сохранён через два JSON/DOCX-цикла вместе с текстом и FONT references.
Исходная модель и fixture не меняются. В профиле пять установленных пакетов:
Formats, Model, python-docx, lxml, typing-extensions. Полный шрифт сохраняется
вместо subsetting. CI устанавливает только extra `docx` для этой проверки.
Это конечный asset/profile gate; нативный рендер всех функций Word не заявляется.

`tests/test_native_font_face.py`: 50 проверок native face metadata. Все версии
OS/2 0–5, embedding/subsetting flags, signed widths и italicAngle сверяются
с прежним engine reader; импорт fontTools на поддержанном пути запрещён тестом.
Проверены post 1/2/3, границы Pascal storage, отсутствие permission table и отмена;
собственный CFF/OTF original покрывает maxp 0.5 без импорта fontTools.
В 24 системных TTF все поля face совпали; 23 прошли без импорта fontTools,
variable Bahnschrift сохранил прежний engine-путь.
Совместный прогон face/cmap/name/baseline и PDF/DOCX/Unicode: 164 passed;
дополнительная CFF-проверка принята отдельно без изменения runtime source.
В установленном базовом wheel статический face прочитан без fontTools; SHA и
границы приёмки записаны в [свидетельстве face](font-face-evidence.json).

`tests/test_native_font_cmap.py`: 68 проверок объявленного Unicode coverage.
Собственные бинарные subtables сравниваются с fontTools для formats 0/2/4/6/12/13,
delta/array адресации, нулевых IDs, non-BMP, приоритета и повторных encoding records.
Resolver сохраняет все поля face и embedding/subsetting flags; native профиль
запрещает вызов `getBestCmap` тестом. Для 0/6 проверяются весь face без импорта
fontTools, крайние codepoints, пустой массив, приоритет, нулевые IDs, точный размер,
выход за BMP, бюджет нулевых entries и отмена внутри массива.
Неканонический format 6 с лишними данными сохраняет результат engine fallback.
Legacy fallback, повреждения, work budgets,
отмена и закрытие font handle проверяются отдельно. На 24 системных TTF весь
face совпадает с engine-путём, cmap во всех 24 прочитан нативно.
Вместе с face/fvar/name/baseline, PDF/DOCX complex/model, opaque fonts и PDF Unicode —
215 passed, включая WOFF/TTC сценарии снимка входа и выбора первого collection face.
Прямой helper для 0/6 проверен в установленном базовом wheel без fontTools;
неохваченные профили face сохраняют прежний движок. SHA и границы
приёмки — в [свидетельстве cmap](font-cmap-evidence.json).
Для format 2 дополнительно проверены single-/double-byte codes, общие subheaders
и glyph storage, отрицательный delta, переход в нулевой ID, пустые ranges,
приоритет Unicode-записей и отказ от повышения legacy-кодировки в Unicode.
Десять сценариев запрещают импорт fontTools и сравнивают полный FontFace с engine;
повреждения не дают частичный mapping, повторные/нулевые entries расходуют бюджет,
отмена прекращает native walk, неканонический key сохраняет engine recovery.
Общий текущий набор шрифтов/PDF — 475 passed. Установленный base wheel только
с Model проверяет format 2 и полный resolver через `tools/package_smoke.py`.
Границы и SHA — в [свидетельстве cmap 2](font-cmap2-evidence.json).

`tests/test_native_font_names.py`: 59 проверок native name selection и fallback.
Unicode/Windows UTF-16, non-BMP, английский Mac Roman, порядок языковых записей,
пустые обязательные имена и aliases сравниваются с независимым fontTools reader.
Name version 1 с language tags и Windows ShiftJIS/GB2312/Big5/EUC-KR/Johab
совпадают с прежним reader без импорта fontTools; full resolver также проверен.
Однобайтовые Macintosh и языковые варианты сравниваются по каждому ненулевому
байту репертуара; ISO ASCII/UTF-16BE/Latin-1 и порядок предпочтений — отдельными
fixtures. Полный face с Cyrillic/Turkish name records проверяется без импорта
fontTools. На обычном пути импорт fontTools запрещён тестом. WOFF, неизвестные Mac encodings,
восстановление нечётного UTF-16 и double encoding сохраняют прежний результат
движка; повреждённые диапазоны, бюджеты общих строк и отмена проверяются отдельно.
Исходные bytes и права шрифта этой операцией не переписываются.
Полный шрифтовой/PDF/DOCX/Unicode прогон для name 0/1 и Windows/Mac/ISO codecs:
242 passed. Установленный базовый wheel проверяет version 1, ShiftJIS, Mac Cyrillic,
турецкий Mac Roman и ISO Latin-1
без fontTools; BCP 47 locale selection и восстановление malformed strings
нативной поддержкой не объявляются.
Дополнительный read-only корпус: первые 24 TTF из Windows Fonts в порядке Path
полностью совпали с прежним выбором имён; все прошли native-путь без fallback.
В отчёт включены только имена файлов и hashes, программы шрифтов не копируются
в репозиторий. Проверка относится к извлечению имён, не к полному рендеру.
Результаты — в [свидетельстве](font-names-evidence.json).

`tests/test_word_font_metrics.py`: 12 проверок baseline helper. Результат native
TTF-пути совпадает с fontTools на разных unitsPerEm, знаках ascent/descent и lineGap;
импорт движка на этом пути запрещён тестом. Прежнее поведение WOFF и lazy-чтения
метрик при повреждённой посторонней таблице сохранено. Отмена выходит исключением,
без запуска fallback; неизвестные метрики остаются неизвестными.
Вместе с PDF → DOCX complex/model и opaque-font сценариями — 66 passed.
Установленный базовый wheel проверяет тот же helper без fontTools; формула
и права embedding/subsetting не подменяются новым выбором метрик.

`tests/test_sfnt_inspection.py`: 26 проверок конечного standalone sfnt-профиля.
Собственный TTF сравнивается с независимым fontTools directory reader по всем
смещениям, размерам, объявленным checksums и исходным bytes таблиц. Дополнительные
fixtures проверяют `OTTO`, неизвестные tags, повреждения, лимиты и отмену.
`tests/test_anatomy_sfnt.py`: 13 проверок общего API и CLI — исходные bytes целиком,
таблицы, границы общего бюджета, отмена внутри parser, сравнение metadata отдельно
от payload, явный профиль ZIP/sfnt polyglot и отсутствие ложного PDF по маркеру
внутри программы. Автоматический вложенный обход этой приёмкой не подтверждается.
Инспектор проверен из установленного wheel в окружении только с Formats и
официальным Model 0.19.0: исходник модуля совпадает побайтно, fontTools/PyMuPDF/Pillow
отсутствуют, исходный payload извлекается точно. Это приёмка инвентаря таблиц,
а не проверки glyph programs, shaping, variable instances или лицензии шрифта.

## Выбранный face TTC

`tests/test_native_font_collection.py`: 34 проверки TTC 1.0/2.0, TrueType/CFF,
общих таблиц, DSIG declaration, выбора обоих faces, строгого index, границ,
квот и отмены. Native metadata и абсолютные ranges сравниваются с fontTools;
импорт движка на принятом пути запрещён. Resolver сохраняет первый face и fallback
при неподтверждённом collection profile. Исходные байты остаются неизменными.
Общий набор sfnt/шрифтов/HTML/PDF и TextLayout — 729 passed.
В 15 независимых системных TTC весь FontFace совпал с прежним reader; 14 прочитаны
без fontTools, один файл превышает 32 MiB и использует прежний fallback.
Установленный base wheel только с `opendoc-model` проверяет два различных faces
и resolver. Автоматическое перечисление всех системных TTC и их embedding
не засчитываются; источник и границы — в [свидетельстве TTC](font-collection-evidence.json).

`tests/test_anatomy_font_collection.py`: ещё 27 проверок общего API/CLI:
выбор face, полная исходная коллекция и точные таблицы, JSON inventory, locators
с номером face, comparison scope, общие budgets, поздняя отмена, polyglot и
отказы по неверным/несовместимым options. Общий Anatomy/sfnt/TTC набор — 334 passed.
Установленный base wheel без fontTools проверяет тот же selected-face API;
его CLI сохраняет коллекцию побайтно и сравнивает выбранный face.
Совокупный обход всех faces и проверка подписи DSIG остаются открытыми.
Хеши и границы — в [приёмке Anatomy TTC](anatomy-font-collection-evidence.json).

## Нативные PDF glyph observations

Потребительский `tests/native/test_text_layout_consumer.py` принят отдельно на
Model `0.19.0.dev20261024+consumer5`, без изменения основной зависимости.
Одиннадцать проверок покрывают реальные placement matrices и FONT, `fi` 2:1,
ActualText 1:N, два JSON-цикла, range-aware edit и batch-инвалидацию fill/stroke,
unknown, атомарные отказы и 12 000 физических глифов с явным node budget.
Пакетная запись проверена на 16 реальных PDF-вхождениях и 1 245 точных кластерах;
прежний snapshot от SHA-проверенного установленного consumer2 сохраняет привязку
версии 1 через два JSON-цикла и обновляется до версии 2 только явно.
Область и hashes записаны в [свидетельстве приёмки](text-layout-consumer-evidence.json).
Оба пакета установлены из отдельных preview wheels; runtime files Formats
проверены по hash, объявленные зависимости совместимы. Сборку/проверку воспроизводит
`tools.text_layout_preview`; артефакты отмечены dev, не являются публикацией и
не закрывают рабочий reader/writer C-PDF-01.

`tests/native/test_pdf_placements.py` проверяет точные матрицы через native text
device: исходные text/CTM/Form operators, отдельные fill/stroke/ignore/clip,
shear, наследуемый Rotate, реальные границы собственных прямоугольных глифов и
`fi` continuation. `own_placement_font` создаёт собственную single-face TTF с
детерминированными bytes; fontTools нужен только генератору fixture. PDF собирается
из wire objects/commands, без Formats writer. Program digest совпадает с исходным
TTF, raw sentinel не превращается во второй физический glyph.

Проверены точная compact metadata quota, glyph/span budget до font copy,
однократное хеширование программы и суммарный font bytes budget, отмена внутри
callback, неизвестный native профиль и нечисловая матрица до native glyph bound.
После ошибки/отмены повторное чтение, исходные object dictionaries и свежие
растры прежние. Ошибки переносятся за C boundary без заимствованных wrappers.
Native memory/time, полная видимость и общий semantic projection этим не приняты.

`tests/native/test_pdf_text_spans.py` использует прямые PDF objects/commands,
без writer Formats: обычный текст, `2 Tr`, `3 Tr`, zero alpha и частичный clip.
Проверены исходные Unicode/origin, дубли fill/stroke, raw ligature continuation,
unknown Unicode, отсутствие alias на mutable backend arrays, точные metadata budgets,
отмена внутри glyph copy и после native call. Неверные native shapes имеют явный
отказ; источник и контекст сохраняются. Default bytes прежнего wire fixture не меняются.

Свежий native raster при отключённом кэше совпадает до/после инспекции на 0/90°.
Для inherited Rotate после успеха/ошибки совпадают активные словари объектов и
повторный рендер. Независимый Poppler при 108 dpi показывает `Visible`, synthetic-bold
`Both` и только `Pa` от `Partial`; hidden/zero-alpha текст не виден, хотя span inventory
его сохраняет. Это конечная read-only приёмка, не доказательство полной видимости,
shaping, порядка чтения или PDF → DOCX fidelity. Установленный минимальный PDF-профиль
проверяется в `tools/pdf_profile_smoke.py` без остальных PDF/Office/image backend.

`tests/readers/test_pdf_paint_matching.py` проверяет переход от нативных наблюдений
к paint-признакам Model: единственное точное совпадение, неоднозначные fill/stroke,
недопустимые Unicode scalars/U+FFFD, ligature continuation и неоднозначные FONT
bindings. Отмена проверяется внутри сравнения Unicode; выбранные квоты импорта
дают адрес и тип ограничения. Прямой wire PDF подтверждает очистку устаревших
paint-признаков после изменения текста, сохранение причины неопределённости через
JSON и неизменность исходных bytes. Это конечная проверка привязки, а не полная
проекция глифов или закрытие C-PDF-01.

## Независимые бинарные оригиналы

`own_cfbf` собирает CFBF v3/v4 непосредственно из header, FAT/DIFAT/miniFAT,
directory entries и заданных bytes. Оригиналы содержат разрывные обычные и mini
цепочки, padding и unclaimed сектор. `tests/test_anatomy_cfbf.py` подтверждает
payload, диапазоны, raw metadata, полное восстановление физических bytes, старый
v3 high DWORD, extended DIFAT, неверные цепочки/имена, квоты, отмену и CLI.
Контролируемые изменения wire bytes дают явный отказ либо неизменённый физический
инвентарь, без положительной оценки полноты.

`tests/native/test_cfbf_windows.py` отдельно открывает только эти собственные
оригиналы read-only через Windows IStorage и сравнивает Small/Large bytes для
v3, v4 и старого v3. COM storage API не активирует вложенный объект; source bytes
после закрытия прежние. На других платформах эти три проверки пропускаются.
Это конечная приёмка чтения потоков, не storage tree validation и не проверка
семантических правок OLE. Базовый установленный wheel проверяет CFBF/miniFAT
без olefile, Office, PDF и XML backend.

`tests/binary_fixtures.py` собирает воспроизводимый ZIP/XML DOCX с вложенной таблицей,
PNG, внешней гиперссылкой и неизвестной бинарной частью. PDF собирается напрямую
из объектов, xref offsets, команд и Flate-потоков; 2×2 RGB изображение имеет
независимо заданные pixels. Ни один оригинал не создаётся нашим writer.

`tests/test_anatomy.py` проверяет wire/content fingerprints, реальные XML-узлы и
атрибуты связей, opaque payload, CRC, unsafe/duplicate names, XML DTD в UTF-8/16,
квоты/отмену, отсутствие обязательных Office/PDF декодеров для ZIP и признак ремонта
PDF. CLI выгружает части под собственными именами и не заменяет существующий каталог.

`tests/test_anatomy_content_types.py` задаёт OPC manifest после payload в ZIP.
Проверяются extensionless UTF-16 XML, `+xml`, приоритет overrides, case-insensitive
extension defaults, declared binary с именем `.xml`, прежний extension fallback,
ошибочные bindings, DTD, единый бюджет и его однократный учёт manifest.
Отмена после manifest не допускает чтения следующих частей; oversized manifest
отвергается до открытия payload. `--opaque-xml` сохраняет прежние bytes без
разбора деклараций. Базовый установленный wheel проверяет extensionless OPC XML
без дополнительных зависимостей.

`tests/test_anatomy_opc.py` проверяет корневые/частичные связи, внешние Target,
фрагменты, несколько путей, недостижимые циклы и подключение компонента к root.
Missing owner/target, инфраструктурные targets, unsafe URI, duplicate Id,
неизвестные mode/markup, missing Content Type/Override и неразобранные `.rels`
имеют located findings и не дают ложного полного обхода. Обычный binary с именем
`.rels` вне relationship directory остаётся data part. Проверены неизменяемые
snapshots, независимая JSON-копия, `opc_changed`, отмена внутри resolver
и отсутствие OPC claims при opaque inspection.

`tests/test_anatomy_epub.py` собирает независимые ZIP/XML originals с extensionless
OPF/XHTML в UTF-16, percent-encoded href, binary под именем `.xml` и двумя rootfiles.
Проверены совместные ресурсы, конфликтующие типы/дубликаты, missing части,
точное определение mimetype, DTD, `xml:base`, remote rootfiles/outside ссылки, общий XML-бюджет
и отмена после OPF до чтения ресурсов. ZIP open spy подтверждает однократное чтение;
opaque inspection сохраняет bytes. Базовый установленный wheel проверяет этот
маршрут без BeautifulSoup/EbookLib/lxml; это проверка контейнера, не EPUBCheck
и не визуальная/семантическая приёмка всех ресурсов книги.

Инвентарь `EpubAudit` дополнительно проверен на отдельных manifest occurrences
всех rendition, исходных атрибутах/адресах, неизменяемости и независимом JSON,
`epub_changed` и отсутствии положительной оценки полноты. HTTP(S), protocol-relative,
file/data/javascript/mailto адреса остаются `external-unassessed`; тест запрещает
открытие файлов, создание sockets и URL fetch при inspection bytes. Неверные поля,
буквальные дубликаты и отвергнутый URL дают адресный отказ. Квота XML ограничивает
и внешние записи; отмена внутри инвентаризации не читает content parts. Строгий
EPUB reader продолжает отвергать внешние ресурсы; источник остаётся прежним.
Локальный URL-профиль дополнительно проверяет корректные Unicode/percent paths,
однократное декодирование, фрагменты и dot segments. Некорректные escapes/UTF-8,
controls/пробелы, query и encoded separators отказывают по исходному XML-адресу
до чтения content parts. Нативный и публичный EPUB import также отвергают
повреждённые ссылки при наличии реально существующего «исправленного» имени,
не выбирая другой ресурс и не меняя архив. Новые 30 inspection и 10 reader
проверок входят в профильный EPUB/Anatomy прогон: 334 passed.
Установленный базовый wheel проверен без EPUB/font/PDF движков;
SHA и границы — в [свидетельстве локальных URL](epub-local-url-evidence.json).
Полный 2595-test прогон Model 0.19.0 относится к снимку перед этим EPUB-изменением;
его новый локальный профиль принят указанным отдельным набором.

`tests/native/test_binary_compatibility.py` проверяет, что нативная правка меняет
содержимое только `word/document.xml`, сохраняя PNG, `.rels` и opaque bytes;
сопоставляет таблицы/пиксели/диагностику с фактическим оригиналом.
`tools/document_anatomy_word_acceptance.ps1` принят в Microsoft Word 16.0,
build 16.0.17932: одна страница, корневая таблица шириной 120 pt, одна картинка и
одна гиперссылка сохранены; файлы read-only не изменились. Независимые Poppler
PNG при 108 dpi совпали вне области единственной правки `Before` → `Edited`.
Повторяемая проверка — `tools/document_anatomy_visual_check.py`.
Это конечный native-edit fixture, а не полная семантическая приёмка Word.
Обработка default/preserve `xml:space` и отсутствующего `pgSz` rich reader
остаётся открытой задачей. У sparse DOCX оригинала Word показывает `AfterLink`
и страницу 612×792 pt; текущая модель содержит `After Link` и 595.28×841.89 pt.
Эти расхождения не скрываются стабильностью собственного JSON/экспорта.

`tests/test_opc_orphans.py` проверяет перенос физически недостижимых OPC частей
через rich Model и два JSON/DOCX цикла. Независимые оригиналы содержат циклические
компоненты, UTF-16 `.rels`, внешний target, зависимость от достижимого XML со
своими связями, неизвестный binary и коллизии URI. Payload выбранных частей
совпадают побайтно; редактирование текста/картинки и явная правка opaque bytes
не восстанавливаются из устаревшего снимка. Неверные связи/metadata, DTD,
embedded-byte quota и отмена, включая копирование выходного ZIP, сохраняют
источник, модель и прежнее назначение. Промежуточные файлы удаляются.

Microsoft Word 16.0 открывает результаты Model/JSON-экспорта обычного fixture
и варианта с `/custom/main.xml`: доступны изменённый текст, одна таблица и
одна картинка. Это проверка читаемости; она не подтверждает геометрию страницы,
поведение произвольного вложения или полный lossless-профиль DOCX.

`tests/native/test_docx_consumer_contract.py` проверяет на прямом OPC/XML tab stops
отдельно от run tabs, `noBreakHyphen`, text/run offsets, сохранение native токена
при граничной вставке, явную замену дефиса и разделители пустых абзацев ячейки.
Merge остаётся физическим; отсутствие владельца `.rels` даёт явный отказ.
Потребительская gate из десяти случаев проходит на локальном установленном wheel
с Model 0.18.0 и lxml 6.1.3, без python-docx и других format extras.
Официальный выпуск и повторная приёмка реального корпуса остаются открытой работой
[C-DOCX-NATIVE-TEXT-01](format-requests.md#c-docx-native-text-01).

`tests/test_text_projection.py` проверяет инвентарь потерь Model → Text, исходные
адреса/provenance, таблицы и повторные occurrences, вложенное содержимое ячеек,
два JSON-цикла, конфликтующие ссылки, выбранные бюджеты и отмену.
Графовые поля оцениваются агрегатно; assessment_complete не повышается.

## Диагностика legacy Text

`tests/test_text_diagnostics.py` проверяет два Text/Model/JSON цикла, повторяющиеся
сообщения разных объектов, общий envelope Model, независимые вложенные
данные, неизвестные record fields, source node locators и выбранный бюджет.
Положительные semantic claims не переносятся в упрощённый view; отсутствие
оценки не становится подтверждением lossless. Некорректные metadata warnings
не отбрасываются молча.

На Model 0.18.1 дополнительно проверены публичные `Text.to_dict` и
`text_to_document`: не-JSON объект в extra/measurement отклоняется до вызова
его `__deepcopy__`, без подмены значения и изменения исходного Text. Общий codec
остаётся в Model; собственного обхода или копирования его схемы Formats не вводит.

`tests/readers/test_pdf_text_fallback.py` проверяет прекращение цепочки при отмене
и превышении лимитов, восстановление контекста, table-only результат и сохранение
source bytes/полного текстового результата при неактивном callback.
OCR diagnostics сравниваются в богатом и текстовом маршрутах; локальные индексы
warnings после fallback сохраняют отдельные occurrences. Тесты DjVu различают
отсутствующий процесс, ненулевой exit, timeout и пустой hidden text.

## FONT и сохранённый OOXML

`tests/writers/test_docx_opaque_fonts.py` строит собственный smartTag с
`OwnSmartToken` между обычными runs. Два публичных DOCX/Model/JSON цикла
сохраняют XML, исходник, FONT references и cmap выбранных font programs;
все глифы opaque-текста остаются в программах, дополнительного `font-glyphs`
LOSS нет. Известная `docx.smart-tags` LOSS остаётся при каждом импорте.
Проверяется full-program policy для retained OOXML и прежняя semantic subsetting
policy для обычного документа. Полнота opaque-only font inventory и отображение
всех возможных wrappers не выводятся из этой приёмки: C-FONT-OPAQUE-01 остаётся
открытым для этих профилей.

`tests/writers/test_pdf_unicode.py` constructs a project-owned OpenType font at
runtime with `fi` and `ti` ligatures. Its native Story PDF checks repeated text
and exact RGB pixel equality before/after ToUnicode restoration. No third-party
font is shipped; ambiguous or unknown glyph decompositions are negative controls.

The primary corpus is generated from source instead of storing opaque binary fixtures. Run:

```powershell
uv run python -m tests.corpus.scientific_report
uv run python -m tests.corpus.multiformat
```

The primary `scientific_report` fixture covers portrait and landscape sections,
named styles, numbering, headers and a page-number footer, hyperlinks, merged
tables, raster and SVG images, native OMML, and a footnote. Archive timestamps and
document metadata are fixed so identical dependencies produce identical bytes.

`multiformat.py` adds deterministic PDF, PPTX and EMF fixtures. It covers fixed PDF
page geometry, two-column text, tables, raster/vector commands, presentation text,
charts, tables, speaker notes and a native EMF package relationship. Nested chart
workbooks and outer OOXML archives have normalized timestamps, so two builds are
byte-identical.

`office/libreoffice-scientific-slides.pptx` is a committed compatibility profile
opened and re-saved by LibreOffice. Its producer/version, SHA-256 and expected WMF
part are recorded in `office/manifest.json`; the source content is generated by
`multiformat.py`.

Structural expectations live in `scientific_report.golden.json` and
`multiformat.golden.json`. Visual checks combine tolerant page occupancy bounds
with committed images under `visual/`. The perceptual regression normalizes page
size and antialiasing, then checks mean absolute similarity, difference-hash
distance and foreground intersection-over-union against explicit thresholds in
`visual/manifest.json`.

Regenerate page references only after reviewing an intentional visual change:

```powershell
uv run python -m tests.corpus.visual_references
```

`charts.py` builds a pure `DocumentModel` corpus of 14 rich chart fixtures (dual
axes, trendlines, error bars, per-point colors, combo, percent data labels).
Charts render deterministically through `pdf_writer` (fitz.Story) into PNG pages
compared perceptually against committed golden images in `visual/charts/`. The
per-chart pages and their thresholds live in `visual/charts/manifest.json`.

Regenerate chart references only after reviewing an intentional chart change:

```powershell
uv run python -m tests.corpus.charts
```

## Office provenance fixtures

`libreoffice-scientific-slides.pptx` is the reproducible source presentation from
`tests.corpus.multiformat`, opened and re-saved by LibreOffice 25.8.6.2 on Windows.
It contains only project-generated content. ZIP timestamps are normalized after
the office-suite roundtrip; the producer metadata and converted WMF media part are
left untouched. `manifest.json` records provenance, size, SHA-256 and structural
expectations.

The fixture is intentionally committed because office-suite serialization cannot
be reproduced in CI without that exact application and version. Source-first PDF,
PPTX and EMF fixtures remain generated during tests and require no office suite.

## Нативные fixtures

Каталог: `tests/corpus/native/`.

Созданы для этого проекта, без внешних документов и пользовательских данных.

- `native-edit.docx`: генератор `fixture_bytes` в `tests/native/test_docx_access.py`;
  split runs, header/footer, объединения, вложенная таблица, собственный PNG, OMML и секции.
- `zero-opacity.pdf`: PyMuPDF, страница 100×100 points, прямоугольник (10,10,90,90),
  красная заливка и синяя обводка с alpha=0. Приёмка: alpha сохраняется, raster белый.
- `vector-export.pdf`: та же геометрия с alpha=1. Приёмка: нативный экспорт сохраняет
  paint, геометрию и пиксели без растровых изображений.
- `unsupported-vector.json`: собственная модель с неизвестной командой. Приёмка:
  явное отклонение и сохранение прежнего выходного файла; surrogate проверяется отдельно.
- `text-pages.pdf`: собственные две страницы PyMuPDF с текстом Native PDF и второй
  страницей с поворотом 90°. Проверяет установленный extra pdf-text без PyMuPDF.

Файлы являются тестовыми входами, а не временными сборками. Контрольные SHA-256
вычисляются тестами для проверки неизменности частей и транзакций.

## DOCX: исходные ширины и smartTag

`tests/readers/test_docx_layout_roundtrip.py` создаёт собственные smartTag и таблицу
20×3 с колонками 10/80/10, длинным текстом средней колонки и фиксированным layout.
Два JSON roundtrip проверяются независимым чтением `word/document.xml`:
видимый текст, оболочка, `tblW`, `tcW` и grid widths. Отдельно проверены
`auto`, `nil`, процентная запись и явное изменение ширины ячейки.

Локальная приёмка Microsoft Word 16.0 build 16.0.17932 подтвердила одну страницу
во всех трёх файлах каждого случая, совпадение текста и ширины 48/384/48 pt
в таблице. Исходники открываются только для чтения, их SHA-256 не меняется.
Проверка не является полной визуальной приёмкой или проверкой произвольного DOCX.

Повторить при установленном Word:

```powershell
uv run --frozen pytest tests/readers/test_docx_layout_roundtrip.py --basetemp=.opendoc-formats/docx-word
./tools/docx_word_acceptance.ps1 -FixtureRoot .opendoc-formats/docx-word
```

Word — отдельная локальная программа; её отсутствие не заменяет проверку XML
и не означает выполненной нативной приёмки в CI.

## PPTX: нативные свойства фона, линий и таблицы

`tests/readers/test_pptx_visual_roundtrip.py` создаёт собственные слайды со
сплошным фоном в slide/layout/master, двумя осевыми freeform paths и таблицей
с наследуемым цветом текста. Проверяются два JSON roundtrip, приоритет ближайшего
фона, отсутствие мутации источника, размеры и сохранение editable custGeom,
отсутствие пустого `solidFill` для неуказанного цвета.

Microsoft PowerPoint 16.0 build 17932 подтвердил равенство нативных свойств
во всех трёх файлах каждого случая: RGB фона, типы/позиции/размеры фигур,
текст и цвета ячеек. Источники открываются read-only, SHA-256 не меняется.
Это не пиксельная или полная семантическая приёмка и не проверка всех тем Office.

```powershell
uv run --frozen pytest tests/readers/test_pptx_visual_roundtrip.py --basetemp=.opendoc-formats/pptx-native
./tools/pptx_visual_acceptance.ps1 -FixtureRoot .opendoc-formats/pptx-native
```

PowerPoint устанавливается отдельно; CI выполняет проверки XML и модели,
а локальная нативная проверка требует установленной программы.

## PDF: размещения растра и обрезка

`tests/writers/test_pdf_raster_roundtrip.py` самостоятельно создаёт растровые
страницы с рамкой и диагональю, повторяет один xref на двух страницах, размещает
несколько разноцветных изображений и обрезает страницу. Тесты охватывают
четвертьобороты изображения/страницы, soft mask и JSON.

После каждого из двух циклов результат сравнивается с оригиналом, а не только
с предыдущим результатом: число страниц/размещений, page rect/rotation, image bbox
и все RGB pixel bytes. Исходные bytes не изменяются. Отдельно проверены явная
правка геометрии, отмена и отклонение unsupported transform с сохранением старого файла.
Для этого конечного профиля результат пиксельно совпадает в проверенном PyMuPDF.
Другой raster engine и произвольный PDF не считаются проверенными этим тестом.

## HTML: язык и семантика таблиц

`tests/readers/test_html_accessibility.py` создаёт собственные документы,
выполняет два цикла через публичные API и JSON и сравнивает lang (в том числе
пустой и вложенный), caption/форматирование, th/scope/headers/IDs, группы строк,
заголовки, нумерацию и внутренние ссылки. Вложенные таблицы и пустая подпись
проверены отдельно; опасные символы в атрибутах экранируются. ARIA вне профиля
получает расположенный loss. Это структурная приёмка, без доказательства
браузерного accessibility tree или работы экранного диктора.

## DOCX: общая предпочтительная ширина

`tests/readers/test_docx_typed_widths.py` проверяет абсолютные и относительные
предпочтения таблиц/ячеек, physical units, отсутствие type, ноль, auto/nil,
отсутствующую ширину, два JSON/DOCX цикла, точную native запись и неизменность
исходника/модели. Старые JSON проходят публичный импорт до правки/удаления.
Отрицательная native ширина остаётся расширением. Прежний тест неверной ширины
проверяет сохранение старого результата при отказе.

`tools/docx_word_acceptance.ps1` подтверждает прежний текст, одну страницу и
колонки 48/384/48 pt. `tools/docx_typed_width_acceptance.ps1` открывает четыре
результата правок read-only в Word 16.0, проверяет preferred types и значения:
75.001% и 12.125 pt отображаются API Word как 75% и 12.1 pt. Точный XML сохраняется;
это дискретность Word, без утверждения о точном полном визуальном рендере.

```powershell
uv run --frozen pytest tests/readers/test_docx_typed_widths.py --basetemp=.opendoc-formats/width-native
./tools/docx_typed_width_acceptance.ps1 -FixtureRoot .opendoc-formats/width-native
```

## DOCX: формальная роль заголовка

`tests/readers/test_docx_headings.py` создаёт собственные документы с уровнями
1/2/3/9 без именованного стиля, native Heading 2, наследуемым пользовательским
стилем, прямым override и основным текстом. Проверяются JSON и два DOCX цикла,
document defaults, смена/удаление роли, неверные уровни и защита старого результата.
`tools/docx_heading_acceptance.ps1` открывает исходник и два результата read-only
в установленном Word, сверяет уровни структуры. Для явно изменённых ролей
сравнивает текст, имя/размер/цвет шрифта и интервалы с исходником. SHA-256 файлов
не меняется. Это конечная проверка свойств, без полной визуальной приёмки Word.

```powershell
uv run --frozen pytest tests/readers/test_docx_headings.py --basetemp=.opendoc-formats/heading-native
./tools/docx_heading_acceptance.ps1 -FixtureRoot .opendoc-formats/heading-native
```

## PDF: affine, обрезка и поток изображений

`tests/writers/test_pdf_raster_roundtrip.py` сравнивает два цикла с независимо
заданными native matrices для произвольного поворота, shear и отражений:
совпадают исходные RGB bytes и geometry. Невырожденность проверяется отдельно.
`tests/writers/test_pdf_docx_rasters.py` проверяет ImageCrop и углы 3/12.5/-17/90
по независимому Form-reference. Из-за двойного clipping у reference допускаются
различия антиалиасинга только в пределах 1.5 pixels от границы, а не внутри изображения.

Настоящие PDF → JSON → PDF циклы с поворотами страниц/изображений сохраняют
crop и RGB pixels точно. Собственные DOCX проверяют положение изображения
между абзацами, перенос на следующие страницы, центрирование, колонтитулы,
located LOSS для paragraph anchor и отказ при пустой обрезке, чрезмерной
рамке и PNG pixel dimensions. Исходник и модель не изменяются.

## PDF: перенос body-изображений у границы страницы

`tests/writers/test_pdf_flow_pagination.py` строит собственный DOCX с таблицей,
двумя изображениями, подписями и заключительным абзацем. Без повторной компоновки
этот источник получает `pdf-text-content` и сохраняет прежнее назначение.
С переносом двухкратный JSON → PDF экспорт сохраняет весь текст, видимую рамку
обрезанных изображений, поворот 0/3° и left/center/right alignment. Проверяются
отсутствие перекрытий с текстом и одинаковые страницы при 108 dpi между циклами.
Ширины страниц 200/240 pt включают перенос заключительного абзаца на строки;
сравнение текста нормализует whitespace, сохраняя все слова и число вхождений.
Отдельная приёмка исходных crop/rotation pixels остаётся в независимом
Form-reference наборе, а не выводится из одного совпадения двух generated PDF.
Poppler-рендер собственного двухстраничного примера проверен визуально.
Отмена, повторное переполнение и предел 32 повторов сохраняют назначение;
discarded native documents закрываются. Состав зависимостей и Model не меняется.
`tools/pdf_profile_smoke.py pdf` проверяет перенос в установленном wheel без
DOCX/Pillow/lxml и альтернативных PDF-движков.

## PDF: изображения в ячейках таблиц

`tests/writers/test_pdf_cell_images.py` строит собственные DOCX с обычной,
объединённой и вложенной ячейкой, картинкой, подписью, соседним и последующим
текстом. Проверяются три выравнивания, crop/rotation, два JSON/PDF-цикла,
отсутствие перекрытий и совпадение decoded RGBA программы с исходным PNG.
Negative case оставляет только изображение без текста: выход в поля нельзя
скрыть успешной проверкой текста. Измеренные grid proportions учитывают
горизонтальные/вертикальные spans, общий HTML-renderer сохраняет прежние стили.

Собственный MIT `tests/native/data/table-image.png` — 561 bytes, 120×180 RGBA,
SHA-256 `5f229f090b197209fe7703d18f3ce7a47ebb0eb2f1549e400e0748c1979372fe`.
Он воспроизводится `tests.writers.test_pdf_docx_rasters.own_pixels`; сторонних
изображений нет. Word независимо экспортирует три исходных DOCX: размеры растра
72×72 pt, pixel dimensions 120×180, подпись и последующий текст подтверждены.
Страницы могут отличаться: вложенная строка Word разбивается иначе; это явно
диагностируется, совпадение с source pagination не заявляется.

`tools/pdf_cell_image_smoke.py` проверяет вложенную таблицу из установленного
wheel только с Model/PyMuPDF, без Office/Pillow/fontTools/NumPy и других PDF engines.
Тест проходит два JSON/PDF-цикла с теми же pixel samples и всем текстом;
gate добавлен в локальный CI. [Доказательства и границы](pdf-cell-images-evidence.json).

## PDF: общий outline и нативные закладки

`tests/writers/test_pdf_outline.py` создаёт собственный PDF с nested entries,
page/URI/unknown destinations, точками, zoom и bold. Два PDF → JSON → PDF цикла
сравнивают исходную иерархию, номера страниц и destination points для 0/90/180/270
градусов, с crop и без него. Исходник и модель не меняются. Body paragraph anchor
проверяется на реально следующей странице; удаление не оставляет bookmarks.
Прежний JSON мигрирует один раз, сохраняет native raw данные и не восстанавливает
явно удалённый outline. Минимальный установленный pdf-rich профиль проверяет
настоящие закладки без дополнительных движков.

## PDF: отдельные MediaBox/CropBox

`tests/writers/test_pdf_page_geometry.py` создаёт собственный растровый документ
с нулевым, положительным и отрицательным native MediaBox origin, crop и всеми
четырьмя поворотами. Два PDF → JSON → PDF цикла сравнивают MediaBox, CropBox,
viewport rect, rotation и все RGB bytes; источник и модель не меняются.
Typed crop/rotation edits сравниваются с независимо изменённым native PDF.
Удалённая декларация не восстанавливает старые области/поворот. Layout links
сохраняют native rectangles и internal destinations при переносе; unknown null
outline points остаются unknown вместо NaN или произвольной точки backend-а.
Минимальный installed pdf-rich профиль проверяет общий тип и реальные crop cycles.

## PDF → DOCX: обрезка, Form XObject и группы

`tests/writers/test_pdf_docx_graphics.py` создаёт независимые PDF с вложенными
Form, разными обрезками общего ресурса, поворотами страницы/формы, отражением,
кубическими контурами, even-odd отверстием и прозрачными пересечениями внутри
нейтральной isolated/nonisolated группы. Проверяются исходные RGBA bytes,
границы scope, два DOCX/JSON цикла и неизменность входной Model. Растр остаётся
исходным PNG внутри SVG; векторная обрезка не получает растрового представления.

Негативные примеры: knockout, nonseparable blend, пересекающая текст
обрезка, stencil, preblended `/Matte`, повреждённые ссылки/команды/bounds/alpha
и лимит вложенности. Текст внутри полностью содержащего его clip Form остаётся
редактируемым; внешний текст не наследует clip формы.
Отказ сохраняет прежний файл; source PDF удерживается при неизвестной композиции.
Нативный PDF writer продолжает отклонять неподдержанный не-прямоугольный clip.

Сравнение с исходными PDF выполняется в Microsoft Word 16.0, build 16.0.17932,
с независимым Poppler 96 dpi. Девять примеров частного проектора включают растр/вектор,
отверстие, reflected Form и обе нейтральные группы. Два нативных DOCX/JSON цикла
дают попиксельно одинаковые страницы Word. Это проверка конечного профиля,
а не утверждение о попиксельном равенстве разных движков PDF и Word.
Границы кубических контуров отличаются от заданного оригинала до 0,041 pt.
Проверка нативного изменения crop/position использует сохранение встроенного
шрифта в Word: обе полные страницы двух циклов совпадают с нативно изменённым
оригиналом. Удаление программы шрифта проверяется как отдельное ограничение.

![Оригинальные PDF слева и Word справа: обрезка, отверстия, формы и группы](../assets/pdf-docx-clips.png)

Это визуальная приёмка проектора. Строгий маршрут дополнительно требует сохранения
нативной структуры групп: одинаковые картинки без независимо редактируемой группы,
её clip и isolation получают LOSS и отказ. Нейтральная группа сама по себе
не означает отсутствия этих ограничений.

## Общая прозрачность и typed scopes

`tests/writers/test_pdf_group_scopes.py` проверяет официальный scene API SDK:
исходный полный Unicode, clips/occurrences, JSON, правку opacity, удаление
group/clip/scene без возврата legacy, порядок children, лимиты и атомарный отказ.
48 сочетаний двенадцати separable режимов, isolated/nonisolated и двух alpha фона
проверяют цвета пяти областей независимых PDF, созданных PDF-операторами.
MuPDF сравнивает исходный PDF с аналитической SVG-проекцией с допуском 3/255.
Дополнительная проверка всех 48 исходников Poppler даёт максимум 2/255.
Проверяется вложенная общая opacity; SVG не содержит filters, image и group opacity.
Отдельные оригиналы отличают технологический запас `bboxlog` от реального
контура глифа: clip внутри запаса допускается, пересечение контура меньше чем
на 1 pt отказывает. Используются измерения нативного glyph API, без вычитания
предполагаемого запаса. Повторный PDF/JSON экспорт AcroForm остаётся отдельным
прежним профилем и проходит без ложной mixed scope сцены.

Word 16.0: opacity .5, Multiply, Screen, nonisolated фон и снятый typed clip
проверены относительно исходных PDF через Poppler 96 dpi. Цвета внутренних
областей отличаются до 2/255, два нативных DOCX/JSON цикла дают попиксельно
одинаковые страницы. Печатные PDF Word не содержат растровых image XObjects.
Внешний текст и строка после удаления clip остаются редактируемыми.
Исходные typed группы сохраняются в Model; DOCX-проекция — один векторный SVG,
без нативного управления отдельными детьми/композицией группы. Обычный экспорт
и строгий конвертер помечают потерю структуры как LOSS и отказывают до публикации.
Проверки Word/SVG относятся к экспериментальному частному представлению,
а не к принятому маршруту без потерь.

Нативная `wpg:wgp` с двумя отдельными фигурами также проверена в Word:
`a:effectDag/a:alphaModFix amt="50000"` применяет общую opacity, но печатный
PDF содержит image XObject вместо векторной группы. Вариант с вложенным
`a:cont` даёт тот же результат; контрольная группа без эффекта остаётся векторной.
Наличие эффекта в схеме DrawingML не подтверждает векторный вывод Word.
Такое представление не принимается как маршрут без потерь качества.

Knockout не принят: при красном opaque и синем alpha=.5 прямоугольниках,
`/I true /K true /CS /DeviceRGB` MuPDF даёт RGB (116,109,203) в пересечении,
Poppler — (127,0,128), PDFium — (128,0,127). Совпадение с одним движком
недостаточно. Смысл knockout сохраняется в SDK/JSON, DOCX отказывает.
Частичная обрезка глифов также отказывает: Word игнорирует правую границу
`horzOverflow="clip"`; поворот текстового блока может приводить к растеризации.
Скрытая часть текста не удаляется и не появляется в успешном экспорте без
явного снятия typed clip. Эти ограничения остаются в OF17.

## Редактируемые группы и цветовое пространство

`tests/writers/test_docx_vector_groups.py` использует официальный Model 0.16.0,
конечный WPC/WPG профиль и независимый XML из документа, созданного непосредственно
в Microsoft Word. `tests/corpus/native/word-canvas-group.xml` содержит только
собственные геометрию и заливки; личные метаданные и пакет шаблона не включены.
Проверяются фон полотна, имена и порядок детей, собственная alpha, правка цвета,
перенос, удаление и два JSON/DOCX цикла. Активная сцена не подменяется старым SVG;
общая opacity/ICC/unknown, непроверенные эффекты/расширения и глубокая вложенность
отклоняются. PDF-тест допускает нативную группу только после явных typed правок,
снимающих исходные clip/общую opacity, и не выдаёт их за сохранение исходного PDF.

В Word 16.0 полотно имеет Shape.Type=20; группа доступна отдельно как
CanvasItems.Item(...).Type=6 с двумя GroupItems. Контроль `wpg:grpSp` сохранял
XML, но не отдельную промежуточную группу в интерфейсе. Проверены: собственная
сцена адаптера, независимый Word-оригинал и документ после нативного переноса
группы/ребёнка и перекрашивания ребёнка. Два цикла каждого из трёх документов
дали попиксельно одинаковые страницы Word при независимом рендере MuPDF и
Poppler 144 dpi. Печатные PDF не содержат image XObjects. Внутренние цвета
контрольных областей совпали с независимыми PDF-примитивами. Эти результаты
подтверждают только описанный профиль, а не общую прозрачность или Form clipping.
Нативную структуру, геометрию и заливки сравнивает
`tools/docx_group_acceptance.ps1 -FixtureRoot .opendoc-formats/native-groups`:
`source.docx`, `cycle-0.docx`, `cycle-1.docx` создаются из `scene_document()`
и двух публичных JSON/DOCX циклов. Параметр `-Names` позволяет проверить
независимый Word-оригинал или нативно изменённый документ с его циклами.
Скрипт открывает только собственные fixtures, не меняет их и печатает PDF;
отсутствие image XObjects и сравнение страниц проверяются отдельным PDF renderer.

Штатная `Group.Fill.Transparency=.5` также не заменяет общий эффект: Word создаёт
групповую заливку `a:solidFill` и переводит детей на `a:grpFill`, теряя их
разные цвета/собственную alpha. В контрольном пересечении получается RGB
(57,54,38), а не исходная композиция. Векторный вывод такого варианта не
означает сохранения качества; этот обход в writer не применяется.

`tests/writers/test_pdf_group_color_space.py` проверяет закрытый C-GRAPHICS-02:
официальную декларацию, два JSON-цикла, правку/удаление и unknown/Gray/CMYK.
Старое нативное свидетельство RGB не восстанавливает удалённую декларацию.
Унаследованное PDF-пространство разрешает Formats в явно объявленном RGB device
профиле; отсутствующая декларация старого документа остаётся неизвестной.

## Нативные списки TeX

`tests/writers/test_latex_lists.py` проверяет C-LIST-02 Model 0.17.0:
продолжения без нового номера, пустой родитель, вложенные списки, начало и
перезапуск нумерации, выход из списка, правку и удаление официальной роли.
Два JSON/TeX цикла сохраняют Anchor, ListItem и текст; Office imports запрещены
в контрольном тесте. Несогласованные counters/metadata, custom labels и
непредставимое расположение связей приводят к атомарному отказу.

`tests/writers/test_latex_list_acceptance.py` независимо компилирует три собственных
оригинала и по два нативных цикла через `pdflatex -no-shell-escape`.
MuPDF сравнивает страницы попиксельно при 108 dpi и проверяет отсутствие image
XObjects. В набор входят продолжения, пустой родитель и пустой листовой пункт,
перезапуск счётчика и смешанная вложенность. Эта проверка включена в Linux CI
Python 3.12; TeX distribution не является runtime-зависимостью.
Она подтверждает только конечный профиль, а не произвольные macros, labels,
формулы, таблицы или компоновку. Другие экспортеры явно сообщают LOSS общей
структуры списка; quality gate может отклонить публикацию такого результата.

## Нативные формулы TeX

`tests/writers/test_latex_math.py` проверяет точные value/format/display/fallback,
text/formula порядок и paragraph boundaries, формулы внутри пунктов/продолжений
списка, отдельные Formula blocks, правку режима и выражения, удаление, два JSON/TeX цикла и запрет Office
imports. Неподдержанные команды/форматы/geometry, numbered environments,
непривязанные и повреждённые metadata, попытки file/shell/macro/`^^` синтаксиса
отклоняются до публикации. Fallback — inert metadata, не подмена выражения.

`tests/writers/test_latex_math_acceptance.py` компилирует четыре собственных оригинала
и по два JSON/TeX цикла через pdflatex с отключённым shell escape. Дроби, корни,
суммы/интегралы, матрицы, cases/aligned, оба display delimiter и формулы в списках
дают попиксельно одинаковые страницы MuPDF при 108 dpi; image XObjects отсутствуют.
Проверка работает в том же Linux CI профиле, что и списки; TeX distribution
не включается в пакет. MathML/OMML, FormulaTree, numbered equation/align,
произвольные macros/Unicode и moving arguments вне описанного профиля заголовков
не входят в принятую проекцию.

`tests/writers/test_latex_heading_acceptance.py` проверяет inline math в Heading 1–5,
numbered/starred команды, дроби/корни/греческие символы и матрицу. Для каждого
original и двух JSON/TeX циклов отдельная обёртка добавляет оглавление и выполняет
три прохода pdflatex, проверяя moving arguments через auxiliary files.
Страницы MuPDF при 108 dpi совпадают попиксельно без image XObjects.
Структурные тесты подтверждают правку/удаление Heading и значения формулы,
сохранение fallback и отказ для display в заголовке без Office imports.

## Предупреждения OCR в PDF

`tests/readers/test_pdf_model_ocr_diagnostics.py` использует собственный двухстраничный
PDF и внедрённые провайдеры. Structure/scan сохраняют warnings результата с блоками
и без блоков в metadata, публичном ImportResult и JSON; исходные bytes неизменны.
Отдельно проверены отсутствующий/недоступный backend, исключение и пустой список
page results в богатом и текстовом маршрутах. Fast не инициализирует OCR и не
добавляет ложное предупреждение о его отсутствии. Эти проверки подтверждают
типизированные коды отсутствия/сбоя/пустого ответа OCR и provider warnings,
reason, OPAQUE-состояние и provenance страниц. Одинаковые сообщения разных страниц
остаются разными occurrences; лишнему OCR page result не приписывается выдуманная
страница источника. JSON сохраняет ledger и коды; явно связанный legacy warning
не дублируется в публичном отчёте. Проверена отмена после первой записи ledger.
Превышение лимита OCR провайдера в structure/scan не превращается в best-effort
warning: прямые rich/text readers сохраняют исходный тип исключения, общий
ArtifactLimitError в реестре даёт `import.document-limit` с адресом источника.
Полнота распознавания и типизация всех остальных PDF-потерь этим не объявляются.

## Отмена нативного импорта PDF

`tests/readers/test_pdf_resource_diagnostics.py` использует собственные страницы
с повторными raster xref и вектором, созданные только PyMuPDF. Контролируемое
отсутствие bytes даёт четыре разных LOST occurrences; сбой анализа drawings
даёт OPAQUE с адресом страницы. Текст ячейки сохраняется при неподтверждённой
геометрии с адресом Model и native row/column. Проверены JSON, общий порядок
warnings с OCR, неизменность source bytes и повторное обычное чтение. Лимиты
и отмена в vector backend не становятся best-effort предупреждением; реконструкция
ячеек и связывание warning records проверяют отмену до следующего элемента.
Строгий DOCX-экспорт известной потери изображения отказывает до публикации и
сохраняет прежнее назначение.

`tests/readers/test_pdf_table_diagnostics.py` использует собственный двухстраничный
PDF и контролируемые отказы нативного поиска таблиц. Обе стратегии имеют отдельные
записи с адресом страницы, причиной, provenance и связью с исходным warning.
Геометрический enrichment, rich import и JSON сохраняют эти записи. Проверены
общий ledger с OCR без смещения индексов, типизированные лимиты без попытки
следующей стратегии и отмена после backend до обхода найденных таблиц.
Исходные bytes неизменны, повторное обычное чтение успешно; состояние OPAQUE
не объявляет наличие или отсутствие исходных таблиц.

`tests/readers/test_pdf_import_cancellation.py` проверяет сигнал через геометрию,
растр/вектор, enrichment, шрифты, paint, interactions и scopes. Отмена после native
text extraction не начинает tables/следующую страницу; между table strategies
второй backend call не запускается. Отмена при удалении appearances в несохраняемой
копии оставляет исходные notes и bytes неизменными. Источник повторно импортируется
после отмены, частичная Model не выдаётся.

OCR cancellation не превращается в warning, включая отдельное исключение провайдера.
Проверены direct reader, текстовый scenario, завершение history stage и поздняя
отмена при Model validation. Публичный реестр возвращает import.cancelled;
прямой reader — OperationCancelledError. Неактивный callback даёт полный
идентичный JSON собственной модели с текстом, растром, вектором и annotation.
Контрольные точки кооперативные: одиночный сторонний вызов не прерывается.

## Отмена нативного импорта HTML и EPUB

`tests/readers/test_web_import_cancellation.py` использует собственные HTML
и трёхглавный EPUB с CSS, MathML и таблицей. Проверены отмена после разбора
первой главы и между блоками, остановка чтения ZIP перед следующей главой,
локальных изображений перед следующим ресурсом и CSS перед обработкой правил.
Длинный сканер CSS EPUB реагирует на сигнал внутри цикла. Поздний сигнал
при привязке диагностики также отбрасывает модель.

Реестр возвращает `import.cancelled` без частичного документа; прямые readers
и package reader выбрасывают `OperationCancelledError`. Архив повторно
открывается, исходные bytes не меняются, повторный импорт успешен.
Неактивный callback сохраняет полный JSON обоих форматов. Проверки не
доказывают прерываемость одиночного стороннего вызова или жёсткий бюджет памяти.

## Отмена нативного импорта DOCX и PPTX

`tests/readers/test_office_import_cancellation.py` использует собственные DOCX
со стилями, runs, вложенной/объединённой таблицей, изображениями и колонтитулами
и трёхслайдный PPTX с группами, таблицей, изображениями, диаграммой и notes.
Контрольные события после первого обработанного объекта проверяют остановку
между runs, ячейками, стилями, ресурсами, фигурами и chart caches. Отмена после
открытия backend не начинает построение модели; поздняя отмена при диагностике
не выдаёт частичный документ. Отмена при чтении темы не заменяется default palette.

Реестр возвращает `import.cancelled`; богатые и текстовые direct readers —
`OperationCancelledError`. ZIP проходит проверку целостности, source bytes
сохраняются, повторный импорт успешен. Неактивный callback даёт идентичный полный
JSON, включая оформление, ресурсы, package и diagnostics. Два параллельных импорта
с независимыми сигналами и вложенный scope с исключением проверяют восстановление
контекста Formats. Никакие runtime-поля в Model не добавляются.
`tools/package_smoke.py --all-formats` дополнительно проверяет отмену DOCX/PPTX
и повторное чтение установленного wheel вне checkout.

`tests/readers/test_docx_heading_cancellation.py` проверяет отмену внутри
наследования нативного стиля заголовка: следующий предок не разрешается,
исходный DOCX и выходной узел не меняются, контекст восстанавливается.

## Отмена нативного экспорта DOCX и PPTX

Потоковый профиль PDF-модели дополнительно принят на собственном crop 3×3 → 2×2,
двух DOCX/JSON циклах и нативной правке Microsoft Word. Проверяются точные
ячейки, ширины и границы, source locations шрифтов, карта исходных линий,
неизменность модели и назначения при отказе/отмене. Установленный wheel
проверяет JSON → flow без PDF-движков; [границы и результаты](pdf-word-flow-contract.md#приёмка).

`tests/writers/test_docx_flow_borders.py` проверяет разные цвета/толщины общих
и поклеточных границ, обычные и merged tables, crops и два JSON/DOCX-цикла.
Подмена записанных XML-границ, в том числе continuation, отклоняется до замены
назначения. Переход стиля внутри одной логической стороны не усредняется;
квота сравнений и отмена проверяются отдельно.
`tools/docx_flow_cell_word_acceptance.ps1` подтверждает все четыре стороны каждой
логической ячейки в Word, ширины, нативную правку и экспорт PDF для двух случаев.
Шесть PDF стабильны внутри MuPDF/Poppler при 108 dpi; изображения просмотрены.
`tools/docx_flow_smoke.py --minimal --cell-borders` проходит из установленного
wheel без PDF/fontTools/Pillow/NumPy; gate включён в локальные изменения CI.
[План, наблюдения Word и hashes](docx-flow-cell-borders-evidence.json).

`tests/writers/test_docx_source_grid.py` проверяет source-grid snapshot и скрытую
закладку таблицы, нормализацию 3→2 столбца с полностью изменённым текстом,
два JSON/DOCX-цикла и отсутствие накопленных custom XML. Изменённые границы,
удалённая ячейка, missing/duplicate/outside/reversed bookmark, отсутствующая или
неоднозначная OPC-связь, неизвестная версия и повреждённые spans не восстанавливают
исходную сетку. Подмена snapshot, relationship или bookmark до публикации сохраняет
прежний файл и Model. XML byte budget/DTD и unknown profile проверяются отдельно.
Реальный Word 16.0 нормализует таблицу и заменяет текст; импорт восстанавливает
исходную identity по binding, затем проходит ещё два JSON/DOCX-цикла. Три Word PDF
стабильны внутри MuPDF и Poppler при 108 dpi. Установленный минимальный DOCX gate
`tools/docx_flow_merge_smoke.py --crop top` проверяет snapshot без PDF/fontTools/Pillow.
[Доказательства и границы](docx-source-grid-evidence.json).

`tests/writers/test_office_export_cancellation.py` использует собственные Office
источники из проверки импорта. Сигнал после первого native объекта останавливает
запись текста, ячеек, изображений, групп, данных диаграмм, embedding и package graph.
Проверены прямые writers и публичный реестр; отмена после сохранения ZIP и после
копирования `.partial` оставляет прежнее назначение целым, промежуточные файлы
удаляются. Повторный экспорт после отмены успешен, исходный JSON не изменяется.

Неактивный callback сохраняет полный JSON повторного импорта по сравнению с
обычным экспортом в тот же путь. Сигнал после успешного прямого commit возвращает
успешный отчёт, не заявляя rollback опубликованных bytes. При работе через реестр
публикация дополнительно отделена staging и его последними проверками.
Установленный wheel проверяется также через `tools/package_smoke.py --all-formats`:
отмена внутри DOCX/PPTX writers сохраняет хеш готового файла назначения.
`tests/support/test_ooxml_package.py` дополнительно проверяет отмену после
создания первой части OOXML в DOCX: следующая часть не создаётся,
исходный граф и связи корня неизменны; повторное восстановление успешно.

`tests/writers/test_office_nested_cancellation.py` проверяет сигнал внутри одного
объекта: сетки DOCX, физических продолжений объединённой ячейки, векторной сцены,
сбора одной группы PPTX и одного набора серий комбинированной диаграммы.
Прямые writers и реестр останавливаются до следующего элемента; исходный JSON
и прежний файл назначения неизменны, `.partial` удалён, повторный экспорт читается.
Обычные регрессии таблиц, заголовков, групп и комбинированных диаграмм проверяют
сохранение структуры без активного сигнала.

## Отмена HTML, EPUB и TeX export

`tests/writers/test_web_tex_export_cancellation.py` использует собственную
модель с тремя секциями, таблицами, MathML и SVG, а также нативные TeX списки
с формулами и отдельный табличный DOCX-мост. Прямые writers и реестр проверяются
с сигналом после первого объекта: HTML абзаца/изображения и verification,
XHTML start tag/image, EPUB XML, TeX символа/токенизации/маркера списка
и bridge paragraph. Следующий такой объект не обрабатывается.

Проверены отмена после `.partial`, удаление временного файла, сохранение прежнего
назначения и JSON модели, повторный экспорт и восстановление контекста. Сигнал
после успешного прямого commit не даёт ложный отказ. При неактивном callback
HTML/TeX совпадают побайтно; содержимое каждого ZIP member EPUB совпадает при
фиксированном времени OPF metadata. ZIP timestamps не выдаются за format semantics.

## Отмена подготовки PDF → DOCX

`tests/writers/test_pdf_docx_preparation_cancellation.py` использует собственные
двухстраничные PDF: текстовые колонки, merged table, repeated image Form, curved
clip, neutral/opacity groups и многокомандный вектор. Без сигнала проверяется
полный JSON частного Word view и исходной модели. Отмена после первого объекта
проверена для прямой подготовки, direct writer и реестра: lines/baselines,
tables/borders, image transform, clip commands, SVG, native groups и compositor.
Для native group используется принятый профиль с явной правкой typed clip;
исходные Form clips не удаляются неявно. Сценарий общей opacity проверяет
подготовку и отмену, не отменяя последующий отказ quality gate.

Проверены source bytes/JSON, прежнее назначение, отсутствие `.partial`, повторная
подготовка и восстановление контекста. Отмена font provider не превращается в
warning. Отмена между командами вектора сохраняет тип ошибки и закрывает native
document. Поздний сигнал после Model validation отбрасывает подготовленное
представление. Converter наследует import signal при отсутствии export options.
`tools/pdf_profile_smoke.py pdf` проверяет ту же подготовку и отмену в установленном
минимальном PDF-профиле без DOCX/Pillow/lxml и альтернативных PDF-движков.

## Отмена нативного TXT

`tests/test_txt_cancellation.py` проверяет отказ между создаваемыми абзацами,
после нормализации, внутри вложенной таблицы, после проверки кодирования
и после записи `.partial`. Проверены public/direct API, восстановление контекста,
повторный запуск, неизменность source bytes/Model и прежнего назначения.
Неактивный callback сохраняет полный JSON и исходные UTF-8/UTF-16/CP1251 bytes
с BOM и смешанными переводами строк; кодировочные ошибки не заменяются отменой.

## Нативные текстовые индексы TeX

`tests/writers/test_latex_text_scripts.py` проверяет общие superscript/subscript
в тексте, списках и заголовках, два JSON/TeX цикла, изменение/снятие роли,
разбиение run внутри одного scope и запрет Office imports. Вложенные индексы,
underline ordering, пустые/многоабзацные аргументы и nested emphasis имеют located
opaque records; unsupported styles/objects и некорректные scope hints отказывают
до публикации и сохраняют назначение. Флаг из native hint не восстанавливает
снятый/изменённый общий стиль.

`tests/writers/test_latex_text_scripts_acceptance.py` компилирует пять собственных
оригиналов и по два JSON/TeX цикла. Каждый вариант проходит три pdflatex запуска
с оглавлением и `-no-shell-escape`; страницы MuPDF при 108 dpi совпадают попиксельно
без image XObjects. Проверены font declarations/normalfont внутри индексов,
соседние отдельные scopes и отличия italic correction между itshape и textit.
`tools/package_smoke.py` подтверждает маршрут установленного базового wheel
без Office и дополнительных зависимостей.
