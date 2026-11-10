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
| PNG | Исходная signature и chunks, offsets/lengths/CRC, размеры IHDR и raw property bits; пиксели не декодируются |
| TTF/OTF sfnt | Исходная программа целиком, directory records, смещения/размеры таблиц, объявленные checksums и SHA-256 payload; по `sfnt_checksums=True` — проверка сумм |

`capture=True` возвращает payload в памяти; обычный снимок хранит инвентарь.
`BinarySnapshot.to_dict()` — диагностический формат Formats, отдельный от JSON
документа OpenDoc. Пакет общей модели и её codec не меняются.
ZIP/XML, CFBF, PNG, sfnt и исходная PDF-инспекция используют стандартную библиотеку Python.
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
`directory_tree_assessed=false` и `assessment_complete=false`: полное storage
tree, остальные ограничения directory fields/имён, все reserved fields, семантика OLE и соответствие
всей спецификации этой проверкой не подтверждаются. CLSID и времена — исходные
значения; обработчик по CLSID не создаётся. Ремонт исходника не выполняется.

`header_fields_assessed` отдельно отмечает конечный аудит header CLSID, reserved bytes
и нулевого заполнения header sector v4 по [MS-CFB 2.2](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-cfb/05060311-bfce-4b12-874d-71fd4ce63aea).
`header_field_constraints_valid` отражает проверенные MUST, а
`header_field_recommendations_met` — SHOULD minor version 0x003E. Ненулевой
transaction signature не объявляется ошибкой без сведений о producer transactions.
`header_field_findings` содержит code/rule/field, locator `cfbf:header/field` и
абсолютный byte range. Замечания не меняют bytes или payload. Неподдержанный
structural profile и повреждённые allocation chains по-прежнему дают исключение,
а не частичный snapshot. Отсутствие findings не подтверждает полную CFBF-конформность.

Указатели directory entries проверяются отдельно от правил сортировки имён и цветов.

