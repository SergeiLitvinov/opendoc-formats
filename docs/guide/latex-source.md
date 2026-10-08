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
вид и уровень списка; точная нумерация не вычисляется TeX engine.

Inline `$...$` и `\(...\)`, display `$$...$$` и `\[...\]` становятся
`Formula(format=LATEX)`. Значение — исходный TeX между delimiters; оно не исполняется
и не преобразуется в MathML. Labels становятся anchors, `ref` — внутренней ссылкой.
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
Экспорт LaTeX пока использует существующий DOCX bridge и требует extra `docx`;
семантический source → JSON → TeX roundtrip ещё не заявляется.

Незакрытые группы, math delimiters и mismatched environments дают
`InvalidDocumentError`; превышение профиля — `ResourceLimitError`, отмена —
`OperationCancelledError`. Reader failures остаются исключениями по общему контракту
реестра. Отмена до вызова reader даёт стандартный `import.cancelled`.

Собственный parser распространяется по MIT; исходники LaTeX distribution не включены.
Полная [документация LaTeX Project](https://www.latex-project.org/help/documentation/)
описывает существенно более широкую систему, чем данный профиль.
