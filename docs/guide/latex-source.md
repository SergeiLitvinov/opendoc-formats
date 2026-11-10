# Чтение исходного LaTeX

`read_document("source.tex")` использует собственный конечный lexer/parser в базовом
пакете. ID формата — `latex`. Python-зависимостей сверх OpenDoc Model нет; TeX,
Pandoc и shell commands не запускаются. Исходный UTF-8/UTF-8 BOM файл сохраняется
точными байтами в inert attachment `latex-original-source`.

## Профиль source-v1

Поддерживаются body `document` или самостоятельный fragment, documentclass/title/
author/date как текстовые metadata, абзацы и комментарии, экранированные символы,
простые буквенные акценты, группы и локальные textbf/textit/emph/underline/texttt,
bfseries/itshape/normalfont. Заголовки section/subsection/subsubsection/paragraph/
subparagraph/chapter становятся heading paragraphs. Itemize/enumerate задают
вид и уровень списка. Reader использует ListItem закреплённого Model 0.1.0:
continuation_of связывает продолжение с первым абзацем того же пункта, parent_id
указывает родителя вложенного списка. Пустой/child-only пункт становится пустым
Paragraph с ролью и якорем. Вне списка абзац остаётся без роли. Номера вычисляет
официальный iter_list_numbers; TeX engine для чтения не запускается.
Простой setcounter для текущего enumerate переносит start/restart.
Custom labels, текст перед первым item, пустое окружение и item вне списка
получают located opaque причины. В таком документе reader оставляет списки
source profile без предполагаемых общих номеров, сохраняя полный исходник.

Inline `$...$` и `\(...\)`, display `$$...$$` и `\[...\]` становятся
`Formula(format=LATEX)`. Значение — исходный TeX между delimiters; оно не исполняется
и не преобразуется в MathML. Display не создаёт отдельный Paragraph без реальной
границы абзаца; порядок text/formula внутри Paragraph сохраняется.
Labels становятся anchors, `ref` — внутренней ссылкой.
Pageref/eqref/cite удерживают target и тип команды, но дают диагностированный
текстовый fallback без вычисления page numbers, equation numbers или библиографии.

## Текстовые верхние и нижние индексы

Braced `\textsuperscript{...}` и `\textsubscript{...}` используют существующие
`TextStyle.superscript/subscript`. Они работают в обычном тексте, пунктах/продолжениях
списка и Heading 1–5, включая оглавление. Изменение или снятие поля стиля через Model
управляет экспортом; исходная роль из native hints не восстанавливается.

Formats хранит только границы TeX-команды в `TextRun.properties.latex_text_script_scope`
(`kind`, инертный `id`): иначе каждый фрагмент разного шрифта создавал бы отдельную
команду TeX с лишним промежутком. Разбиение run сохраняет общий scope; соседние
исходные команды остаются раздельными. Hint используется только при совпадении
его kind с актуальным полем стиля. Содержимое id никогда не выводится в TeX.
Некорректный или расширенный hint отклоняется, размер id ограничен 256 символами.

`latex_bold_declaration/latex_italic_declaration` в свойствах стиля различают
декларацию шрифта и текстовую команду: `\itshape` и `\textit` имеют разные правила
italic correction. Они принимают только bool и действуют только при активном
общем bold/italic. `\normalfont` сбрасывает шрифт, сохраняя положение индекса;
пробел-разделитель control word не превращается в текст, пустая строка остаётся
границей абзацев. Эти native детали принадлежат Formats, общий стиль и JSON — Model.

Вложенные индексы, порядок index/underline, nested emphasis toggling и пустые/
многоабзацные аргументы получают located opaque diagnostics с исходными bytes.
Одновременные superscript/subscript, неподдержанный стиль или индексы в объектах
вне нативного текстового профиля дают явный отказ `latex.text-script-profile`.
DOCX-мост для обхода такого отказа не применяется. Геометрия произвольных
текстовых индексов этим не объявляется полностью принятой.

## Ограничения и происхождение

По умолчанию файл ограничен 10 MiB (`ImportOptions.max_input_bytes`), поток —
250 000 tokens, вложенность групп/окружений — 64, диагностика — 10 000 records.
`properties.source_span` и provenance сохраняются через JSON: источник,
нулевые Unicode character offsets start/end (end exclusive), line/column с единицы.
Offsets относятся к декодированному тексту без UTF-8 BOM, не к позициям байтов.