Конечный аудит `directory_fields_assessed` проверяет запрещённые `/`, `\`, `:`, `!`,
ранний NUL в заявленном имени и точное имя root, а также обязательные нулевые поля
stream/storage/root и инициализацию незанятых slots. Основа —
[MS-CFB 2.6.1](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-cfb/60fe8611-66c3-496b-b70d-a504c94c9ace),
[root](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-cfb/026fde6e-143d-41bf-a7da-c08b2130d50e)
и [unused entries](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-cfb/b37413bb-f3ef-4adc-b18e-29bddd62c26e).
`directory_field_constraints_valid` относится к проверенным MUST-правилам;
`directory_field_recommendations_met` отдельно отражает SHOULD для stream state bits.
Старший DWORD v3 имеет rule `compatibility` и не делает профиль недействительным.
`directory_field_findings` содержит code, field, directory index и точный byte range;
locator имеет вид `cfbf:directory=N/field`. Исходные entry/sector bytes и payload
сохраняются. Количество findings отдельно ограничено `max_items`, обход отменяемый.
Не проверенные требования к пустым именам, reserved header fields и полная
корректность дерева этим флагом не подтверждаются.

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

Цвета проверяются независимо: `directory_colors_assessed=true`,
`directory_color_constraints_valid` и `directory_color_findings`. Замечание содержит
code, location `cfbf:directory=N/color`, точный byte offset, исходный value и
related_directory/relation для связи с соседом или storage owner.
`invalid-color-flag` сообщает значение вне 0/1; `red-sibling-tree-root` — красную
вершину дерева, выбранную child указателем storage; `consecutive-red-siblings` —
два красных узла, связанных left/right sibling. Проверяются также недостигнутые
записи и компоненты с циклами, без рекурсии и исправления исходника. Цвета не
подтверждают корректность указателей или имён; все замечания сохраняют физические
сектора и logical payload.

Root directory entry может быть красным или чёрным. Красный storage owner и
красный узел его собственного child tree не считаются соседями одного дерева;
для вершины child tree действует отдельное требование black. Равная чёрная высота
и балансировка не навязываются: [MS-CFB 2.6.4](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-cfb/d30e462c-5f8a-435b-9c4c-cc0b9ea89956)
разрешает all-black binary search tree. Значения флагов —
[MS-CFB 2.6.1](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-cfb/60fe8611-66c3-496b-b70d-a504c94c9ace).
Полная валидность дерева остаётся отдельной открытой проверкой; Color constraints
не добавляют сторонних зависимостей или ролей Model.

Порядок и уникальность имён имеют собственные признаки
`directory_name_order_assessed`, `directory_name_order_valid` и
`directory_name_order_findings`. При недопустимом графе указателей порядок не
оценивается, valid равен null: из повреждённых связей не угадывается storage owner.
Иначе для каждого storage выполняется итеративный in-order обход всего sibling
поддерева. Сравнение соседей в этом порядке проверяет ограничения предков тоже;
дубли находятся во всём scope, а одинаковые имена в разных storages разрешены.
`sibling-name-order` и `duplicate-sibling-name` содержат source location/offset/name,
related_directory и storage_owner. Исходные bytes не исправляются.

Сравнение следует [MS-CFB 2.6.4](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-cfb/d30e462c-5f8a-435b-9c4c-cc0b9ea89956):
сначала UTF-16 byte length с terminator, затем числовые значения UTF-16 units
после simple uppercase. Locale, Unicode normalization, full uppercase/casefold и
преобразование surrogate pairs не применяются. Поэтому ß не разворачивается в SS,
а два Deseret case variants остаются разными именами. Greek prosgegrammeni сохраняет
один simple-uppercase unit вместо full expansion. Используется Unicode runtime;
`directory_name_comparison_unicode_version` сообщает его версию. Спецификация
разрешает учитывать новые casing mappings более поздних Unicode releases.

Все 65536 units сверены с простым uppercase из первичного
[UnicodeData 15.0](https://www.unicode.org/Public/15.0.0/ucd/UnicodeData.txt),
включая identity для surrogates: [доказательство с SHA](../development/cfbf-unicode-evidence.json).
`tools/cfbf_unicode_acceptance.py` воспроизводит проверку на локальном UnicodeData
той же версии, что и runtime, без сети в самой проверке. Dataset не входит в wheel;
новых библиотек и общих DTO Model нет. Это finite order/uniqueness audit, а не
подтверждение всех ограничений имени или всей спецификации CFBF.

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
`inspect_binary`. XML-флаг `parse_xml` не отключает разбор allocation tables CFBF.
Для совместного бюджета предусмотрен отдельный режим ниже. Полная приёмка
семантики OLE-объекта в Word или другом приложении остаётся отдельной задачей.

## Дерево вложенных ZIP и OLE/CFBF

`opendoc_formats.anatomy_tree.inspect_container_tree` обходит полные ZIP members
и логические CFBF-потоки, начинающиеся с ZIP/CFBF signature. Например, DOCX ZIP →
`word/embeddings/own.bin` → CFBF miniFAT/FAT stream → вложенный ZIP.
Полные PNG payload также получают отдельные листовые snapshots с тем же общим бюджетом.
XML в этом режиме остаётся непрозрачным, включая OPC control parts; приложения,
макросы, handlers по CLSID и сетевые ресурсы не запускаются.

Каждое вхождение имеет отдельный `BinarySnapshot` и `location`: tuple исходных
локаторов от корня, у которого tuple пуст. Одинаковые bytes в двух частях остаются
двумя вхождениями. Physical sectors, root mini stream и фрагменты отдельных
потоков повторно не обходятся: это storage aliases, а не новые вложенные объекты.
Префикс перед ZIP, внутренние Package wrappers, PDF и шрифты автоматически
не распаковываются; такие payload остаются opaque. Ole10Native envelope описан ниже.
Произвольный поиск сигнатуры
внутри неизвестных bytes не выполняется.

Профиль выбирает **начальная сигнатура** либо точное имя CFBF-потока
`\x01Ole10Native`, что явно записано в `selection_policy`.
ZIP внутри корректного CFBF может распознаваться общим auto-detector как
self-extracting ZIP; дерево использует явный CFBF profile и проверяет его структуру.
Повреждённый CFBF не исправляется переключением на найденный ZIP. Это конечная
политика вложенного обхода, не полная проверка альтернативных интерпретаций polyglot.
Прежний `inspect_binary` сохраняет свои правила неоднозначности.

`AnatomyLimits.max_items` и `max_total_bytes` общие для всех вхождений.
За каждый контейнер списывается большее из 1, числа inventory items и числа
CFBF directory slots. Bytes учитывают исходный контейнер плюс сумму размеров
его inventory payload, минимум один байт inventory даже для пустого ZIP.
Storage aliases и повторные occurrences учитываются дополнительно; это бюджет
разбора/копирования, а не уникальных bytes исходника. Следующий parser получает
только остаток бюджета. Per-input/per-part/ratio limits сохраняются.
`max_depth` считает корень уровнем 0 (по умолчанию 8, максимум 64),
`max_containers` включает корень (по умолчанию 128).

`capture=False` скрывает payload результата, но использует тот же бюджет:
для безопасного обхода полные логические потоки всё равно читаются.
Известная сигнатура повреждённого child даёт отказ всего вызова с полным scope;
квота и отмена не возвращают частичного дерева. `compare_container_trees`
сравнивает буквальные пути и отдельные snapshots; semantic correspondence
и lossless conversion из совпадения адресов не следуют.

```powershell
python -m tools.container_anatomy own.docx --output .opendoc-formats/own-tree --max-depth 4 --max-containers 32
```

CLI создаёт только новый каталог: `inventory.json` связывает scopes с каталогами
`container-000000`, где лежат обычные snapshots и сгенерированные payload filenames.
Имена исходных ZIP members/CFBF streams не превращаются в disk paths.
Есть `--compare`, `--no-payloads` и общие flags AnatomyLimits. Отказ разбора
не создаёт выход, ошибка записи удаляет только созданные этим вызовом файлы.
Это собственный физический parser без зависимости от olefile, Office и XML engines;
Model DTO/codec не меняются.

## Обёртка Ole10Native

Профиль основан на [MS-OLEDS 2.3.6 OLENativeStream](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-oleds/cc825ec3-f0ed-4023-97f6-13c323ac1172):
четырёхбайтовый NativeDataSize и массив NativeData заданной длины.
Размер обязан точно совпадать с остатком полного логического потока;
усечённый header, слишком большой размер и trailing bytes дают расположенный отказ.
Источник не ремонтируется и не дополняется нулями.

`inspect_binary(data, container="ole-native", capture=True)` возвращает два items:
`ole-native:header` и `ole-native:data`, с исходными offset/length, SHA и payload.
Их конкатенация восстанавливает полный вход. Без capture содержимое не выдаётся,
но источник проверяется теми же квотами. OPC/EPUB audit к этому профилю не применяется.

В дереве профиль выбирается только для логического CFBF-stream с точным именем
`\x01Ole10Native`. Обычный ZIP member или случайный size prefix не объявляется
OLE envelope. Обёртка становится отдельным occurrence, а вложенный ZIP/CFBF,
начинающийся непосредственно с NativeData, получает дополнительный scope
`ole-native:data`. Глубина, число контейнеров, исходные и inventory bytes/items
списываются с того же общего бюджета; прежние CFBF bytes сохраняются полностью.

NativeData может содержать собственный формат приложения, что отдельно разъясняет
[Microsoft Open Specifications](https://learn.microsoft.com/en-us/answers/questions/2277690/what-is-the-data-structure-of-nativedata-in-olenat).
Инвентарь поэтому содержит `application_data_assessed=false`: подтверждена обёртка,
а не семантика произвольного OLE-объекта. Packager metadata, filenames/commands,
links и их внутренние layout variants пока остаются opaque; поиск ZIP после
неизвестного prefix не выполняется. Прежнее общее auto detection не меняется:
оно может видеть самораспаковывающийся ZIP с prefix, но не доказывает OLE envelope.

```powershell
python -m tools.document_anatomy own.native --container ole-native --output .opendoc-formats/own-native
```

CLI использует сгенерированные имена частей. Содержимое и имена из NativeData
не служат путями файловой системы, не исполняются и не передаются OLE handlers.
Это собственный parser без olefile/oletools и без изменения общей Model.

## Физический инвентарь PNG

`inspect_binary("own.png", capture=True)` и явный `container="png"` разбирают
signature и полные исходные chunks без Pillow. Профиль основан на
[W3C PNG: chunk layout](https://www.w3.org/TR/png-3/#5Chunk-layout) и
[порядке chunks](https://www.w3.org/TR/png-3/#5ChunkOrdering).
CRC проверяется по type+data каждого chunk; неподтверждённые bytes не ремонтируются.
Проверены finite IHDR width/height, depth/color combinations, compression/filter/
interlace profile, PLTE size/order и обязательность, непрерывность IDAT, завершающий
пустой IEND без trailing bytes. PNG marker внутри неизвестного payload не ищется.

`png:signature` и `png:chunk=N:TYPE` содержат размер, SHA-256 и, при capture,
полный raw payload, включая length/type/data/CRC. Их конкатенация восстанавливает
источник побайтно. Chunk details указывают offset/data_offset/data_length, CRC
и raw ancillary/private/reserved/safe-to-copy bits. Эти биты сами по себе не дают
разрешения изменять неизвестные данные. Unknown critical/ancillary chunks сохраняются
и перечисляются отдельно; полная семантика метаданных не объявляется проверенной.

Конечные `metadata_declarations` описывают tRNS/gAMA/sRGB/pHYs вместе с локатором
и data offset. Основание — [tRNS](https://www.w3.org/TR/png-3/#11tRNS),
[gAMA](https://www.w3.org/TR/png-3/#11gAMA), [sRGB](https://www.w3.org/TR/png-3/#11sRGB)
и [pHYs](https://www.w3.org/TR/png-3/#11pHYs) спецификации PNG.
tRNS сохраняет raw 16-bit samples и отдельно эффективные значения по исходному
bit depth. Старшие неиспользуемые биты не превращаются в отказ или потерю raw данных;
16-bit ключ сравнения не усекается до 8 бит. Palette alpha содержит только
объявленные entries и явное implicit alpha=255 для остатка палитры.

Gamma хранится исходным целым gamma×100000, sRGB — числом rendering intent,
pHYs — двумя исходными pixels-per-unit и unit code. Unit unknown не получает
выдуманного DPI. Цветовой профиль по этим полям не выбирается и не применяется.
Повторные декларации не выбираются по принципу first/last wins: каждый экземпляр
получает `metadata_findings` с code/location/message, а неоднозначный тип не попадает
в разобранные declarations. Непринятые lengths/fields/order также сохраняются raw
с расположенным замечанием, без исправления или отказа всего физического inventory.
Это проверка конечного профиля деклараций, а не всех PNG ancillary constraints.
`BinarySnapshot.to_dict()` отделяет вложенные metadata/unknown fields от snapshot:
правка словарного результата не меняет исходные наблюдения.

`image_data_assessed=false`, `ancillary_semantics_assessed=false`,
`color_interpretation_assessed=false` и
`assessment_complete=false`: IDAT не распаковывается, scanlines/filters/palette
indices, APNG frames, цветовые профили и пиксели не проверяются. Корректный CRC
не означает декодируемую картинку. Header dimensions — наблюдение, а не разрешение
создать растровый буфер такого размера. Этот parser не заменяет WMF/EMF renderer
или полноценный image decoder и не добавляет PNG в реестр документных converters.

Input/total bytes, число items и полный размер каждого chunk ограничены
AnatomyLimits; XML-флаг к PNG не применяется. Отмена проверяется между chunks
и после CRC; отдельное хеширование/CRC ограниченного chunk неделимо.
Ошибка не возвращает частичный снимок и не меняет исходник. CLI сохраняет
только сгенерированные имена частей; --compare сравнивает literal chunk addresses,
не semantic equivalence пикселей.

Дерево контейнеров распознаёт PNG в полных ZIP members, CFBF streams и NativeData
Ole10Native. Каждый экземпляр имеет свой scope и списывает исходные/inventory bytes,
items, глубину и число вхождений из общего бюджета. Содержимое самих chunks дальше
не обходится. Самостоятельное auto detection сохраняет отказ от неоднозначных
polyglot-интерпретаций; tree использует явный профиль начальной сигнатуры.

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
Для ZIP, включая исходный инвентарь PPTX и EPUB, отмена проверяется при обходе
центрального каталога и между порциями распаковки до 256 КиБ.
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
Для физической инспекции гибридных PDF 1.x косвенный `Length` дополнительного
потока поддерживается, если объявившая его классическая таблица содержит точную
запись несжатого целого объекта. `length_source` сохраняет адрес, generation,
значение и адрес таблицы. Для PDF 2.0 исправленная спецификация требует прямой
`Length`. [Исправления ISO 32000-2, 7.5.8.2](https://pdf-issues.pdfa.org/32000-2-2020/clause07.html#7582-cross-reference-stream-dictionary)
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
до декодирования. Ключи словаря параметров со значением `null` трактуются как
отсутствующие. При захвате исходных байтов словарь сохраняется в оригинальном виде.
Flate TIFF/PNG работает и на промежуточных стадиях, и в ObjStm.
`filter_chain` сохраняет порядок, `decode_stages` — размеры, SHA-256 результата
и работу каждой стадии. `filter` остаётся строкой для одного фильтра и становится
массивом для цепочки. `input_space=source` обозначает физические координаты первой
стадии; `stage[n]-output` обозначает координаты внутри результата предыдущей стадии.
Они не являются смещениями PDF. Каждая стадия расходует общий `max_pdf_tokens`;
`max_part_bytes` ограничивает каждый промежуточный результат, а `max_total_bytes`
учитывает физические bytes и сумму выходов всех стадий до удаления PNG-тегов.
Отмена проверяется внутри декодеров и между стадиями. Неподдержанные фильтры,
параметры и косвенная длина вне описанного гибридного профиля остаются явными отказами.

Размеры и число записей проверяются до распаковки. `max_items` учитывает секции
и записи, `max_part_bytes` ограничивает физическую секцию и распакованный индекс,
включая теги PNG-строк до восстановления. `max_total_bytes` суммирует физические
секции и работу декодирования, включая эти теги. `decoded_bytes`/`decoded_xref_bytes`
показывают размер готовых записей; `decode_work_bytes`/`xref_decode_work_bytes` —
сумму выходов стадий до удаления PNG-тегов, используемую для квоты.
`max_pdf_tokens` и `max_pdf_depth` ограничивают синтаксис и обход ссылок.
Распаковка выполняется порциями до 64 КиБ с контрольными точками отмены;
повреждённый zlib, лишние/недостающие decoded bytes и неверные closing keywords
дают адресный отказ. Другие фильтры, внешние потоки и косвенная длина вне профиля
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
неотрицательный Length либо принятая ниже исходная ссылка на скаляр; raw bytes сохраняются без запуска фильтра или поиска
слов endstream/endobj внутри данных. Он расходует общие квоты, но не увеличивает
`decoded_object_streams`. `non_object_stream_candidates` сообщает отдельное число;
`unresolved_container_numbers` учитывает только действительно декодированные ObjStm.
Это классификация физических кандидатов; каждая историческая type-2 ссылка ещё
не привязана к собственной редакции. [Приёмка](../development/pdf-object-reuse-evidence.json).

`N`, `First`, `Length` настоящего ObjStm и `Length` обычного кандидата могут ссылаться
на несжатый объект с прямым неотрицательным целым body. Formats выбирает xref record
по цепочке, в которой объявлен физический кандидат: primary table, hybrid supplement,
затем Prev. Generation ссылки, record и заголовка должны совпадать. Заголовок и
`endobj` проверяются по точному смещению; поиск подходящего литерала не выполняется.
При нескольких исторических контекстах объявления все значения должны совпадать; разные значения
дают явный отказ. Это не выбор активного значения для каждой исторической type-2 ссылки.

Тот же разбор применяется к целочисленным `Predictor`, `Colors`,
`BitsPerComponent`, `Columns` и `EarlyChange` внутри прямого словаря
`DecodeParms` или словаря стадии в прямом массиве. Путь параметра сохраняется
в наблюдениях. Если новая ревизия подменяет значение, текущая связь с ранее
декодированным объектом получает статус `container-changed-from-decoded-parameters`.
Для `Filter` принимается ссылка на несжатый объект с прямым PDF-именем.
Элементы прямого массива фильтров могут использовать такие же ссылки.
В отчёте сохраняются путь, имя фильтра и диапазон исходного объекта.
`DecodeParms` также может ссылаться на несжатый объект с прямым словарём
или массивом словарей и `null`. Ссылка на словарь допустима и для отдельной
стадии прямого массива. Значения внутри косвенного словаря должны быть прямыми
неотрицательными целыми или `null`. Исходный диапазон и значение структуры
учитываются при проверке текущей ревизии.

`source_integer_observations` хранит контекст/выбранную xref-секцию, адрес record,
generation, исходный диапазон скаляра, SHA и значение. Исходные scalar bytes не
переписываются. Lookup indexes, скаляры и observations расходуют общий `max_items`;
прочитанные scalar bytes входят в `max_total_bytes`, обход xref и парсинг —
в `max_pdf_tokens`. Работают отмена и прежняя атомарность CLI. Рекурсивные scalar
ссылки и compressed scalar bodies пока явно отклоняются; compressed Length ObjStm
не является допустимым способом обхода этой границы.
[Приёмка восьми оригиналов](../development/pdf-source-integer-evidence.json)
подтверждена pypdf и MuPDF без repair. Правила stream/object streams —
[ISO 32000-1, 7.3.8 и 7.5.7](https://opensource.adobe.com/dc-acrobat-sdk-docs/pdfstandards/PDF32000_2008.pdf).

Шифрование, другие неподдержанные фильтры/параметры и ненулевые поколения
настоящего ObjStm дают `UnsupportedDocumentError`.
`Extends` сохраняется как исходная ссылка и имеет отдельный ограниченный аудит
деклараций коллекции, описанный ниже. `object_streams_decoded`
означает, что разобран хотя бы один кандидат; `decoded_object_streams` сообщает число.
`ownership_proven=false`, `active_resolution=false`,
`object_stream_reference_links_assessed=false` и `assessment_complete=false`:
локальная директория не доказывает владение исходным диапазоном и активное состояние объекта.

Внутри проверенных decoded members `indirect_references` перечисляет синтаксические
косвенные ссылки: object/generation, точный decoded range и SHA исходного написания.
Строки, hex strings, имена и комментарии не выдаются за ссылки; повторного
лексического поиска по payload нет. Каждая запись расходует общий `max_items`;
`object_stream_member_reference_items` сообщает число таких записей.

`compressed_member_reference_declarations` сопоставляет ссылки только из members,
получивших `matched-declared-member`, с выбранным xref их исторического или текущего
контекста. Отчёт различает отсутствующий target, free/unknown запись, несовпадение
generation и совпавшее uncompressed/compressed объявление. Адрес record и выбранная
секция сохраняются; для compressed generation сравнивается с нулём. Обход и
проекции расходуют общие `max_pdf_tokens`/`max_items`.
Для несжатой цели `target_header_status` сообщает результат проверки номера,
поколения и ключевого слова `obj` строго по выбранному смещению xref.
Совпавший заголовок получает точный диапазон и SHA-256. Несовпадение,
повреждённый синтаксис и смещение вне файла различаются в отчёте.
После заголовка парсер проверяет одно обычное значение и завершающее `endobj`.
Статус `matched-ordinary-body` сопровождается диапазоном и SHA-256 всего объекта.
Для внутреннего потока с прямым `/Length` инспектор проверяет `endstream` и
`endobj` после указанного числа байтов. `matched-stream-body` содержит диапазон
закодированного потока и SHA-256 всего объекта. Косвенный `/Length` читается
по xref выбранной ревизии. Для сжатого целого инспектор сверяет номер, индекс
и параметры контейнера. `target_stream_length_observation` сохраняет адрес
и хеш выбранного скаляра, а для сжатого целого также декодированный диапазон.
Повреждённая или неподдержанная длина и внешние потоки получают отдельные
статусы. Повреждённый синтаксис и отсутствие `endobj`
отмечаются отдельно.
Повторные ссылки используют один результат проверки того же объекта.
Работа над заголовками и телами отражена отдельно и входит в общий бюджет ObjStm.
`target_range_status` отмечает пересечение физического диапазона цели с другой
проверенной целью, контейнером или секцией xref. Для пересечения указывается
диапазон одного свидетеля. В аудит входят и физические диапазоны разобранных
целочисленных объектов. Для несжатого объекта косвенной длины собственный
результат доступен в `target_stream_length_range_status`. Точные совпадения
диапазонов учитываются один раз.
`disjoint-from-inspected-ranges` описывает только уже исследованные диапазоны.
`object_stream_bound_member_reference_declarations_assessed` относится только к
этому конечному сопоставлению. Для сжатой цели `target_member_status` сообщает
результат проверки номера и индекса в том же контексте и той же проекции.
При совпадении отчёт содержит адрес, хеш и диапазон декодированного кандидата.
Для унаследованной цели инспектор проверяет выбранный контейнер и его параметры
в контексте исходной ссылки. Результат используется повторно в пределах этого
контекста. Проверка расходует общие лимиты и не обходит ссылки самой цели.
`target_body_resolved` остаётся false, пока принадлежность диапазона и полное
разрешение тела не подтверждены. Текущая проекция не использует старое тело,
если текущие параметры его контейнера не подтверждены. В исторической проекции
переиспользуется проверенный скаляр с теми же номером объекта, поколением и
физическим смещением. Если ревизия выбирает другой скаляр, нативный парсер читает
его по xref этой ревизии и записывает результат в `historical_parameters`.
Связи строятся при совпадении значений с параметрами декодирования. Для
изменённых, повреждённых и неподдержанных параметров отчёт сохраняет причину отказа.
Полное разрешение ссылок
остаётся в TODO; `object_stream_reference_links_assessed` остаётся false.

Page content не исполняется;
семантические readers и их движки этим режимом не подменяются.

### Привязка объявленных сжатых объектов к xref-контексту

`pdf_object_streams=True` также создаёт `compressed_object_links`: для каждого
исходного type-2 occurrence выбирается собственный primary xref context с его
hybrid/Prev приоритетами, затем выбранный контейнер, его generation/offset и
конкретный index. Совпадение object number в decoded directory обязательно.
Успешный `matched-declared-member` содержит исходную xref record range,
container record range, физический locator/SHA контейнера и locator/SHA/decoded range
его члена. Исторические контейнеры с одинаковым номером не смешиваются;
отсутствующая текущая запись контейнера может наследоваться по Prev этого контекста.

`shadowed-reference` отмечает occurrence, перекрытый основной таблицей hybrid;
free/unknown container не воскрешает старый контейнер. Остальные статусы различают
сжатый/ненулевого поколения/не-ObjStm контейнер, неизвестный диапазон index и
несовпадение номера члена. У supplement с несколькими primary owners —
`ambiguous-primary-context`, без угаданного владельца.
`object_stream_declared_links_assessed=true` относится только к этому конечному
сопоставлению деклараций. `object_resolved=false`, `ownership_proven=false` и общая
неполная assessment сохраняются: поддельный header внутри stream bytes,
владение диапазоном и активное состояние после произвольных incremental edits этим
не доказываются. `unresolved_container_numbers` остаётся физической сводкой и не
заменяет статусы каждой ссылки.

Кэш xref contexts и каждая ссылка расходуют общий `max_items`; значение
`object_stream_link_work_items` показывает дополнительную работу. Проходы и lookup
расходуют тот же `max_pdf_tokens`, что syntax/decoders, с контрольными точками отмены.
Новые PDF/image packages не требуются; original/payload bytes не изменяются.

### Текущая проекция type-2 ссылок

Текущие type-2 ссылки оцениваются отдельно в `compressed_object_current_links`:
выбирается конечный `startxref`, включая унаследованные compressed users. Поле
`xref_offset` сохраняет адрес исходной записи, `context_xref`/`primary_xref` —
текущий контекст. При замене только контейнера новая проекция указывает новые
member locator/hash/range, а `compressed_object_links` сохраняет историческое
сопоставление. Free/unknown/обычный/сжатый/ненулевого поколения контейнер не
подменяется прежним ObjStm; перекрытый direct/free user не входит в текущие roots.

`object_stream_current_declared_links_assessed` и `object_stream_current_links_xref`
описывают этот конечный профиль текущих деклараций. Косвенные параметры контейнера
требуют наблюдений в текущем primary context; иначе статус —
`container-parameters-not-assessed-in-current-context`, без member binding.
Это не разрешает контекстно различающиеся параметры, владение физическими
диапазонами или произвольные object bodies. `object_resolved`/`ownership_proven`
остаются false. Текущие lookup/rows входят в общий `object_stream_link_work_items`,
тот же token budget и отменяемый обход; отдельно прибавлять их к квоте не нужно.

Для принятого профиля косвенных `N`/`First`/`Length` текущие значения дополнительно
наблюдаются по конечному primary xref. В `current_parameters` указаны исходные
decoded values, текущие значения и scalar witnesses с точными ranges/SHA/xref.
Совпадение разрешает использовать уже декодированный member; изменённое значение
даёт `container-changed-from-decoded-parameters` без member binding. Недействительный
или неподдержанный scalar получает `container-invalid-current-parameter` либо
`container-unsupported-current-parameter` с именем поля и reference. Исторический
отчёт не меняется; контекстно отличающийся поток этим не декодируется заново.
Чтение, неудачная parse attempt, delimiter witness и текущий lookup входят в общий
учёт scalar work; отмена и ResourceLimitError не преобразуются в обычный статус.
Повторный текущий обход через Extends не меняет исторические параметры. При наличии
косвенных параметров `parameter_xref_contexts` показывает контексты decode;
`xref_sections` может дополнительно содержать текущий inspection context.

### Коллекции object streams: Extends

`/Extends` не наследует members и не заменяет xref. По
[ISO 32000-1, 7.5.7](https://opensource.adobe.com/dc-acrobat-sdk-docs/pdfstandards/PDF32000_2008.pdf)
это ссылка на другой ObjStm в коллекции с ациклическими связями. Инспектор
начинает с прежних физически объявленных кандидатов type-2, затем итеративно
находит Extends targets по unambiguous primary/hybrid xref context. Цель без своих
type-2 users тоже становится кандидатом: проверяются заголовок, dictionary, длина,
фильтры, members и прежние ресурсные границы. Ошибки не исправляются поиском
похожего object header или выбором новой версии по одному object number.

`object_stream_extends_links` хранит source object/generation/offset, context и
primary xref, target reference, выбранные xref record range/offset и status:
`matched-declared-extends`, `missing-target`, `generation-mismatch`,
`target-not-uncompressed`, `nonzero-target-generation`, `target-not-object-stream`
или `ambiguous-primary-context`. `in_cycle` отмечает только рёбра самого цикла,
а не входящий в него префикс. `object_stream_extends_declared_links_assessed=true`
относится к этим декларациям; `object_stream_extends_dag_valid` равен false при
найденном цикле, null при неподтверждённой цели, true при полном ациклическом
сопоставлении выбранного профиля. Это не утверждение обо всех ObjStm в файле.

Предварительный проход строит полный набор contexts до декодирования; indirect
scalar parameters затем проверяются прежним механизмом сразу для всех contexts.
Nodes, edges и кэш выбранных xref records расходуют общий max_items; дополнительные
work items указаны в `object_stream_extends_work_items`. Синтаксис, lookup и graph
work используют тот же max_pdf_tokens и проверяют отмену; собственный лимит
каждой nested коллекции не сбрасывается. Cycle detection не использует рекурсию.

Исторические декларации сохраняют свою версию цели. Контейнер, унаследованный
новой редакцией без нового физического объявления, не повышается молча до latest
scope в историческом отчёте; текущая проекция хранится отдельно, как описано ниже.
Новые candidates имеют
прежние SHA/source ranges, ownership_proven=false, active_resolution=false,
extends_resolved=false. Рёбра имеют object_resolved=false и members_inherited=false:
аудит коллекции не создаёт отсутствующие compressed xref references и не объединяет
наборы объектов. [Доказательства девяти originals](../development/pdf-extends-evidence.json)
и 15 focused tests включают цепочки, hybrid, incremental replacements, inherited
scope boundary, циклы, ошибки поколений/типов, точные квоты и отмену. Pypdf strict
подтверждает валидную цепочку; malformed/hybrid originals проверяются отдельно
по буквальным source offsets. Ремонт backend не выдаётся за исходную совместимость.

### Текущая проекция коллекций Extends

При найденных Extends-декларациях инспектор дополнительно выбирает effective xref
от terminal startxref. `object_stream_current_extends_roots` перечисляет выбранные
compressed references с их record range и записью контейнера. Свободный, неизвестный,
сжатый, ненулевого поколения или не-ObjStm контейнер получает отдельный status;
старый контейнер не подставляется вместо новой недопустимой записи. Статус
`selected-container` подтверждает выбор контейнера, не разрешённый member или ownership.

`object_stream_current_extends_links` обходит коллекцию в этом текущем контексте,
включая унаследованный физический ObjStm. Поэтому замена родителя отражается здесь,
а `object_stream_extends_links` сохраняет историческую цель. Удалённая/free/unknown
цель не воскрешается из Prev. Цикл, созданный новой версией родителя, отмечается
в текущем графе отдельно. `object_stream_current_extends_xref` — выбранный terminal
context; `object_stream_current_extends_dag_valid` имеет прежние true/false/null
значения, но только для коллекций выбранных compressed roots. Отсутствие текущих
users оставляет пустую проекцию. Если Extends-деклараций нет, отдельный проход не
включается, `object_stream_current_extends_assessed=false`.

Физический контейнер декодируется один раз при согласованных N/First/Length во всех
проверяемых contexts. `xref_sections` перечисляет эти inspection/parameter contexts,
`historical_xref_contexts` — их историческую часть; у цели, открытой только текущим
проходом, исторический список пуст. Это не доказательство физического владельца
диапазона. Контекстно различающиеся indirect parameters остаются явным unsupported
профилем, не заменяются первой попавшейся трактовкой потока.

Кэш текущего xref, roots и обход расходуют те же max_items/max_pdf_tokens; bytes
обеих версий родителей учитываются прежним общим decoder budget. Поле
`object_stream_extends_work_items` теперь охватывает оба прохода;
`object_stream_current_extends_work_items` — его текущая часть, её не надо повторно
прибавлять к общему числу. Проверяются отмена и точные item/token/byte границы.
[Десять paired originals](../development/pdf-current-extends-evidence.json) показывают
замену/удаление/повреждение целей и roots, цикл и исчезнувших users; 17 focused tests
включают hybrid primary, независимое strict pypdf-чтение валидной правки и source SHA.
Model, ownership/body resolution, полный mapping и классификация редакций не меняются.
Правила index и generation — [PDF Reference 1.7, 3.4.6–3.4.7](https://opensource.adobe.com/dc-acrobat-sdk-docs/pdfstandards/pdfreference1.7old.pdf).
Пять независимых исходных случаев и hashes связей приведены в
[свидетельстве](../development/pdf-object-links-evidence.json). В нём отдельно
записаны предупреждения pypdf о ненулевом начале classic subsection: его чтение
не выдаётся за доказательство отсутствия repair. Точные исходные адреса и
shadowing проверяют собственные byte assertions; Fonts/Model API не меняются.

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
внутри выбора. Разбор синтаксиса и основной выбор xref используют один `max_pdf_tokens`:
каждый посещённый primary и каждая просмотренная запись, включая затенённые,
расходуют остаток бюджета. Stage selection не получает новую полную квоту после
разбора source sections. На точной границе результат совпадает с обычным inspection,
на один ниже выдаётся расположенный отказ `xref lookup` без изменения исходника
или предыдущей dissection. Это budget фактической работы, не только размера результата.
`xref_record_selection_complete=true` относится только к приоритету
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
