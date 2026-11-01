# Препарирование документа

Совместимость проверяется по исходному файлу: контейнеру, частям, связям,
объектам и бинарным данным. Затем оцениваются общая модель и файл результата.
Цикл через собственный экспортёр используется дополнительно к независимому
оригиналу и проверке в приложении, которое открывает целевой формат.

## Порядок исследования совместимости

Отправная точка — независимый исходный документ с известным происхождением,
а не файл, созданный нашим экспортёром. Для воспроизводимости фиксируются SHA-256,
формат, выбранный профиль инспектора и его лимиты. Исходник остаётся неизменным.

1. Получить физический инвентарь и выгрузить исходные части. Исследовать связи,
   вложенные контейнеры, шрифты и медиа; неизвестные поля оставить явно неизвестными.
2. Открыть оригинал в целевом приложении и зафиксировать структуру, текст,
   геометрию и отображение исследуемых объектов.
3. Импортировать документ и для каждого исследуемого объекта проследить связь
   «исходный адрес → объект OpenDoc или сохранённый payload → адрес результата».
   Если связь не доказана, записать пробел покрытия; совпадения имени или номера
   объекта недостаточно.
4. Выполнить экспорт, повторное препарирование и сравнение с оригиналом.
   Отдельно оценить содержимое, упаковку, редактируемую структуру и отображение.
5. Внести одну адресную правку, повторить экспорт и проверку в целевом приложении.
   Проверить как изменённый объект, так и неизменённые соседние объекты и зависимости.

Для каждого дефекта в отчёте нужны исходный SHA-256 и локатор, ожидаемое и
фактическое поведение, способ воспроизведения и результат нативной проверки.
Сохранение исходного payload подтверждает сохранность bytes; редактируемость,
семантика и отображение требуют своих проверок. Текущий `inventory.json` содержит
физические наблюдения; автоматическая полная карта соответствия с OpenDoc
остаётся [задачей C-MAP-01](../development/todo.md).

Formats отвечает за разбор формата, исходные адреса, измерения и доказательства
совместимости. Общие представления документа и их проверка принадлежат OpenDoc.
Если для исследованного объекта общего представления недостаточно, требуется
[явный контракт Model](../development/opendoc-proposals.md) с минимальным примером
и критериями приёмки.

## Снимок внутреннего устройства

```python
from opendoc_formats.anatomy import inspect_binary, compare_snapshots

original = inspect_binary("original.docx", capture=True)
result = inspect_binary("result.docx")
changes = compare_snapshots(original, result)
```

| Профиль | Что фиксируется |
| --- | --- |
| ZIP, включая OOXML и EPUB | Имя и смещение локального заголовка, его исходные 30 байт в hex, сжатие, flags, CRC, ZIP metadata, SHA-256 распакованной части и локального заголовка со сжатым payload |
| XML-часть | QName с URI namespace, позиция узла, byte offsets событий, атрибуты, SHA-256 собственного текста и его длина; неизвестные namespaces сохраняются |
| Связи OOXML | Исходные XML-узлы `.rels`, в том числе Id, Type, Target, TargetMode; внешние адреса не загружаются |
| Неизвестная бинарная часть | Исходные распакованные bytes, размер и SHA-256; вложения и макросы не запускаются |
| PDF | Активные объекты через backend либо физические xref-секции и записи raw/Flate streams собственным разбором |
| CFBF/OLE container | Исходные секторы, FAT/DIFAT/miniFAT, directory objects, логические потоки и их byte ranges; содержимое OLE не активируется |
| TTF/OTF sfnt | Исходная программа целиком, directory records, смещения/размеры таблиц, объявленные checksums и SHA-256 payload; по `sfnt_checksums=True` — проверка сумм |

`capture=True` возвращает payload в памяти; обычный снимок хранит инвентарь.
`BinarySnapshot.to_dict()` — диагностический формат Formats, отдельный от JSON
документа OpenDoc. Пакет общей модели и её codec не меняются.
ZIP/XML, CFBF, sfnt и исходная PDF-инспекция используют стандартную библиотеку Python.
Активные PDF-объекты по умолчанию читаются через профиль `pdf` с его
[лицензионными условиями](dependencies.md).

## Выгрузка частей и сравнение

```sh
uv run python -m tools.document_anatomy original.docx --output .opendoc-formats/anatomy --compare result.docx
```

Новый каталог содержит `inventory.json` и части `part-000000.xml` / `.bin`.
Их имена создаёт инструмент; имена из архива не становятся путями на диске.
В JSON остаётся связь с исходным именем части. Существующий каталог не заменяется.
Для PDF также сохраняются читаемые `.pdf-object.txt` со словарями объектов.

`content_changed` означает изменение содержимого по одному и тому же буквальному
адресу, `storage_changed` — изменение упаковки/метаданных, включая смещение.
Пересжатие ZIP может изменить wire bytes при неизменных payload.
Для PDF одинаковый xref номер **не доказывает** соответствие объектов двух файлов:
они могут перенумеровываться. Снимки не подтверждают C-MAP-01 или lossless;
`assessment_complete` сравнения остаётся false.

## Потоки CFBF/OLE

`inspect_binary("object.bin")` распознаёт CFBF по начальной сигнатуре; API и CLI
принимают явный `container="cfbf"` / `--container cfbf`. Поддержанный физический
профиль — little-endian версии 3 с секторами 512 байт и версии 4 с секторами
4096 байт, mini sectors 64 байта и cutoff 4096. Основа —
[MS-CFB header](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-cfb/05060311-bfce-4b12-874d-71fd4ce63aea)
и [mini FAT](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-cfb/c5d235f7-b73c-4ec5-bf8d-5c08306cd023).
Это инспекция контейнера, а не импорт семантики DOC/XLS/PPT или вложенной программы.

| Локатор | Содержимое |
| --- | --- |
| `cfbf:sector=-1` | Весь header sector, включая padding v4; `-1` — обозначение инспектора |
| `cfbf:sector=N` | Исходный физический сектор, offset, raw FAT allocation value и наблюдённая роль |
| `cfbf:directory=N` | Активная directory entry: имя, type, raw metadata/entry hex, логический payload и SHA-256 |

Имена не используются как файловые пути. Обычные и mini-потоки имеют
`details.allocation`, `chain` и `data_ranges`: исходные `(offset, length)` каждого
фрагмента в логическом порядке. Последний фрагмент ограничен объявленным размером;
padding остаётся в физическом секторе. Root entry описывает общий mini stream,
storage object имеет пустой payload. Неиспользуемые directory slots и неизвестные
байты остаются в физических секторах. Сектор без известного владельца получает
роль `free` при FREESECT или `unclaimed` в остальных случаях; последнее не означает
доказанную недостижимость в полностью проверенной storage hierarchy.

При `capture=True` конкатенация всех `cfbf-physical-sector` payload в исходном
порядке восстанавливает bytes входа, включая свободные области. Payload логических
потоков хранится дополнительно. Старый v3 high DWORD размера сохраняется в
`stream_size_raw`, но при чтении используется low DWORD: это совместимость,
предписанная [MS-CFB directory entries](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-cfb/b37413bb-f3ef-4adc-b18e-29bddd62c26e).