```python
from opendoc_formats import read_document, write_document

result = read_document("source.tex")
if result.success:
    write_document(result.document, "source.json")
    write_document(result.document, "preview.html")
```

Неизвестные команды и неподдержанные окружения получают located opaque record:
сохранённые исходные байты подтверждены resource ID. Текст внутри неизвестных групп
может стать fallback; его нельзя считать результатом исполнения программируемого TeX.
HTML writer переносит информацию о невосстановленных исходных функциях в отчёт.
`assessment_complete=False`; сохранение source attachment не означает lossless conversion.

Input/include/includegraphics/bibliography/usepackage и команды файлового/программного
ввода не исполняются и не читают дополнительные файлы. Пользовательские макросы
удерживаются в источнике, но пока не раскрываются. Таблицы, math environments,
рисунки, bibliography/include и ограниченные macros остаются в OF04.
Запись `native-text-v1` не требует дополнительных Python-пакетов: одна секция
с обычными абзацами, заголовками article или book/report, списками, TeX-формулами и прямым bold/italic/underline,
без произвольных стилей, ссылок, геометрии, шрифтов и других объектов. Текст должен содержать одиночные
пробелы без начальных/конечных пробелов: TeX иначе меняет whitespace.
Все спецсимволы экранируются; `[ ]` не становятся display-math delimiters,
текст `\input{...}` не становится командой. Преамбула использует конечный профиль
буквального стандартного класса article/book/report и его options; TeX не запускается.
Два публичных JSON/TeX цикла сохраняют текст и выделение. Произвольная компоновка
не объявляется сохранённой (`LOSS latex-layout`, assessment неполная);
независимые конечные корпуса списков и формул описаны ниже.

Reader связывает заголовки с официальным `Heading` из OpenDoc. Writer использует
`get_heading`, не выводит роль из имени стиля. Иерархия зависит от стандартного
класса в `document.metadata.documentclass`:

| Уровень Model | article / исходный fragment | book / report |
| --- | --- | --- |
| 1 | section | chapter |
| 2 | subsection | section |
| 3 | subsubsection | subsection |
| 4 | paragraph | subsubsection |
| 5 | subparagraph | paragraph |
| 6 | вне профиля | subparagraph |

Chapter и section имеют разные общие уровни; source class сохраняется через JSON.
Выбор класса не превращается в путь к `.cls` или произвольную TeX-команду.
Исходная звёздочка
сохраняет нумерованный или ненумерованный вариант. Общий Heading без исходной
декларации записывается со звёздочкой, чтобы не добавлять нумерацию по догадке.
Пустые служебные стили source reader допускаются, произвольный визуальный
каскад — нет. Правка и удаление через `set_heading` управляют результатом:
устаревшие `latex_heading_level` и `Heading N` не возвращают удалённый заголовок.
Короткий optional title остаётся source-only opaque. Его диагностика охватывает
весь аргумент `[... ]`, с Unicode character offsets, строкой/колонкой и ссылкой
на неизменённый `latex-original-source`, включая BOM/CRLF. Scanner завершает
optional argument по первому незащищённому `]`; braces защищают внутренние brackets,
а bare `[` не создаёт вложенный optional scope. Комментарии и escaped braces
не ломают границу. Внутри argument token pass проверяется отмена и предел глубины.
Это корректное чтение и сохранение исходника, не native semantic short-title export.
Для styled/math label передан [C-OUTLINE-LABEL-01](../development/outline-label-contract.md):
plain OutlineEntry.title не подменяет форматированный отдельный label.

Chapter без подтверждённого book/report, уровни вне таблицы и нестандартные классы остаются
вне этого нативного профиля. `part`, front/main/back matter, произвольные class options
и counters требуют отдельной приёмки. Margins и служебные packages используют
конечную преамбулу writer; это не сохранение произвольной исходной page geometry.
Только article/book/report выбирают класс вывода; для остальных metadata действует
прежний article-default без восстановления исходного `.cls`.

### Буквальные параметры стандартного класса

