# Статус XSL-ресурсов lxml

## Результат проверки

Для зафиксированного **lxml 6.1.3** разрешение на распространение
`RNG2Schtrn.xsl` и `XSD2Schtrn.xsl` **не подтверждено**. Это проверенный открытый
лицензионный вопрос, а не AGPL/LGPL-ограничение и не назначенная нами новая лицензия.
В собственный wheel OpenDoc Formats эти файлы не входят.

| Ресурс | Что установлено | Статус |
| --- | --- | --- |
| `RNG2Schtrn.xsl` | Заголовок отмечает Eddie Robertsson и Holger Joukl; содержит attribution, но не разрешение use/copy/modify/distribute | Нет explicit license grant в проверенном исходнике |
| `XSD2Schtrn.xsl` | Заголовок отмечает исходную работу Eddie Robertsson, изменения с инициалами `fn` и Holger Joukl; разрешения нет | Нет explicit license grant в проверенном исходнике |
| Upstream `LICENSES.txt` | Прямо выделяет обе extraction transformations как unlicensed exceptions к общей BSD-лицензии | BSD-3-Clause всего lxml не подставляется вместо отсутствующего разрешения этих файлов |
| Установленный Windows x64 wheel | Оба файла присутствуют; совпадение с исходниками выпуска после нормализации CRLF/LF | Поставка полного wheel включает их независимо от использования |
| Исходники OpenDoc Formats | Нет обращения к `lxml.isoschematron`, этим файлам или Schematron API | Нужен XML/OOXML parser, а не этот необязательный функционал lxml |

Первичные источники выпуска:
[LICENSES.txt](https://raw.githubusercontent.com/lxml/lxml/lxml-6.1.3/LICENSES.txt),
[RNG2Schtrn.xsl](https://raw.githubusercontent.com/lxml/lxml/lxml-6.1.3/src/lxml/isoschematron/resources/xsl/RNG2Schtrn.xsl),
[XSD2Schtrn.xsl](https://raw.githubusercontent.com/lxml/lxml/lxml-6.1.3/src/lxml/isoschematron/resources/xsl/XSD2Schtrn.xsl).
Контрольные суммы исходников и установленных ресурсов:
[машиночитаемые доказательства](lxml-xslt-evidence.json).

Проверка GitHub issues/PRs lxml по обоим именам и истории исходника не выявила
публичного разрешения правообладателей. Это результат поиска, а не доказательство,
что никакого разрешения нигде не существует. В актуальном upstream notice также
сохранено указание unlicensed. Для снятия вопроса требуется проверяемый grant
с охватом этих файлов и необходимых прав.

## Какие разрешения не подходят

MIT-лицензия [Schematron skeleton](https://github.com/Schematron/schematron/blob/master/LICENSE)
относится к своему исходному комплекту. Его опубликованное дерево не содержит
этих двух extraction stylesheets; автоматически переносить эту MIT-лицензию на
них оснований нет. XML-схема ISO Schematron и эти XSL также являются разными ресурсами.
Нельзя считать unlicensed синонимом public domain, BSD или MIT.
Общее правило отсутствия лицензии разъясняет
[документация GitHub](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/licensing-a-repository).

## Значение для открытых проектов

Собственный код библиотеки — MIT. Открытые PDF/EPUB-проекты могут выбрать
AGPL-профиль и выполнить copyleft-обязательства; это предусмотренное использование.
Отсутствующий grant у отдельного ресурса — иной вопрос: публикация исходников
или выбор AGPL не создают права на чужой файл.

Затронуты установки `docx`, `pptx`, `epub-ebooklib`, `pdf-docx`, `pdf`, где lxml установлен прямо либо
транзитивно. Базовая модель, `pdf-text`, `pdf-rich`, `pdf-layout`, `html`, `epub` и `fonts` по проверенному графу не
требуют lxml. Раздельная установка не устраняет вопрос прав у фактически
распространяемого lxml; отсутствие вызова XSL не означает разрешения его копирования.

## Действие

[OF16](todo.md) требует получить explicit grant либо выбрать/собрать проверенный
дистрибутив без ненужных спорных ресурсов. Такую сборку нужно обозначать как
изменённую, фиксировать её hash, сохранить все остальные notices и проверить
DOCX/PPTX/EPUB/PDF маршруты. Не изменять установленный lxml пользователя и не удалять
его файлы при импорте библиотеки. Свой оригинальный XML-код и backend остаются
доступными; замена всего lxml не требуется без отдельного обоснования.

До выполнения OF16 статус сохраняется **unresolved-license-grant**; задача не
закрывается фактом успешных тестов или распространённости lxml в дистрибутивах.
Текущая документация раскрывает границу, но не выдаёт юридическое разрешение
за правообладателей. Контакт с ними — отдельное внешнее действие по разрешению пользователя.
