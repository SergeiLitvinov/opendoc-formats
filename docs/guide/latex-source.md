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
вид и уровень списка. Reader использует ListItem из Model 0.17.0:
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
с обычными абзацами, заголовками 1–5, списками, TeX-формулами и прямым bold/italic/underline,
без произвольных стилей, ссылок, геометрии, шрифтов и других объектов. Текст должен содержать одиночные
пробелы без начальных/конечных пробелов: TeX иначе меняет whitespace.
Все спецсимволы экранируются; `[ ]` не становятся display-math delimiters,
текст `\input{...}` не становится командой. Преамбула фиксирована; TeX не запускается.
Два публичных JSON/TeX цикла сохраняют текст и выделение. Произвольная компоновка
не объявляется сохранённой (`LOSS latex-layout`, assessment неполная);
независимые конечные корпуса списков и формул описаны ниже.

Reader связывает заголовки с официальным `Heading` из OpenDoc. Writer использует
`get_heading`, не выводит роль из имени стиля. Уровни 1–5 соответствуют
section/subsection/subsubsection/paragraph/subparagraph; исходная звёздочка
сохраняет нумерованный или ненумерованный вариант. Общий Heading без исходной
декларации записывается со звёздочкой, чтобы не добавлять нумерацию по догадке.
Пустые служебные стили source reader допускаются, произвольный визуальный
каскад — нет. Правка и удаление через `set_heading` управляют результатом:
устаревшие `latex_heading_level` и `Heading N` не возвращают удалённый заголовок.
Короткий optional title получает located opaque диагностику; chapter и уровни
6–9 остаются вне нативной приёмки и используют bridge.

В заголовках 1–5 поддержан inline Formula LATEX: выражение и fallback проходят
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

Собственный parser распространяется по MIT; исходники LaTeX distribution не включены.
Полная [документация LaTeX Project](https://www.latex-project.org/help/documentation/)
описывает существенно более широкую систему, чем данный профиль.