Reader хранит options в format-specific metadata
`opendoc_formats.latex_documentclass_options`: `{"version": 1, "source": "11pt,a5paper,oneside"}`.
Нативный writer сохраняет порядок и пробелы, размер шрифта `10pt/11pt/12pt`, бумагу
`a4paper/a5paper/b5paper/letterpaper/legalpaper/executivepaper`, `landscape`,
`oneside/twoside`, `onecolumn/twocolumn`, `openright/openany`, `titlepage/notitlepage`,
`draft/final`, `leqno/fleqn`. Длина source ограничена 2048 ASCII-символами.
Отсутствующий исходный optional argument записывается как `source: null`, пустой `[]`
как `source: ""`; writer различает их. Модель без carrier использует прежний
default `12pt,a4paper`. Правка или удаление carrier управляет результатом;
старый source attachment не возвращает удалённые значения.

Неизвестные options, macros и комментарии в options остаются исходными байтами
с located opaque diagnostic `documentclass-options`. Неподдержанный/будущий carrier
даёт атомарный отказ `latex.preamble-profile`. Если другие объекты требуют DOCX-моста,
writer отказывает при отличающейся преамбуле, чтобы не потерять class/options.
Произвольные packages, geometry и программируемая преамбула остаются вне профиля.
Эти данные принадлежат Formats; общая Model не получает TeX parser или новую page geometry.

Пять независимых originals/reference cases проверяют columns, размер шрифта и бумаги,
book, пустые options, BOM/CRLF и явную правку options. Два JSON/TeX цикла дают
16 точных полностраничных сравнений в каждом из MuPDF и Poppler при 108 dpi,
без масок, допуска и растеризации. [Свидетельство](../development/latex-class-options-evidence.json)
содержит SHA исходников, отдельного edit reference и экспортированных файлов.

Независимые book/report originals с шестиуровневой иерархией, starred вариантами
и явной структурной правкой проходят два JSON/TeX цикла. Оглавление добавляет
независимый compiler harness, оно не объявляется функцией parser. Все 42 полных
страничных сравнения точны отдельно в MuPDF и Poppler при 108 dpi, включая пустые
страницы book, без масок/допуска и raster objects.
[Свидетельство](../development/latex-chapters-evidence.json) содержит SHA оригиналов,
независимых edit references и cycles; native приёмка не меняет границу Model/Formats.

В заголовках поддержан inline Formula LATEX: выражение и fallback проходят
два JSON/TeX цикла вместе с официальной ролью Heading, её правкой и удалением.
Нумерованные и starred команды сохраняют вариант исходника. Display Formula
в аргументе заголовка получает атомарный отказ без DOCX-моста.
Три независимых примера, включая матрицу, проверяются с оглавлением в отдельной
компиляторной обёртке: три прохода pdflatex для original и каждого из двух циклов
дают одинаковые страницы при 108 dpi без image XObjects. Сам tableofcontents
не объявляется поддержанной командой source reader; обёртка проверяет запись
и повторное чтение moving arguments через auxiliary files.

Источник с неизвестными body-командами не попадает в этот профиль. Opaque
диагностика собственной фиксированной преамбулы допустима только когда её
точный текст повторяется; исходное вложение не является видимым объектом.
Для объектов вне профиля сохраняется DOCX bridge с extra `docx`. Без backend
writer явно отказывает, сохраняя прежний файл. Таблицы, заголовки вне профиля,
сложное оформление и полный source → JSON → TeX остаются в OF04.

### Нативные списки без Office

itemize/enumerate записываются как настоящие TeX-окружения с item, а не строки
с нарисованными номерами. Продолжение остаётся в том же пункте без нового item;
пустой родитель и вложенный список не сливаются с соседним пунктом. Структуру,
start/restart и нумерацию определяют только публичные get_list_item,
get_anchor и iter_list_numbers. parent_id управляет физической вложенностью;
level остаётся индексом общей нумерации, не догадкой о родителе.

Неисполняемые комментарии `% opendoc-par-v1:...` содержат base64 JSON с ID якоря,
группы, level, start/restart. Это идентичность и декларации, а не кэш текста или
дерево списков: текст, вид окружения, родители и продолжения повторно выводятся
из TeX. Реальные setcounter сверяются с вычисленной SDK нумерацией; противоречие
с аннотацией отклоняется. Неизвестная версия, повреждённый payload и повторные
ключи дают InvalidDocumentError. Размер аннотации ограничен 65536 encoded chars,
число аннотаций — выбранным max_nodes. Они не исполняют команды и не читают файлы.

