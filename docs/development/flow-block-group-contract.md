# C-BLOCK-GROUP-01: составные группы потока

Статус: общий `BlockGroup` доступен в закреплённом `opendoc-model==0.1.0`.
[Потребительская приёмка SDK](model-api-acceptance.json) проверяет установленный
wheel, публичные экспорты, JSON и ограничения. Подключение к нативным readers/writers
и полная приёмка Formats остаются отдельными задачами; наличие DTO не означает
готовую проекцию или визуальную эквивалентность.

## Назначение контракта

BlockGroup задаёт вложенный поток документа с абзацами и таблицами.
VectorGroup описывает graphics scene и не заменяет семантический flow container.
Нативная проекция list scopes и вложенных групп принадлежит Formats.

Собственные исходники для Formats:

```html
<blockquote id="quote"><p id="before">Before</p>
  <table id="data"><tr><td>Cell</td></tr></table><p>After</p></blockquote>
<ol><li id="item">Start<table><tr><td>Cell</td></tr></table>End</li></ol>
```

Плоские sibling blocks сохраняют таблицу, но теряют общий quote/list scope,
его anchor и связь продолжения с тем же item. Копирование quote anchor на каждого
ребёнка создаёт неоднозначность. Повторная роль ListItem у хвостового абзаца
может добавить лишний номер. Empty paragraph вместо контейнера не является
эквивалентной семантикой и может изменить компоновку. Пока Formats сохраняет
полные исходные XHTML bytes как opaque, а не выдаёт flattening за semantic support.

## Минимальный общий контракт

Имена API согласует Model; предлагается нейтральный BlockGroup со следующими данными:

- Упорядоченные children: list[Block], допускающие вложенные группы, Table,
  Paragraph, Formula и Image. Группа входит в обычный Block union, включая TableCell.
- Необязательная общая роль generic/quotation либо эквивалентный semantic carrier;
  никаких HTML tag names, CSS selectors или package parts как обязательной схемы.
- Обычные properties и provenance; собственный anchor контейнера, не скопированный
  в children. Отдельные детские anchors остаются независимыми.
- Согласованный способ привязать один ListItem к compound group. Общая нумерация
  считает такой item один раз; children без роли не становятся новыми item.
  Существующий Paragraph owner продолжает работать. Вложенные item и продолжения
  ссылаются на owner anchor по тем же правилам parent_id/continuation_of.

Предпочтительный минимальный вариант list binding — типизированная ссылка группы
на существующий primary Paragraph owner внутри children; continuation_of у остальных
абзацев использует его anchor, нумерация считает owner один раз. SDK не добавляет
невидимые абзацы автоматически и не выводит binding по первому ребёнку. Если Model
выберет непосредственный group owner, нужно явно описать совместимость старого
Paragraph API и запрет двойного номера; форматный обходной алгоритм не подходит.

Model владеет только DTO, codec/envelope/unknown fields, walk/node references,
общей валидацией и selected limits, anchors и list numbering. Rendering/cascade,
source parsing, native locators, split correspondence и visual acceptance остаются
в Formats. Не добавлять EPUB/HTML/OOXML engines и не делать default layout выводов.

## Приёмка Model

1. Group[Paragraph, Table, Paragraph], nested group и group в TableCell проходят
   два JSON цикла без flattening, перестановок и подстановки стилей/геометрии.
2. walk_model и существующие node references различают group, детей и отдельные
   occurrences. Anchors контейнера и детей не конфликтуют и не клонируются.
3. Compound list item с таблицей считается один раз; следующий item получает
   следующий номер. Nested/empty/continuation/start/restart cases и существующие
   paragraph lists сохраняют прежние правила.
4. Unknown JSON fields сохраняются; неверный child/type/role/link и циклы дают
   расположенный отказ. max_nodes/max_depth/max_bytes учитывают group и детей;
   проверяется граница квоты и независимость mutable values после codec.
5. Импорт SDK без форматных движков, без локальных parser/rendering helpers Formats.

## Приёмка Formats

Независимые XHTML/EPUB originals с quote и compound LI → Model → JSON → HTML/EPUB:
проверить nested block order, один marker/number, anchors/internal links,
редактирование таблицы и продолжения, исходные payload и диагностику unsupported
профилей. Сравнить оригинал с результатом в независимом браузере и принять native edit.
Это не замена C-MAP-01 или полной EPUB/CSS приёмки.

Draft принимается отдельным неизменённым candidate wheel с SHA и выбранными
лимитами. Основная `.venv`, официальный pin и ранее замороженные свидетельства
C-PAGE-DEFAULTS-01/C-IMAGE-RECT-01 не меняются. При сомнении в API сначала сверить
существующие контракты Model; не реализовывать форматную логику ради этих fixtures.

## Потребительская проверка кандидата

`tools/block_group_consumer.py` проверяет установленный wheel с SHA256
`5fac0c362b5f343f59984f437f135cba9bb3fd907abfce823c9b8b1cecbcc1be`.
Все 54 исходных файла установленного SDK побайтно совпадают с manifest и wheel;
это неопубликованный кандидат, а не официальный выпуск с тем же номером 0.19.0.
В отдельной среде Python 3.12.16 установлен только `opendoc-model`.

Восемь сценариев проверяют два JSON-цикла quote → compound item → table/paragraphs/
nested item, отдельные anchors и внутренние ссылки, один номер и continuation,
правку ячейки, mutable independence неизвестных полей, пустые/повторные scopes,
merge с переназначением ссылок и extract с замыканием зависимости owner.
Шесть неверных owner bindings, удаление используемого owner, неверные children/role/
binding и цикл получают явные отказы. Удаление всей группы допустимо.

Для этого fixture минимальные совместные encode/decode бюджеты: max_nodes=322,
max_depth=20, max_bytes=5620; каждое значение проходит, уменьшение на один
отказывает без изменения исходной Model. Это границы данного transport fixture,
а не число пользовательских блоков или бюджет HTML/CSS parser.

Воспроизведение в отдельной среде с установленным кандидатом:

```powershell
python -I tools/block_group_consumer.py --candidate .opendoc-formats/block-group-candidate --output .opendoc-formats/block-group-candidate/consumer-evidence.json
```

Каталог candidate содержит неизменённый wheel и upstream `provenance.json`.
Основная `.venv`, pin и замороженные кандидаты других контрактов не меняются.
Эта приёмка подтверждает конечный нейтральный API; source parsing, сохранение CSS,
экспорт EPUB/HTML, нативные правки и сравнение с браузером остаются работой Formats.
