# Отступ таблицы и явные табуляции Word

DOCX использует общий API OpenDoc 0.11.1: `TableIndent` принадлежит таблице,
`TabStops` — абзацу. Модель проверяет декларации и JSON, адаптер измеряет исходные
OOXML-значения и записывает нативные объявления. Codec и схема модели не дублируются.

```python
from opendoc_model import TableIndent, TabStop, TabStops, set_table_indent, set_tab_stops

set_table_indent(table, TableIndent(30))
set_tab_stops(paragraph, TabStops((TabStop(396, alignment="right", leader="line"),)))
# Явное удаление прямых объявлений:
set_table_indent(table, None)
set_tab_stops(paragraph, None)
```

Положительные и отрицательные позиции заданы в points; один twip равен 0,05 pt.
Ноль — явный отступ; `TableIndent(value_pt=None)` — неизвестное значение,
которое нельзя угадать при записи. Отсутствие декларации разрешает наследование.
Выравнивание таблицы сохраняется отдельно: отступ не означает одинаковый
визуальный сдвиг при любом выравнивании Word.

Общие alignment: `left`, `center`, `right`, `decimal`, `bar`.
Общие leader: `none`, `dot`, `dash`, `line`, `heavy`, `middle-dot`.
`line` переводится в нативный `underscore` согласно
[контракту OOXML](https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.wordprocessing.tabstopleadercharvalues).
`TabStop(position_pt, kind="clear")` подавляет унаследованную явную позицию.
Неизвестные alignment/leader остаются `None`, а не превращаются в guessed defaults.
Нативные `start`/`end`/`num` удерживаются в opaque extra с расположенным LOSS;
из них не выводится известная межформатная alignment.

`TabStops(inherit=False)` материализуется как clear для текущих известных
explicit positions стилей и defaults. Это конечный нативный snapshot, поэтому
режим замены имеет расположенный `docx.tab-stops-materialized` LOSS. Новые
будущие style positions автоматически не подавляются. Обычный автоматический
интервал табуляции не изменяется. Неизвестное или циклическое наследование
отклоняется; fallback positions не угадываются.

Стили сохраняют native declarations в `style.properties['docx_tab_stops']`
(список position_pt/alignment/leader с именами OOXML), поскольку TextStyle
не является владельцем общего tagged TabStops. Прямые правки и удаление этого
native свойства меняют только tabs в копии исходной части стилей; остальные
объявления, basedOn и расширения сохраняются. Общий API нельзя записывать в
свойства объекта неправильного типа.

Позиции должны представляться точно в signed 32-bit twips. NaN, бесконечность,
boolean, неизвестные значения и более 256 explicit stops не принимаются.
Неподдержанные исходные объявления имеют native XPath в диагностике;
попытка записи без явной замены или удаления отклоняется до публикации.
При переходе в другой формат утрата отступа/табуляций имеет расположенный LOSS,
который может отклонить внешний нулевой бюджет качества.

Собственный пример принят в Word 16.0 build 16.0.17932: 30 pt и
396 pt/right/line, два DOCX/JSON цикла, правка и удаление. Полные страницы обоих
циклов совпадают с оригиналом попиксельно при Poppler 96 dpi. Нативная правка
в Word до 12 pt и 296 pt/center/dot сохраняется следующим публичным циклом.
Полный inherited/conditional table cascade, RTL layout и оформление
произвольного документа остаются в TODO.

Повторяемая Word-проверка: `tools/docx_direct_layout_acceptance.ps1` принимает
только собственные fixtures из `.opendoc-formats`, открывает исходники read-only,
проверяет SHA-256, измеряет native значения, экспортирует полные PDF-страницы
и редактирует отдельную копию. Вычисленные default stops отделены от явно
объявленных; фактический XML-инвентарь дополнительно проверяется тестами.