Два JSON/TeX цикла сохраняют ID, parent/continuation, start/restart, порядок,
текст и внешний абзац. Правка/снятие роли через SDK не восстанавливается из
latex_list_id/list_kind/list_level. Несуществующая ссылка отклоняется Model;
разорванное продолжение или неактивный родитель не получает предполагаемый scope.
Отказ сохраняет прежний файл и не использует DOCX bridge для обхода проверки.

Конечный профиль использует стандартные enumerate counters enumi–enumiv:
до четырёх окружений одного вида и шести всего, номер от 1 до 2147483647.
Custom labels, произвольные counter-программы, объекты вне текстового профиля,
пустое продолжение и непредставимый порядок остаются явным отказом. Правила
TeX list/counter принадлежат Formats и сверены с
[исходниками LaTeX](https://github.com/latex3/latex2e/blob/main/base/ltlists.dtx).

Независимая приёмка `tests/writers/test_latex_list_acceptance.py` компилирует три
собственных оригинала и два цикла через pdflatex с отключённым shell escape.
Проверяются продолжения, пустой/child-only пункт, вложенность, start/restart и
внешний абзац; страницы каждого примера совпали попиксельно при 108 dpi, image
XObjects отсутствуют. Тест опционален при отсутствии TeX engine; он не добавляет
зависимости пользователю. Это конечный корпус, не гарантия полной компоновки TeX.

Незакрытые группы, math delimiters и mismatched environments дают
`InvalidDocumentError`; превышение профиля — `ResourceLimitError`, отмена —
`OperationCancelledError`. Reader failures остаются исключениями по общему контракту
реестра. Прямой reader выбрасывает `OperationCancelledError`; `read_document`
возвращает `import.cancelled` без модели также при отмене внутри reader.

### Нативные TeX-формулы

`Formula(format=LATEX)` внутри Paragraph и отдельным block записывается
непосредственно как inline/display TeX; два вида размещения не смешиваются.
Значение переносится точной строкой, без text fallback, изображения, DOCX или
преобразования в другой математический язык. Поддержаны дроби, корни, индексы,
суммы/интегралы, греческие команды, math fonts, масштабируемые delimiters,
matrix/pmatrix/bmatrix/Bmatrix/vmatrix/Vmatrix/smallmatrix/cases/aligned/gathered
внутри выражения. Это сохранение исходного TeX, а не построение математического AST.
Определения команд сверены с [официальным руководством amsmath](https://www.latex-project.org/help/documentation/amsldoc.pdf).

Сохраняются `value`, `format`, `display`, `fallback_text`, порядок формул и текста,
границы абзацев и роли списков через два JSON/TeX цикла. Поле display управляет
режимом после правки; `latex_math_delimiter` удерживает исходный вариант delimiters
только когда он соответствует этому полю. Снятый узел не восстанавливается.
Неисполняемый комментарий `% opendoc-math-v1:...` содержит только base64 JSON
с текстовой заменой, включая пустую, и опциональным `placement=block` для отдельного
Formula block. Такой marker допускается только для единственной формулы вне списка
и без соседнего текста. Он не хранит значение или дерево выражения и не может
переопределить реальный TeX. Повреждённые, повторные, будущие или
непривязанные annotations отклоняются. Экранированный percent остаётся текстом.

Formats проверяет конечный allowlist команд, парность groups/environments и
left/right, обязательные braced arguments. Лимиты: 65536 символов и tokens
выражения, 64 группы, 16 math environments, 65536 символов fallback и 524288
encoded chars комментария; число annotations ограничено выбранным max_nodes.
Это конечный синтаксический профиль, не универсальная проверка корректности TeX.
Обычные комментарии внутри выражения сохраняются; trailing comment без перевода
строки отклоняется, чтобы он не поглотил закрывающий delimiter.

Нумерованные equation/align и labels/refs, неизвестные macros, активный синтаксис,
file/shell commands, не-ASCII математическая запись, MathML/OMML и FormulaTree,
математические шрифты вне выражения, геометрия и opaque свойства остаются вне
профиля. Writer явно отказывает и сохраняет прежний файл, даже при установленном
Office extra. DOCX bridge для этих формул не применяется. Reader удерживает
неподдержанный оригинал inert; formula source не исполняется.

Четыре независимых originals с inline/display, матрицами, cases/aligned, отдельным
Formula block и формулами в продолжении/вложенном списке компилируются pdflatex с отключённым shell escape.
Два JSON/TeX цикла дают попиксельно одинаковые страницы при 108 dpi, без image
XObjects. Приёмка подтверждает этот корпус; общий `LOSS latex-layout` и неполная
assessment остаются. Требований к Model сверх существующего Formula нет:
тип/codec/limits принадлежат Model, TeX parsing/синтаксис/запись и приёмка — Formats.

## Нативные таблицы tabular

Reader разбирает непустой прямоугольный `tabular` с колонками `l/c/r` и `p{размер}`,
вертикальными разделителями `|`/`||`, полными `hline` и частичными `cline` между строками.
Конечный профиль сохраняет и отсутствие линий, повторные линии, пустые ячейки,
последнюю строку без явного `\\`, inline math и braced text styles/scripts.
Alignment tokens внутри формул и групп не делят внешнюю таблицу.
Table/Paragraph/Formula/TextRun и JSON принадлежат Model; сканирование TeX,
исходные spans, локальное оформление и приёмка принадлежат Formats.

Профиль `Table.properties['opendoc_formats.latex_tabular']` версии 1 содержит
`columns` (буквальные l/c/r, p и вертикальные линии), `rules` (число hline на каждой
из `rows+1` границ) и `trailing_break` (явный перенос последней строки).
Версия 2 сохраняет те же поля; `rules` содержит упорядоченные последовательности
на каждой границе: null означает hline, `[m,n]` — cline с включёнными индексами
логических колонок, начиная с 1. Порядок, повторы и пересечения сохраняются,
включая смешанные hline/cline и multicolumn. Только буквальные целые
`1 <= m <= n <= columns` принимаются; macros/произвольные команды не исполняются.
Таблицы без частичных правил импортируются в прежнюю версию 1; оба варианта
читаются writer. Удаление/правка текущих rules управляет выводом, старые линии
из original source не возвращаются. Это форматное оформление Formats,
не общий DTO границы таблицы и не доказательство межформатной проекции.
Нативный writer воспроизводит эти объявления. Правка текста/формул в ячейке
сохраняет layout; изменение размеров таблицы требует согласовать профиль либо
явно удалить его для применения нового default layout. Неверный/будущий carrier,
подстановка TeX-команд и чрезмерное число правил дают `latex.table-profile` ERROR
без замены назначения и без DOCX bridge.

Ресурсные границы: общий source token/input budget, 64 группы и 10000 горизонтальных
линий; число сканируемых ячеек всех принятых таблиц ограничено выбранным max_nodes.
Это собственный лимит table work, не утверждение о полном бюджете каждого TeX-
преобразования. Cell parsers разделяют исходные строки, маркеры и line index;
lexer, splitter и проекция проверяют отмену в контексте прямого reader.
Source spans используют Unicode character offsets исходного текста с фактическими CR/LF.

Model → JSON → TeX использует `native-table-v1` для непустой прямоугольной таблицы
без вертикальных объединений, заданной геометрии, стилей таблицы/строк/ячеек и opaque свойств.
Ячейка в колонке `l/c/r` содержит один обычный абзац либо остаётся пустой.
В колонке `p{размер}` допустимы несколько непустых абзацев. Это также относится
к ячейкам, где `multicolumn` задаёт колонку `p`. При чтении пустая строка
или `\par` разделяет абзацы; при записи используется `\par`. Поддерживаются конечные
bold/italic/underline и текстовые индексы, экранированные специальные символы,
inline Formula LATEX. Для новой таблицы default вывод — редактируемый `tabular` с левыми колонками и сеткой;
таблица остаётся на своём месте в потоке, без floating `table` environment.
Внешние списки закрываются перед таблицей и продолжают правильный номер после неё.

Вложенные ячейки, display math, вертикальные объединения и произвольное оформление
не упрощаются этим профилем. Другие объекты сохраняют прежний DOCX bridge;
если он теряет поддерживаемые только нативно formulas/lists/scripts или активное
native table declaration, экспорт
по-прежнему отказывает. Отмена и выбранные Model limits сохраняют Model и прежний
файл назначения. Отдельных требований к Model и новых зависимостей нет.

Независимый оригинал `tabular` и два JSON-экспорта компилируются pdflatex с
`-no-shell-escape`: совпадают полные страницы в MuPDF и Poppler при 108 dpi
без масок, допуска и растровых объектов. [Доказательство](../development/latex-table-evidence.json).
Отдельная [source-приёмка](../development/latex-tabular-source-evidence.json)
проверяет четыре независимых originals через два полных TeX → Model → JSON → TeX
цикла с повторным чтением: структуру ячеек и точные полные страницы.
Частичные правила имеют [отдельную приёмку](../development/latex-cline-evidence.json):
четыре независимые таблицы и авторский эталон правки диапазона/ячейки, два полных
цикла, десять точных страниц в каждом из MuPDF/Poppler, 108 dpi без масок/допуска
или raster substitution. Ядро команды описано в
[LaTeX Project lttab.dtx](https://github.com/latex3/latex2e/blob/main/base/lttab.dtx);
исходный код TeX-движка в Formats не переносится.
Колонки `p{размер}` сохраняют заданную ширину и перенос строк внутри ячейки.
Принимаются положительные буквальные размеры в `pt`, `mm`, `cm`, `in` и `bp`
в пределах диапазона профиля; макросы и относительные размеры остаются вне него.
Оригинал с узкими колонками, несколькими абзацами в ячейках, `cline` и `multicolumn` и два экспорта через JSON
дают одинаковую страницу после компиляции pdflatex и растеризации Poppler.
Multirow, nested tabular, floats, размерные row breaks, многоабзацные ячейки
в колонках `l/c/r` и refs/labels внутри таблицы остаются вне этого профиля.
Неподдержанный внешний tabular не превращает внутренний tabular в самостоятельный принятый
объект; original bytes и расположенная opaque диагностика сохраняются.
Измеренная исходная пагинация произвольного документа и
полная assessment не заявляются; `LOSS latex-layout` остаётся.

### Горизонтальные объединения multicolumn

Полная ячейка `\multicolumn{n}{spec}{content}` использует общий
`TableCell.column_span`; n — положительное десятичное целое без знака,
а не скрытый source hint.
Текст, inline-формулы, выделения/индексы и пустые объединённые ячейки проходят
два полных source/Model/JSON/TeX цикла. Выравнивание и вертикальные линии `spec`
содержат ровно одну колонку l/c/r или p с буквальной шириной и хранятся отдельно в формате Formats:
`TableCell.properties['opendoc_formats.latex_multicolumn']` версии 1, поле `columns`.
Explicit multicolumn с n=1 сохраняется: он также может менять выравнивание/линии.
`source_span` ячейки указывает всю исходную команду; абзац/формула сохраняют
собственные адреса содержимого.

Правка общего column_span и текста имеет приоритет; источник не восстанавливает
старое n. Удаление cell carrier снимает override. Для нового объединения без carrier
writer использует выравнивание первой колонки и линии с внешних границ диапазона;
внутренние линии объединения не рисуются. Логическая ширина всех строк должна
совпадать с таблицей, а ширина каждой строки ограничена max_nodes до построения
column spec или обращения к bridge. Несогласованный общий merge даёт явный отказ.
Недопустимый/будущий/исполняемый override отклоняется без DOCX-моста и замены файла.
Макросы в n, paragraph specs, частичные команды и вертикальные объединения
остаются вне профиля. Общего TableCell API Model достаточно; новых DTO нет.

[Четыре независимых multicolumn originals](../development/latex-multicolumn-evidence.json)
подтверждают структуру и исходный рендер в двух полных циклах при 108 dpi;
приёмка ограничена указанным профилем и не подтверждает произвольный TeX layout.

Собственный parser распространяется по MIT; исходники LaTeX distribution не включены.
Полная [документация LaTeX Project](https://www.latex-project.org/help/documentation/)
описывает существенно более широкую систему, чем данный профиль.
