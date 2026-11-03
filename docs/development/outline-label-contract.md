# C-OUTLINE-LABEL-01: форматированный label оглавления

Статус: общий `OutlineLabel` доступен в закреплённом `opendoc-model==0.1.0`.
[Потребительская приёмка SDK](model-api-acceptance.json) проверяет установленный
wheel, публичные экспорты, JSON и ограничения. Подключение к нативным readers/writers
и полная приёмка Formats остаются отдельными задачами; наличие DTO не означает
готовую проекцию или визуальную эквивалентность.

## Назначение контракта

В опубликованном API OutlineEntry.title — строка, включая допустимую пустую.
Outline/OutlineTarget уже дают entry IDs, порядок, parents и anchor/page targets.
Heading задаёт только общий уровень. Эти DTO достаточно для plain outline,
но не для отдельного label с TextRun styles и inline Formula:

```tex
\section[Short \textbf{bold} $x^2$]{Long visible heading}
```

Короткий аргумент стандартных TeX headings влияет на TOC/running marks и отличается
от видимого заголовка. Flattening до строки теряет структуру; замена body heading
коротким label меняет документ. Formats пока сохраняет исходник и located opaque
оценку, не объявляя rich label поддержанным через plain OutlineEntry.title.

## Минимальный общий контракт

Сначала проверить существующие общие DTO/helpers. При подтверждении пробела
расширить существующий OutlineEntry минимальным необязательным rich label на
основе уже имеющихся TextRun/Formula или эквивалентного общего inline carrier.
Не вводить второй реестр outline или форматный TeX codec в Formats.

- Отсутствие rich label сохраняет поведение старого plain title. Явный пустой
  label отличим от отсутствующего. Rich content не добавляется в body и не создаёт
  скрытый Paragraph/Heading или дополнительный маркер списка.
- TextRun styles, inline formulas с явным fallback, FONT/resource refs и provenance
  сохраняются независимо от body heading. Нет TeX commands/CSS/format names как
  обязательной части схемы. Display formulas и неподдержанные inline types имеют
  явную политику, а не скрытое преобразование.
- Уточнить авторитетность plain title и rich label при правке/удалении. Молчаливое
  восстановление прежнего formatted label после plain edit недопустимо; mismatch
  получает определённый отказ/инвалидацию либо явный helper по общим правилам SDK.
  Model не парсит TeX, чтобы вычислить plain title из формулы.
- Публичный codec/envelope/unknown fields, traversal/node refs, validation и selected
  budgets охватывают label и его детей. Общие composition/remap/extract операции
  учитывают FONT/anchor refs; offsets/порядок не угадываются из текста.
- Несколько entries могут ссылаться на один heading anchor; это не даёт права
  выбрать один label по first/last wins. Форматный source binding выбирает Formats.

## Приёмка Model

1. Plain/absent/empty rich label, styled runs и inline Formula проходят два JSON-цикла
   без flattening; старый plain outline не меняется.
2. Правка/снятие rich label и plain title имеет согласованную авторитетность.
   Некорректная комбинация отказывает атомарно, без восстановления устаревшего label.
3. Walk/inspection различают body text и label children. Unknown fields сохраняются,
   mutable значения после codec независимы.
4. Неверные inline types, FONT refs, dangling targets и превышение точных
   node/depth/byte/embedded quotas дают расположенные отказы без частичной записи.
5. Composition/remap/extract сохраняют или явно отвергают зависимости; никаких
   parser/rendering engines в SDK.

## Приёмка Formats

После опубликованного API подключить finite TeX short-title parser/export:
plain/styled/math/empty labels, отдельные heading/entry IDs и ссылки, два JSON/TeX
цикла, явная правка и снятие label, сравнение независимого TOC/running-head original.
TeX scanning, escaping, source spans/bindings, moving arguments, class/counters,
рендер и native acceptance остаются в Formats. Это не закрытие полного OF04.

Кандидат принимать только отдельно по неизменённому wheel SHA. Основную `.venv`,
pin и замороженные кандидаты Page/Image/BlockGroup не менять; commit/push/release
не требуются для передачи контракта или изолированной приёмки.

## Принятый конечный API

`OutlineEntry.label` — необязательный `OutlineLabel(title, content)` из TextRun и
inline Formula с явным fallback. Label отсутствует в legacy wire, если не задан;
пустой content отличим от отсутствующего label. Plain representation задаёт producer:
SDK не вычисляет его из TeX. Label.title должен совпадать с Entry.title; plain edit
с прежним label отказывает, явная замена или удаление label авторитетны.

`iter_outline_inlines` возвращает отдельные detached occurrences с entry_id/index/path.
`walk_model` и body text не получают дополнительных runs. В labels разрешены ссылки
на body anchors, FONT и named styles; собственный body anchor на label child отвергается.
Неизвестные поля и возвращаемые mutable значения проходят independent codec/getter checks.

Проверен wheel SHA256
`06f4ab1202fc534b7d3f1fc808eb3c7016d427f0ed6b363002e62508c2e977c9`:
все 54 файла manifest совпадают с wheel и установленной копией, Python source set
не содержит неперечисленных модулей. В отдельной Python 3.12.16 среде установлен
только Model. Это неопубликованный кандидат с metadata version 0.19.0, не официальный
выпуск с тем же номером; основная `.venv` и pin не меняются.

`tools/outline_label_consumer.py` проверяет шесть сценариев: два JSON-цикла,
styled/math/empty/absent labels, provenance, ссылки и независимость body/getters,
plain edit mismatch и explicit removal, десять invalid profiles, merge с явным
keep_last и extract с замыканием FONT/style/link dependencies, выбранные квоты.
FONT payload в этом fixture opaque: проверены ссылки/kind, не разбор font program.

| Квота fixture | Парный JSON transport | set_outline |
| --- | --- | --- |
| max_nodes | 249 | 249 |
| max_depth | 14 | 13 |
| max_bytes | 4334 | 1469 |
| max_embedded_bytes | 17 | 17 |

Граница проходит, уменьшение на один отказывает без изменения destination metadata
и wire. Setter и полный transport имеют разную область учёта; числа относятся
к этому fixture, а не универсальному размеру label.

```powershell
python -I tools/outline_label_consumer.py --candidate .opendoc-formats/outline-label-candidate --output .opendoc-formats/outline-label-candidate/consumer-evidence.json
```

Candidate directory содержит неизменённые wheel/provenance. Доказательство связано
с SHA самого consumer. Эта приёмка не засчитывается как TeX parsing/export,
TOC/running-head rendering или source mapping. Эти требования Formats остаются в TODO.