FAT/DIFAT/miniFAT, directory stream и data chains проверяются на границы,
циклы, пересечения владения, контрольные markers и согласованность размера/числа
секторов. Ошибка не возвращает частичный снимок. Неподдержанный header profile
даёт `UnsupportedDocumentError`; повреждённая цепочка или имя — `InvalidDocumentError`.
`directory_tree_assessed=false` и `assessment_complete=false`: red-black storage
tree, правила сравнения имён, все reserved fields, семантика OLE и соответствие
всей спецификации этой проверкой не подтверждаются. CLSID и времена — исходные
значения; обработчик по CLSID не создаётся. Ремонт исходника не выполняется.

Указатели directory entries проверяются отдельно от правил сортировки имён и цветов.
`directory_links_assessed=true` означает завершённый обход конечного профиля связей;
`directory_links_valid` показывает отсутствие его замечаний. Профиль основан на
[полях MS-CFB directory entry](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-cfb/60fe8611-66c3-496b-b70d-a504c94c9ace).
В `directory_link_findings` каждое замечание содержит `code`, исходный `location`
вида `cfbf:directory=N/child` и `target` (null для недостигнутой записи):

| Код | Наблюдение |
| --- | --- |
| `root-sibling`, `stream-child`, `root-target` | Связь недопустима для роли записи |
| `inactive-target`, `out-of-range-target` | Цель — пустой slot или адрес вне directory stream |
| `multiple-references` | На запись указывают несколько допустимых по роли связей |
| `cycle` | Обнаружен цикл, включая компоненты вне корневого хранилища |
| `unreached-entry` | Активная запись не достигнута от root по допустимым связям |

`directory_reached_entries` и `directory_unreached_entries` содержат индексы
в исходном порядке directory stream. Недопустимые по роли связи не создают
достижимость, но сохраняются буквально в metadata записи. Замечания не уничтожают
физический инвентарь: это исследование повреждённого контейнера, а не успешный
семантический импорт OLE. Обход всех компонентов выполняется без рекурсии,
с линейным числом посещений записей/связей, в рамках `max_items` и с отменой.
Отсутствие замечаний по указателям не подтверждает порядок имён, red-black правила,
интерпретацию потоков или полную корректность CFBF.

`max_items` ограничивает отдельно число сканируемых directory slots и общую сумму
физических секторов с активными directory objects. Числа доступны в details.
`max_part_bytes` ограничивает сектор и каждый логический поток. `max_total_bytes`
учитывает весь физический вход и логические потоки дополнительно, включая root
mini stream: одни bytes могут учитываться несколько раз. Это ограничивает объём
инвентаря и копирования. Сигнал отмены проверяется внутри allocation/directory/data
обходов; отдельное чтение или хеширование остаётся неделимым.

CFBF-байты из `BinaryItem.payload` внешнего ZIP можно передать в отдельный
`inspect_binary`. Автоматического обхода вложений и общего бюджета глубины между
вызовами пока нет; XML-флаг `parse_xml` не отключает разбор allocation tables CFBF.
Внешний файл и вложение не исполняются. Полная приёмка OLE-объекта в Word или
другом приложении остаётся отдельной задачей.

## Таблицы программ TTF/OTF

Самостоятельный `opendoc_formats.native.sfnt.inspect_sfnt` читает физический
каталог таблиц standalone sfnt с сигнатурой `00010000` или `OTTO` по
[описанию OpenType Table Directory](https://learn.microsoft.com/en-us/typography/opentype/spec/otff).
Он использует стандартную библиотеку, не загружает программу шрифта в движок
и не выполняет инструкции hinting.

```python
from opendoc_formats.native.sfnt import inspect_sfnt

font = inspect_sfnt("embedded.ttf", capture=True)
for table in font.tables:
    print(table.tag, table.offset, table.length, table.sha256)
```

Результат содержит SHA-256 всего входа, размер, исходный 12-byte header в hex и
таблицы в порядке directory records. Для каждой сохраняются адрес записи,
смещение/длина payload, объявленная checksum, SHA-256 и, при `capture=True`,
точные bytes. Неизвестные печатные ASCII tags сохраняются. `variation_tables`
перечисляет обнаруженные `fvar/gvar/avar/CFF2/HVAR/VVAR/MVAR`; отсутствие этих tags
не доказывает полноту интерпретации всех расширений шрифта.

Проверяются границы каталога и таблиц, уникальность/допустимость tags и выравнивание
начал таблиц на четыре bytes. Повреждённый диапазон даёт `InvalidDocumentError`;
невыровненная таблица, TTC без выбора face, WOFF/WOFF2 и legacy signatures — явный
`UnsupportedDocumentError` конечного профиля. Непересечение диапазонов, сортировка
tags, padding, checksums и внутренние subtables этим API не подтверждаются.
Объявленная checksum не выдаётся за проверенную.

`SfntLimits` ограничивает размер входа, число таблиц, размер отдельной таблицы
и сумму их объявленных длин; пересекающиеся диапазоны учитываются повторно.
Отмена проверяется между таблицами и перед возвратом; одно чтение/хеширование
неделимо. Ошибка не возвращает частичного инвентаря и не изменяет исходник.
`assessment_complete=false`: этот инвентарь не определяет cmap/shaping, права
embedding, валидность glyph IDs, конкретный variable instance или лицензии шрифта.
Для полного сохранения программы нужны исходные bytes целиком, включая padding
и неизвестные области; набора извлечённых таблиц недостаточно.

Для TTC 1.0/2.0 face выбирается явно:

```python
font = inspect_sfnt("collection.ttc", face_index=1, capture=True)
print(font.face_index, font.directory_offset, font.source_sha256)
```

SHA-256 и размер относятся ко всей исходной коллекции; `directory_offset`,
адреса directory records и таблиц абсолютные. Header относится к выбранному face;
shared tables могут находиться перед его directory и не копируются в новую программу.
`SfntLimits.max_faces` ограничивает число объявленных faces (по умолчанию 256);
остальные table quotas действуют на выбранный face. Проверяются TTC header/version,
массив указателей, диапазон выбранного каталога и его таблиц, декларация DSIG v2.
Подпись не удостоверяется; полный аудит всех faces, межтабличных overlaps и общего
графа коллекции остаётся отдельной задачей. Общий Anatomy распознаёт TTC по
сигнатуре, но требует явного выбора face через `sfnt_face_index`:

```python
snapshot = inspect_binary("collection.ttc", sfnt_face_index=1, capture=True)
```

В CLI используется тот же выбор для исходника и сравниваемого результата:

```sh
uv run python -m tools.document_anatomy collection.ttc --sfnt-face-index 1 --output .opendoc-formats/ttc-inspection
```

`sfnt:source` содержит всю исходную коллекцию, `sfnt:face=1:table=TAG` — таблицы
выбранного face. Общий бюджет учитывает original source и таблицы, а число
объявленных faces ограничивается оставшимся `max_items-1`; отдельного скрытого
лимита 256 в этом маршруте нет. `sfnt_checksums` сохраняет standalone смысл
и для TTC явно отклоняется. ZIP/TTC polyglot требует явного `container="sfnt"`.

Общий `inspect_binary("embedded.ttf", capture=True)` распознаёт standalone sfnt
по сигнатуре; API и CLI также принимают `container="sfnt"` / `--container sfnt`.
`sfnt:source` содержит исходную программу целиком, включая padding и неизвестные
области; `sfnt:table=TAG` — отдельный payload таблицы. В details таблицы сохраняются
`tag`, `offset`, `directory_offset` и `declared_checksum`; её `storage_sha256`
вычисляется по исходной 16-byte directory record. Поэтому изменение объявленной
checksum или смещения видно отдельно от изменения содержимого таблицы.

Отдельный `native.sfnt.inspect_sfnt_checksums` сопоставляет объявленную и
вычисленную сумму каждой таблицы и проверяет standalone `head.checkSumAdjustment`.
Он использует исходные bytes и не исправляет повреждения. Расчёт следует
[OpenType checksum](https://learn.microsoft.com/en-us/typography/opentype/spec/otff#calculating-checksums):
uint32 big-endian с нулевым дополнением последнего слова, при проверке `head`
поле adjustment считается нулевым. Сумма всего файла учитывает реальные padding
и trailing bytes; при отсутствии `head` проверка adjustment возвращает `None`.
Укороченное поле adjustment — явный отказ. Работают `SfntLimits` и проверки
отмены каждые 64 KiB. Данные и checksum остаются наблюдениями: совпадение не
доказывает корректность glyph programs, рендера, padding/overlaps или лицензии.
`assessment_complete` остаётся false. Generic Anatomy не запускает этот отдельный
аудит по умолчанию. Для общего API включается `inspect_binary("own.ttf", sfnt_checksums=True)`;
результат находится в `snapshot.to_dict()["details"]["checksums"]`, включая исходный SHA,
статусы таблиц и adjustment. Флаг допустим только для sfnt, чтобы запрос не был
молча проигнорирован для ZIP/PDF/CFBF. XML policy и `capture` от него не зависят.

```sh
uv run python -m tools.document_anatomy own.ttf --sfnt-checksums --output .opendoc-formats/font-audit
```

При `--compare` тот же аудит выполняется для обоих исходных снимков; различия
попадают в обычное сравнение metadata/storage/content. `--no-payloads` оставляет
только JSON с наблюдениями. Данные для аудита берутся из того же снимка bytes,
что и payload, повторного чтения изменяемого файла нет.

Для этого профиля `AnatomyLimits.max_items` учитывает исходную программу плюс
все таблицы. `max_part_bytes` ограничивает всю исходную программу и каждую таблицу;
`max_total_bytes` — размер программы плюс сумму длин таблиц, включая повторное
учитывание пересекающихся областей. Скрытого отдельного бюджета `SfntLimits`
в общем инспекторе нет: используются выбранные общие лимиты. `parse_xml=False`
не отключает бинарный разбор шрифта. Источник сохраняется в сгенерированный `.bin`,
исходные tags не становятся путями файлов. При нескольких распознанных контейнерах
профиль требуется выбрать явно. Шрифт, полученный из ZIP, можно передать инспектору
отдельно; автоматический вложенный обход с общим бюджетом глубины ещё не реализован.

### Структурный аудит каталога и padding

`native.sfnt.inspect_sfnt_structure` проверяет сортировку directory tags,
производные `searchRange`/`entrySelector`/`rangeShift`, допустимость пробелов
в tags, padding таблиц до четырёх bytes и пересечения ненулевых payload ranges.
Findings содержат code, абсолютный offset, tag и описание. При вложенных
пересечениях указывается один представитель пересекающегося диапазона для
каждой следующей таблицы; полный попарный граф не строится.
Исходные байты, объявления и checksums не исправляются. `assessment_complete=false`:
проверяется конечная структура, а glyph programs, рендер, подписи и лицензии
остаются за пределами отчёта. Неизвестный trailing payload сохраняется opaque.

```python
snapshot = inspect_binary("own.ttf", sfnt_structure=True, capture=True)
findings = snapshot.to_dict()["details"]["structure"]["findings"]
```

```sh
uv run python -m tools.document_anatomy own.ttf --sfnt-structure --output .opendoc-formats/structure
```

Для TTC применяется явно выбранный `sfnt_face_index` / `--sfnt-face-index`;
общие таблицы других faces не объявляются пересечениями выбранного face.
Прямой API ограничивает findings через `SfntLimits.max_findings` (4096 по умолчанию).
В Anatomy findings занимают оставшийся после source и tables бюджет `max_items`.
Превышение квоты или отмена не возвращают частичный отчёт. Сравнение CLI выполняет
тот же аудит с обеих сторон; `--no-payloads` оставляет JSON inventory.

Использующий этот инвентарь helper `fonts.sfnt_names.read_program_names`
разбирает [name version 0/1](https://learn.microsoft.com/en-us/typography/opentype/spec/name)
для выбора IDs 1/4/6/16 при встраивании шрифта. Это отдельная конечная интерпретация
строк, а не полная валидация всех name records и BCP 47. В version 1 проверяются
границы language-tag arrays, UTF-16 строк и ссылки language IDs >= 0x8000.
Теги не меняют прежний source-order/numeric-English выбор имени. Неизвестная
кодировка/version, необходимость восстановления UTF-16 или превышение
native-бюджета передаются прежнему optional reader в `font_program_names`.
Прямой `read_program_names` возвращает явный отказ вне профиля. Пустые family/full
не заменяются догадкой. Generic Anatomy по-прежнему сохраняет `name` как точные bytes.

Однобайтовые Macintosh name records читаются стандартными Python-кодеками:
Roman с языковыми вариантами Icelandic/Turkish/Croatian/Latin-2/Romanian,
а также отдельные Greek/Cyrillic/Latin-2/Turkish/Icelandic encoding IDs.
Старые ISO records поддерживают ASCII, UTF-16BE и Latin-1.
Идентификаторы платформ и языков описаны в
[OpenType name](https://learn.microsoft.com/en-us/typography/opentype/spec/name).
Выбор английской записи и порядок aliases остаются прежними; неизвестные
и многобайтовые Mac encodings сохраняют engine fallback.

`fonts.sfnt_cmap.read_unicode_coverage` разбирает выбранную Unicode subtable
[cmap 0/2/4/6/12/13](https://learn.microsoft.com/en-us/typography/opentype/spec/cmap).
Возвращается множество объявленных codepoints с ненулевым glyph ID. Сохраняется
прежний порядок выбора: `(3,10), (0,6), (0,4), (3,1), (0,3), (0,2), (0,1), (0,0)`;
в пределах пары используется первая исходная запись. Format 0 читает 256 byte IDs;
format 6 — BMP-массив uint16 IDs с точным размером, включая пустой массив
и отображение U+FFFF. Неканонические массивы остаются за пределами native-профиля.
Format 2 проверяет high-byte keys, single-/double-byte subheaders, общие glyph
arrays, delta modulo 65536 и адреса относительно исходных offset words.
Он читается только при выборе Unicode-записи; legacy-кодировка самостоятельно
в Unicode не преобразуется. Подробности — в [приёмке cmap 2](../development/font-cmap2-evidence.json).
Format 4 учитывает
`idDelta`, относительный `idRangeOffset` и нулевые элементы glyph array;
format 12 — последовательные IDs, format 13 — постоянный ID группы.
Терминальный segment U+FFFF в format 4, как и в прежнем reader, не добавляет покрытие.
Сторонние glyph names для этой операции не строятся.
`read_unicode_mapping` возвращает те же выбранные непустые mappings как независимый
словарь codepoint → numeric glyph ID. Он используется конечным GSUB reader;
объявленный ID не доказывает корректность glyph program или исходного shaping.

Границы subtable/arrays, адреса glyph array, terminal segment и диапазоны групп
проверяются до возврата. Пересекающиеся/неупорядоченные ranges и неизвестная
выбранная таблица дают явный отказ прямого API; resolver сохраняет engine fallback.
Из невыбранных legacy таблиц и format 14 читаются только заголовки и границы. Это не
разбор variation selectors. `max_codepoints` ограничивает суммарную работу по
объявленным ranges; checkpoints действуют и внутри range. Generic Anatomy
сохраняет исходный cmap целиком, не объявляя его семантически проверенным.

`native.sfnt.read_face_metrics` читает статические поля face из
[OS/2](https://learn.microsoft.com/en-us/typography/opentype/spec/os2), `head`, `maxp`
и [post](https://learn.microsoft.com/en-us/typography/opentype/spec/post).
В возвращаемом `SfntFaceMetrics` остаются исходные weight/width/units/average/fsType
и признак ненулевого italicAngle. Версии OS/2 0–5 проверяются по минимальному
размеру; post 1/2/3 — по профилю glyph-name storage. Отсутствующие поля, variable
таблицы и неподтверждённые версии дают явный отказ прямого API. Resolver сохраняет
прежний engine-путь для таких программ. Это проверка используемой metadata,
а не полная валидация шрифта, glyph programs или юридическое заключение о лицензии.

`native.fvar.inspect_fvar_table` принимает payload таблицы
[fvar](https://learn.microsoft.com/en-us/typography/opentype/otspec190/fvar),
возвращает SHA-256, размеры records, оси и named instances. Координаты хранятся
как исходные signed Fixed 16.16 integers, без округления. Name IDs остаются
неразрешёнными ссылками, имена и instance не угадываются. Проверяются версия,
смещения/размеры массивов, уникальность tags, min/default/max, reserved flags
и диапазоны instance coordinates. Неизвестные profiles дают явный отказ.
Настраиваемые границы — 8 MiB payload, 64 оси, 4096 instances и 262144 coordinates
по умолчанию; проверки отмены действуют и внутри coordinate records.

Resolver включает `default_variations=True` только для чтения базовых полей,
как прежде. Никакие named-instance координаты не применяются. Изменение координат,
MVAR/HVAR/gvar и поддержка CFF2 требуют отдельной приёмки. `FontReference.face_index`
в Model обозначает collection face и не используется как номер named instance;
для выбора координат через общую модель потребуется отдельный контракт Model.
Generic Anatomy сохраняет fvar payload; автоматического глубокого разбора fvar
в общем инвентаре пока нет.

## XML по OPC Content Types

При наличии `[Content_Types].xml` инспектор сначала читает ограниченный OPC manifest.
`Override` имеет приоритет над `Default`; расширения defaults сопоставляются без
учёта регистра. Объявленные `application/xml`, `text/xml` и типы с суффиксом `+xml`
разбираются как XML, включая части без расширения и UTF-16. Объявленный binary
остаётся opaque, даже если имя заканчивается на `.xml`.
В `item.details` доступны `content_type` и `xml_detection`: `opc-content-type`,
`opc-manifest`, `extension` либо null. Для необъявленных частей сохраняется
распознавание по `.xml`, `.rels`, `.xhtml`, `.svg`; остальные остаются bytes.

Manifest учитывается в общем XML-бюджете ровно один раз, независимо от его позиции
в ZIP. Конфликтующие declarations отвергаются. Это конечный разбор Content Types,
а не полная проверка OPC: неподтверждённые поля деклараций и URI-грамматика
ещё требуют общей приёмки.
Для EPUB действует отдельный локальный профиль OPF, описанный ниже.

DTD/entities выбранных XML-частей отвергаются до раскрытия; `--opaque-xml`
отключает также разбор manifest и определение Content Type. Повреждённые XML
в выбранном профиле и CRC распакованной части,
дубликаты и небезопасные имена отвергаются. `--no-payloads` оставляет инвентарь
и PDF-словари. XML comments/PI остаются в payload; список узлов представляет элементы.
`start_byte` и `end_event_byte` относятся к распакованным исходным XML bytes,
включая UTF-16. Второе поле — позиция события закрытия Expat: для обычного узла
это начало закрывающего тега, для self-closing — позиция после тега.
Они не объявляются готовым полным lexical span или картой соответствия Model.

## Физические связи OPC

При распознанном OPC manifest `BinarySnapshot.opc` содержит неизменяемый `OpcAudit`.
Для обычного ZIP, PDF или `parse_xml=False` это поле равно null. В `inventory.json`
оно сериализуется под ключом `opc`; отдельный `to_dict()` возвращает независимую копию.

```python
snapshot = inspect_binary("original.docx")
if snapshot.opc is not None:
    for finding in snapshot.opc.findings:
        print(finding.code, finding.location, finding.message)
```

Инспектор проверяет все физические relationship parts, включая недостижимые
компоненты и циклы. В записи остаются исходные атрибуты, адрес `.rels`/XML-узла,
владелец (`/` для пакета), разрешённая внутренняя цель и статус
`internal`/`external`/`rejected`. Внешняя цель сохраняется буквально и не загружается.
Fragment остаётся в исходном Target; проверяется существование части, а не объекта
внутри неё. Общий resolver также используется переносом DOCX-компонентов.

Findings показывают отсутствующего владельца или target, несовпадение Content Type,
дубликат Id, отсутствующие обязательные атрибуты, неизвестный TargetMode и markup,
неразобранный `.rels`, отсутствующую часть из Override. Тип корневого `_rels/.rels`
разрешается по default `rels`. Источник определения владельца и внутренних/внешних
связей — [описание OPC](https://learn.microsoft.com/en-us/previous-versions/windows/desktop/opc/open-packaging-conventions-overview);
relationship part не является допустимой целью
[связи на часть](https://learn.microsoft.com/en-us/dotnet/api/system.io.packaging.packagepart.createrelationship?view=netframework-4.8.1).

| Поле аудита | Значение |
| --- | --- |
| `reachable_parts` | Части, достигнутые из корневого `.rels` по распознанным внутренним рёбрам |
| `unreached_parts` | Физические data parts, не достигнутые в этом обходе |
| `reachability_complete` | Обход конечного профиля не обнаружил пробелов; это не проверка всей OPC/OOXML спецификации |
| `unreachable_parts` | `unreached_parts` только при полном обходе профиля; иначе пустой список |

При отсутствии корневых связей, повреждённой связи или неизвестном расширении
`reachability_complete=false`: недостигнутые части не объявляются доказанно
недостижимыми. Relationship parts и Content Types не считаются обычными data parts.
Циклы обходятся без рекурсии и не являются сами по себе потерей.

`Id` проверяется собственным Unicode NCName reader по XML 1.0 Fifth Edition,
включая supplementary-plane символы до U+EFFFF и combining characters после
первого символа. Unicode normalization, обрезка whitespace и исправление Id
не выполняются; разные последовательности codepoints остаются разными Id.
`Type` проверяется конечным ASCII URI-профилем: scheme, допустимые символы,
percent escapes, reg-name authority/userinfo/decimal port и один fragment delimiter.
IRI, IP-literal authorities и whitespace recovery остаются вне профиля;
finding не объявляет такие входы универсально некорректными OPC.
Проверка не обращается к URL и не использует сторонний URI/XML-schema engine.
Неподтверждённые значения дают `opc.relationship-id` / `opc.relationship-type`,
сохраняя `.rels`, исходные атрибуты и адрес узла. Эти связи не участвуют в
доказанной достижимости; `unreachable_parts` остаётся пустым при неполном аудите.
Полная XML Schema/OPC conformance и URI-нормализация этим не подтверждаются.
Внутренние OPC targets разбираются собственным локальным parser без общего
кэша `urllib.parse.urlsplit`. Resolver не удерживает строки целей в процессном кэше, кэш
других пользователей стандартной библиотеки не очищается. Сохранены прежние
результаты для fragments, пустого query delimiter, root-relative путей и
проверок обхода каталогов/encoded separators. Это замена механизма разбора,
а не расширение URI-профиля. [Проверки совместимости и кэша](../development/opc-reference-cache-evidence.json).
[XML Name productions](https://www.w3.org/TR/xml/#NT-NameStartChar),
[NCName](https://www.w3.org/TR/xml-names/#NT-NCName),
[OPC/.NET ID contract](https://source.dot.net/System.IO.Packaging/System/IO/Packaging/InternalRelationshipCollection.cs.html),
[приёмка лексического профиля](../development/opc-lexical-evidence.json).

Семантически неверная связь даёт finding, сохраняя физический инвентарь и payload.
Это режим препарирования, а не успешный импорт документа: строгие читатели не
смягчают проверку пакета. Unsafe ZIP names, CRC, запрещённые DTD, повреждённый XML,
квоты и отмена по-прежнему завершают inspection отказом. Бюджеты частей/XML также
ограничивают число обрабатываемых связей; контроль отмены действует и внутри обхода.
`compare_snapshots` показывает `opc_changed`, но `assessment_complete` остаётся false.
Нормализация URI за пределами конечного resolver, грамматика Id/Type и все правила
валидности деклараций не заявлены полной OPC-валидацией.

## XML-ресурсы EPUB по manifest

Если OPC Content Types отсутствует и `mimetype` содержит в точности
`application/epub+zip`, инспектор читает `META-INF/container.xml` и все объявленные
OPF rootfiles. Из каждого OPF manifest берутся `href` и `media-type`;
для локальных ресурсов определяется физическая часть ZIP.
Это использует структуру [EPUB container и package documents](https://www.w3.org/TR/epub-33/);
полная валидация EPUB и отображение книги этим разбором не подтверждаются.

XML определяется по media type, включая XHTML/SVG/NCX, нестандартные расширения
и файлы без расширения. Объявленный binary сохраняется opaque при имени `.xml`.
UTF-16 и XML byte offsets остаются исходными. В details доступны:

| Поле | Значение |
| --- | --- |
| `snapshot.details.epub_rootfiles` | Физические имена всех выбранных OPF в исходном порядке |
| `item.details.content_type` | Тип ресурса из OPF либо тип OPF из container.xml |
| `item.details.xml_detection` | `epub-container`, `epub-package` или `epub-media-type` |

Несколько OPF могут ссылаться на общий ресурс с одинаковым типом. Конфликт типов,
duplicate rootfile/item, отсутствующий manifest/control part или локальный ресурс
дают явный отказ. Управляющие XML и общий ресурс читаются и учитываются в XML-бюджете
один раз. Действуют `AnatomyLimits`, кооперативная отмена и прежний запрет DTD/entities.
Новые зависимости не нужны; EPUB href разрешается общей локальной функцией с reader.

`BinarySnapshot.epub` содержит неизменяемый `EpubAudit` со всеми выбранными
manifest item occurrences. Каждый `EpubManifestReference` сохраняет исходный
XML-адрес, имя OPF, id, href, media type и все атрибуты. `status=local` указывает
на найденную часть в `resolved_target`. Ссылка со scheme или network location
получает `status=external-unassessed`, а `resolved_target=null`: её цель не открывается.
Разные OPF сохраняют отдельные occurrences даже для одного внешнего адреса.

В `inventory.json` аудит находится в `epub`, `to_dict()` возвращает независимые
контейнеры. Без распознанного EPUB или при `parse_xml=False` поле равно null.
`compare_snapshots` сообщает `epub_changed`; `assessment_complete` остаётся false.
Сырые атрибуты и payload не меняются. XML-бюджет ограничивает также число и размер
записей, отмена действует внутри их обхода.

Аудит не подтверждает допустимость схемы URL, ресурса или media type в EPUB,
доступность цели и уникальность после полной URL-нормализации. В частности,
сохранённые `file:`, `data:` или `javascript:` остаются инертными непроверенными
строками. Это не разрешение EPUB-читателю использовать их; ограничения внешних
ресурсов и data URLs описаны в [EPUB 3.3](https://www.w3.org/TR/epub-33/).
Локальные пути разрешаются собственным `native.epub.local_path`, общим с нативным
EPUB-reader. UTF-8 percent escapes декодируются строго и один раз: `%252F` остаётся
буквальным `%2F` в имени части. Некорректные escapes/UTF-8, исходные и декодированные
управляющие символы, начальные/конечные неэкранированные пробелы дают адресный отказ
инспектора до чтения content parts. Значение href и исходный XML остаются прежними.
Query (включая пустой `?`) и закодированные разделители `%2F`/`%5C` находятся
вне конечного локального профиля и дают `UnsupportedDocumentError` в inspection;
нативный EPUB-reader отказывает с `ValueError`. Фрагмент не участвует в выборе ZIP-части
и не объявляется семантически проверенным. Полная WHATWG URL-нормализация и
допустимость внешних URL этим не подтверждаются.

Буквальный дубль внешнего href внутри manifest, отсутствующие обязательные поля
и URL, отвергнутый разбором, дают адресный `InvalidDocumentError`.

`xml:base`, удалённые rootfiles и manifest alias на container.xml остаются
вне конечного профиля и дают `UnsupportedDocumentError`. Сеть и файлы вне ZIP
не читаются; строгий EPUB reader не расширяет свой поддержанный профиль.
Источник можно сохранить через `parse_xml=False`/`--opaque-xml`,
отключив также разбор EPUB manifest. Неверный `mimetype` оставляет обычный ZIP-профиль
с распознаванием XML по расширениям. Проверка ZIP-позиции/сжатия mimetype, spine,
навигации и всех правил EPUB не заменяется этим инспектором; `snapshot.opc` для EPUB
остаётся null, а `assessment_complete` сравнения — false.

`AnatomyLimits` ограничивает вход, число частей, размер части и сумму payload,
коэффициент ZIP-сжатия, XML nodes/depth/names/characters. Одноимённые CLI-параметры
имеют вид `--max-part-bytes`, `--max-xml-nodes`. Отмена проверяется при обходе.
Открытие ZIP/PDF, отдельное чтение, хеширование и вызов PDF backend неделимы;
проверка размера результата native call не является жёсткой квотой памяти декодера.

В PDF-режиме по умолчанию словарь представляет активный объект после обработки backend, а не исходный
диапазон байтов файла. Исторические revisions, поколения и различие free/null
slots этим профилем не восстанавливаются. Закодированные потоки не декодируются.
`repaired=true` явно показывает вмешательство backend при открытии.

### Исходные PDF-секции и xref streams без движка

`inspect_binary(source, pdf_source=True, capture=True)` читает физические секции,
достижимые через завершающий `startxref`, ссылки `Prev` и hybrid `XRefStm`.
Classic xref сохраняет object number, generation, free/in-use, смещение либо номер
следующего свободного объекта и диапазон записи. `object_header_matches` проверяет
только буквальный заголовок: совпадение внутри строки или потока не доказывает
принадлежность объекта. Циклы и неоднозначные словари отвергаются без ремонта.

По умолчанию xref stream остаётся словарём: payload заканчивается на `>>`,
`kind=pdf-xref-stream-dictionary`, `stream_entries_decoded=false`.
Для ограниченного декодирования индекса добавьте `pdf_decode_xrefs=True`:

```python
from opendoc_formats.anatomy import inspect_binary

snapshot = inspect_binary('source.pdf', pdf_source=True, pdf_decode_xrefs=True, capture=True)
```

```powershell
uv run python -m tools.document_anatomy source.pdf --pdf-source --pdf-decode-xrefs --output .opendoc-formats/pdf-source
```

Поддержаны прямой `Length`, raw, одиночный `FlateDecode` без предиктора
(`Predictor=1`), с TIFF Predictor 2 либо PNG-предиктором (`Predictor=10..15`),
а также одиночные `RunLengthDecode`, `ASCIIHexDecode`, `ASCII85Decode` без параметров.
`W` допускает ширину каждого поля 0–8 байт и ненулевую сумму,
непересекающиеся диапазоны `Index` либо `[0 Size]`. Нулевые ширины получают
стандартные значения полей. Записи type 0/1 сохраняют generation и free-link/offset;
type 2 — `object_stream` и `object_stream_index` с generation 0.
Неизвестный тип остаётся `raw_fields` с `in_use=null`, без выдуманного адреса.
Правила записей описаны в [ISO 32000-1, 7.5.8](https://opensource.adobe.com/dc-acrobat-sdk-docs/pdfstandards/PDF32000_2008.pdf).

Декодированный индекс получает `kind=pdf-xref-stream`. Payload сохраняет исходные
bytes от заголовка объекта до `endobj`, включая закодированный поток.
`encoded_start/end` — физический диапазон потока; `decoded_start/end` у записей —
позиции внутри распакованного индекса, а не смещения исходного PDF.
`decoded_bytes`, `record_widths`, `index`, `filter` показывают принятый профиль.
Режим сравнения должен быть одинаковым для двух файлов.

PNG None/Sub/Up/Average/Paeth выбираются по тегу каждой строки, независимо от
конкретного значения словарного Predictor 10–15. Поддержаны положительные прямые
`Colors`/`Columns` и `BitsPerComponent=1/2/4/8/16`; строка округляется до целого
байта и должна делить размер индекса без остатка. Значения по умолчанию — 1/1/8.
Восстановление выполняется в том же буфере; упакованные компоненты, padding bits
и многобайтный byte stride сохраняются без обращения к Pillow или PDF-движку.
Правила строк — в [ISO 32000-1, 7.4.4.4](https://opensource.adobe.com/dc-acrobat-sdk-docs/pdfstandards/PDF32000_2008.pdf#page=36).

TIFF Predictor 2 восстанавливает каждую компоненту по предыдущей компоненте
того же цвета в строке с учётом 1/2/4/8/16 бит. Первое значение каждого цвета
и padding bits сохраняются; 16-битные значения обрабатываются целиком, включая
перенос между байтами. Отдельных row tags нет, размер работы равен decoded bytes.
Восстановление выполняется в том же буфере с отменой внутри длинных строк.
Правило padding приведено также в [Adobe PDF Reference, 4.8.4](https://opensource.adobe.com/dc-acrobat-sdk-docs/pdfstandards/pdfreference1.2.pdf#page=54).
Независимые декодеры не объявляются безусловными эталонами: MuPDF 1.28.2
обнуляет ненулевой packed padding, pypdf 6.19.0 расходится на части packed/16-bit
случаев. [Свидетельство](../development/pdf-tiff-evidence.json) сохраняет полные
побайтные результаты отдельно от совпадения значимых компонент; расхождения не скрываются.

`RunLengthDecode` читает literal runs по 1–128 bytes и повторения по 2–128 bytes;
128 завершает данные, даже если в физическом Length остались bytes. Байты 128
внутри literal/repeat payload остаются данными. Расход decoded квоты проверяется
до каждого добавления, отмена — между ограниченными runs. Нет второй полной
копии декодированного потока. Пропущенный EOD, неполный run и неверная decoded
длина дают адресный отказ. `encoded_data_end` — исключительная позиция после EOD,
`trailing_encoded_bytes` сообщает остаток физического encoded диапазона;
весь этот диапазон остаётся в source payload и учитывается в byte budget.
Непустые DecodeParms для RunLengthDecode не принимаются.
Алгоритм — [ISO 32000-1, 7.4.5](https://opensource.adobe.com/dc-acrobat-sdk-docs/pdfstandards/PDF32000_2008.pdf#page=37).

`ASCIIHexDecode` принимает обе формы hex digits и дополняет конечный нечётный
nibble нулём; `>` завершает данные. `ASCII85Decode` принимает полные и частичные
группы, отдельное `z` для четырёх нулей и окончание `~>`. Переполнение uint32,
одиночная конечная цифра, `z` внутри группы, недопустимые bytes и отсутствующий
EOD отвергаются. В обоих фильтрах игнорируются только PDF whitespace, включая
NUL/form feed; vertical tab не подменяется пробелом. Выход проверяется до append,
отмена — внутри сканирования, в том числе длинных whitespace runs.
Позиция EOD и trailing bytes отражаются теми же `encoded_data_end`/
`trailing_encoded_bytes`; encoded source остаётся неизменным.
Правила — [Adobe PDF Reference 4.8.1–2](https://opensource.adobe.com/dc-acrobat-sdk-docs/pdfstandards/pdfreference1.2.pdf#page=50).
[ASCII evidence](../development/pdf-ascii-evidence.json) сохраняет 24 полных
сравнения native/MuPDF и фактические результаты pypdf. В проверенном pypdf 6.19.0
NUL-hex и trailing-ASCII85 дают ошибки, поэтому full-byte agreement с ним — 14/24;
результаты не исправляются и не объявляются всеобщим conformance.

`LZWDecode` использует собственную таблицу до 4096 записей с prefix links,
без хранения отдельной растущей копии каждой фразы. Приняты MSB-first коды
9–12 бит, `EarlyChange=0/1` (по умолчанию 1), clear-table, EOD и специальная
ссылка на следующую создаваемую фразу. Заполненная таблица требует clear-table
или EOD. Квота проверяется до восстановления каждой фразы; отмена — между
кодами и внутри длинных prefix chains. EOD может завершаться внутри байта:
`encoded_data_end` указывает конец содержащего его байта, padding и последующие
bytes остаются в исходном payload. TIFF/PNG-предикторы и цепочки используют те же
общие бюджеты. Полный произвольный PDF этим не поддерживается.
Правила — [Adobe PDF Reference, 4.8.3](https://opensource.adobe.com/dc-acrobat-sdk-docs/pdfstandards/pdfreference1.2.pdf#page=52).
[Побайтное свидетельство](../development/pdf-lzw-evidence.json) содержит 58 originals:
Formats/MuPDF совпадают во всех; pypdf 6.19.0 — в 35. Он не применяет LZW PNG
predictor и расходится на длинных EarlyChange=0 потоках; ошибки и SHA сохранены.

Поддержаны также цепочки перечисленных фильтров в порядке массива `Filter`.
`DecodeParms` задаётся согласованным массивом словарей/null; весь план проверяется
до декодирования. Flate TIFF/PNG работает и на промежуточных стадиях, и в ObjStm.
`filter_chain` сохраняет порядок, `decode_stages` — размеры, SHA-256 результата
и работу каждой стадии. `filter` остаётся строкой для одного фильтра и становится
массивом для цепочки. `input_space=source` обозначает физические координаты первой
стадии; `stage[n]-output` обозначает координаты внутри результата предыдущей стадии.
Они не являются смещениями PDF. Каждая стадия расходует общий `max_pdf_tokens`;
`max_part_bytes` ограничивает каждый промежуточный результат, а `max_total_bytes`
учитывает физические bytes и сумму выходов всех стадий до удаления PNG-тегов.
Отмена проверяется внутри декодеров и между стадиями. Неподдержанные фильтры,
параметры и indirect Length остаются явными отказами.

Размеры и число записей проверяются до распаковки. `max_items` учитывает секции
и записи, `max_part_bytes` ограничивает физическую секцию и распакованный индекс,
включая теги PNG-строк до восстановления. `max_total_bytes` суммирует физические
секции и работу декодирования, включая эти теги. `decoded_bytes`/`decoded_xref_bytes`
показывают размер готовых записей; `decode_work_bytes`/`xref_decode_work_bytes` —
сумму выходов стадий до удаления PNG-тегов, используемую для квоты.
`max_pdf_tokens` и `max_pdf_depth` ограничивают синтаксис и обход ссылок.
Распаковка выполняется порциями до 64 КиБ с контрольными точками отмены;
повреждённый zlib, лишние/недостающие decoded bytes и неверные closing keywords
дают адресный отказ. Другие фильтры, внешние потоки и indirect Length
дают `UnsupportedDocumentError`; dictionary-only режим остаётся доступен.

Это физическая инспекция индекса, а не разрешение активных объектов или проверка
всего PDF. По умолчанию содержимое object streams не декодируется;
type 2 ещё не подтверждает наличие и границы вложенного объекта.
`assessment_complete=false`, `object_streams_decoded=false`. Наличие `Prev`
не доказывает число редакторских ревизий: linearized/hybrid PDF требуют отдельной
классификации. Движки текстового извлечения и отображения этим профилем не заменены.

### Содержимое object streams

Дополнительный `pdf_object_streams=True` требует обоих флагов `pdf_source=True`
и `pdf_decode_xrefs=True`. CLI использует `--pdf-object-streams` вместе с ними.
Инспектор собирает номера контейнеров из всех физических type-2 записей,
затем разбирает все их прямые xref-кандидаты в просмотренных секциях.
Исторические версии одного контейнера сохраняются отдельно по source offset:
выбор активной версии не выполняется. Отсутствующие кандидаты перечислены в
`unresolved_container_numbers`, исходные type-2 occurrences — в
`compressed_object_references` с xref offset, object number, container и index.

Приняты raw/Flate/LZW/RunLengthDecode/ASCIIHexDecode/ASCII85Decode,
прямые неотрицательные `N/First/Length`, generation 0 контейнера,
директория уникальных положительных object numbers со строго возрастающими
смещениями от нуля. Проверяется конец потока по Length, ровно N пар до First
и синтаксис одного объекта в каждом decoded диапазоне. Вложенные stream/obj/endobj
не принимаются. Правила контейнера описаны в
[ISO 32000-1, 7.5.7](https://opensource.adobe.com/dc-acrobat-sdk-docs/standards/pdfstandards/pdf/PDF32000_2008.pdf).

`kind=pdf-object-stream` сохраняет физические bytes от заголовка до `endobj`.
`kind=pdf-compressed-object` сохраняет исходный decoded диапазон без пересборки,
включая завершающий пробельный промежуток. В адресе `pdf:source-objstm=…/index=…/object=…`
указаны физическое смещение контейнера и внутренние index/object. Поля
`decoded_start/end` относятся к декодированному контейнеру, `source_byte_range=null`:
для Flate они не являются диапазоном байтов PDF. Строки остаются в payload;
проверка их синтаксиса не выдаётся за Unicode/семантический импорт.

Секции, их записи, контейнеры и члены используют общий `max_items` и
`max_pdf_tokens/max_pdf_depth`; физические bytes контейнеров и полные decoded
потоки добавляются к `max_total_bytes`. `max_part_bytes` ограничивает каждый
контейнер и его распаковку. Неизвестная decoded длина ограничивается внутри каждого decoder,
отмена проверяется при распаковке, чтении директории и членов. Ошибка не заменяет
ранее сохранённую dissection; исходный PDF не меняется.

Повторное использование номера под другой Type не превращает новый объект в ObjStm.
Обычный кандидат сохраняется как `pdf-non-object-stream-candidate` с исходными bytes,
generation, syntax kind, declared Type и адресами xref-секций. Для его stream требуется
прямой неотрицательный Length; raw bytes сохраняются без запуска фильтра или поиска
слов endstream/endobj внутри данных. Он расходует общие квоты, но не увеличивает
`decoded_object_streams`. `non_object_stream_candidates` сообщает отдельное число;
`unresolved_container_numbers` учитывает только действительно декодированные ObjStm.
Это классификация физических кандидатов; каждая историческая type-2 ссылка ещё
не привязана к собственной редакции. [Приёмка](../development/pdf-object-reuse-evidence.json).

Шифрование, indirect N/First/Length, другие фильтры/параметры и ненулевые поколения
настоящего ObjStm дают `UnsupportedDocumentError`.
`Extends` сохраняется как инертная ссылка, не обходится. `object_streams_decoded`
означает, что разобран хотя бы один кандидат; `decoded_object_streams` сообщает число.
`ownership_proven=false`, `active_resolution=false`,
`object_stream_reference_links_assessed=false` и `assessment_complete=false`:
локальная директория не доказывает владение исходным диапазоном, соответствие
каждой исторической ссылки и активное состояние объекта. Page content не исполняется;
семантические readers и их движки этим режимом не подменяются.

### Выбор действующих записей xref

`pdf_resolve_xrefs=True` требует `pdf_source=True` и `pdf_decode_xrefs=True`;
CLI — `--pdf-source --pdf-decode-xrefs --pdf-resolve-xrefs`.
Содержимое объектов для этого режима читать не требуется.
Выбор начинается от terminal startxref: сначала записи текущей classic-таблицы,
затем её XRefStm, затем Prev основной секции. Для stream-only секции берутся её
записи и её Prev. Совпавшие object numbers больше не заменяются: free/tombstone
подавляет старый body, новая generation подавляет прежнюю, а неизвестный будущий
тип сохраняется как `unknown-null`, без возврата к более старому объекту.
Приоритет текущей таблицы над её дополнением и дополнения над предыдущей
секцией следует [ISO 32000-1, 7.5.8.4](https://opensource.adobe.com/dc-acrobat-sdk-docs/standards/pdfstandards/pdf/PDF32000_2008.pdf).

`snapshot.details.effective_xref_entries` содержит выбранные записи по object number:
`state=free/uncompressed/compressed/unknown-null`, generation, native offset/free-link
либо пару container/index. `xref_offset` указывает физическую секцию;
`primary_xref_offset` — секцию, к которой принадлежит hybrid-дополнение.
`record_range.space=source` адресует bytes classic-записи в PDF,
`space=decoded-xref` — bytes записи внутри декодированного xref stream.
Исходные секции и их payload не заменяются итоговой таблицей.

`xref_search_order` показывает порядок поиска, роли primary/hybrid-supplement и
`search_index`. Prev hybrid-дополнения не обходится в этой роли: поле `ignored_prev`
показывает сохранённый указатель. Если секция также встречается в основной цепочке,
её Prev обходится в основной роли. Forward Prev допускается, как и в linearized
профилях; порядок поиска не является хронологией редактирования или доказательством
полной linearized-совместимости. Cycles отвергаются, непроверенные nested hybrid
профили не подменяются эвристикой.

Выбранные записи дополнительно учитываются в общем `max_items`, отмена проверяется
внутри выбора. `xref_record_selection_complete=true` относится только к приоритету
записей в просмотренной цепочке. `object_resolution_complete=false`,
`object_resolved=false`, `ownership_proven=false` и `assessment_complete=false`:
указатель ещё не доказывает владение body, соответствие запрошенной reference generation,
наличие вложенного объекта или semantic mapping. Для каждого исторического type-2
occurrence и произвольной ссылки разрешение остаётся отдельной работой.

## Независимые оригиналы и нативная приёмка

### Недостижимые компоненты DOCX

Rich reader сопоставляет физические ZIP entries с графом частей, загруженным
DOCX backend. Недостижимые части, их исходные `.rels` и замыкание внутренних
зависимостей сохраняются в `PackageGraph.parts`. Каждый компонент получает
оценку `opaque` с исходным адресом и SHA-256. Внешние связи сохраняются без
загрузки адреса. Циклы допустимы; отсутствующие внутренние targets отвергаются.

Связь с физическим инвентарём хранит Formats в metadata
`opendoc_formats.opc_orphans`; новые типы Model не требуются. Сырой XML `.rels`
остаётся форматным payload, а не объявляется семантически разобранным общим графом.
Импорт использует один ограниченный снимок входных bytes для семантического
парсера и инвентаря. Проверяются embedded-byte budget, XML nodes/depth и отмена;
DTD/entities не раскрываются, включая UTF-16.
Список исходных достижимых частей фиксируется до lazy-доступа backend к стилям,
настройкам и core properties: созданный по умолчанию объект не скрывает
физически существующую недостижимую часть с таким же именем.

После DOCX → OpenDoc → JSON → DOCX сохраняются исходные распакованные bytes
компонентов и их зависимостей. Фиктивные связи от основного документа не создаются.
Если редактируемая часть занимает URI сохранённой зависимости, экспортёр выделяет
ей другое имя и направляет её OPC-связи на актуальный объект. Например, изменение
семантической картинки не подменяет оригинальную картинку, на которую ссылается
неизвестный компонент. Явная правка `PackageGraph.parts[name].data` экспортируется;
исходный hash не используется для восстановления устаревшего содержимого.

Проверки `tests/test_opc_orphans.py` выполняют два фактических JSON/DOCX цикла
с правкой текста, циклическими компонентами, UTF-16 связями, неизвестным binary,
совпадением имён и нестандартным URI основного документа. Отдельно проверяются
правка картинки, отказ при повреждении связей/metadata и отмена во время ZIP copy:
модель, источник и прежнее назначение остаются неизменными, временный файл удаляется.
Побайтная гарантия относится к payload; упаковка ZIP и семантика неизвестного
формата внутри компонента этой проверкой не принимаются. Нативная интерпретация
произвольного вложения и полная совместимость отображения остаются отдельной работой.

### Пакетная правка и отображение

`tests/binary_fixtures.py` собирает DOCX из XML/ZIP, а PDF — из объектов, таблицы
xref, команд и Flate-потоков. Наши конвертеры эти оригиналы не создают.
Проверки сравнивают реальные части и RGB-пиксели, содержимое вложенных таблиц,
порядок блоков и диагностику известных потерь.

Для собственного DOCX fixture проверяется замена `Before` → `Edited`:
из содержимого пакета меняется только `word/document.xml`; PNG, `.rels` и
неизвестная бинарная часть остаются побайтно прежними. Дополнительная проверка
в Microsoft Word выполняется для `source.docx` и `edited.docx`, сохранённых
`test_docx_native_edit_preserves_unknown_binary_parts_relationships_and_table_order`:

```powershell
./tools/document_anatomy_word_acceptance.ps1 -FixtureRoot <каталог-fixture>
uv run python -m tools.document_anatomy_visual_check <каталог-fixture> --output .opendoc-formats/visual-anatomy
```

Word открывает fixture read-only, проверяет текст, страницы, ширины таблицы,
картинку и гиперссылку и сохраняет PDF-превью. Независимый Poppler renderer
сравнивает страницы при 108 dpi: исключается только прямоугольник изменённого
слова с небольшим отступом, меньше 1% страницы; остальные пиксели должны совпасть.
Word, Poppler, PyMuPDF и Pillow нужны для этой дополнительной приёмки; они не добавляются
в базовый профиль библиотеки. Это конечный fixture-контракт, а не заявление о
полной поддержке OOXML, всех вложений или семантических правок.

В этом sparse оригинале `After ` + hyperlink `Link` импортируется как `AfterLink`
по принятой Word-проекции обычного w:t; native snapshot сохраняет исходные пробелы.
Геометрия при отсутствующем `pgSz`, непроверенные whitespace scopes и отображение
sparse defaults остаются в [TODO](../development/todo.md); приёмка нативной пакетной
правки не закрывает эти семантические и визуальные свойства.
