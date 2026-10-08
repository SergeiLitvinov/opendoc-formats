# Проверка EPUB

Собственный EPUB writer не зависит от Java или EPUBCheck. Для приёмки в CI
используется отдельный внешний инструмент: [EPUBCheck 5.4.0](https://github.com/w3c/epubcheck/releases/tag/v5.4.0).
`tools.epubcheck` создаёт два собственных fixture: обычную книгу и книгу с двумя
главами, таблицей, списком, MathML, SVG и ссылками между главами.

## Воспроизводимый запуск

```sh
mkdir -p .opendoc-formats
curl --fail --location --connect-timeout 15 --max-time 180 https://github.com/w3c/epubcheck/releases/download/v5.4.0/epubcheck-5.4.0.zip --output .opendoc-formats/epubcheck.zip
uv run --frozen python -m tools.epubcheck --archive .opendoc-formats/epubcheck.zip
```

Java выбирается из PATH или явно через `--java`. Проверка не устанавливает runtime
и не добавляет Python-зависимостей. SHA-256 официального архива проверяется перед
распаковкой и выполнением:

```text
33350c61038e71dfb3d45a76aed04bf5481e6d5500cb780f6e98db8bbd15a28c
```

Архив ограничен 64 MiB и проходит общий контроль archive paths/entries/size/ratio.
Java запускается без shell, с heap limit 256 MiB и timeout 60 секунд на книгу;
`--failonwarnings` делает ошибки и предупреждения причиной отказа acceptance.
при timeout дочерний процесс завершается. Временная распаковка удаляется после проверки.
Проверяются только наши сгенерированные fixtures, не произвольный внешний документ.
Этот инструмент не является sandbox для JVM. В CI он запускается на Linux/Python 3.12
и входит в acceptance выпуска.

EPUBCheck 5.4.0 сообщает использование правил EPUB 3.4. Оба fixture проходят без
ошибок и предупреждений; это свидетельство для указанного профиля, а не проверка
всех возможных объектов или одинакового отображения в reading systems.

## Лицензионный профиль внешней проверки

Обёртка `tools.epubcheck` — **MIT**. EPUBCheck — **BSD-3-Clause**: проверен
`LICENSE.txt` в официальном архиве с указанным digest. Бинарный ZIP содержит также
отдельные Java-библиотеки; лицензия BSD EPUBCheck не заменяет их условия.
Например, Saxon-HE 11.4 использует [MPL-2.0](https://www.saxonica.com/html/license/terms.html),
Jing 20181222 — [BSD-3-Clause](https://github.com/relaxng/jing-trang/blob/master/copying.txt),
Apache Commons/Jackson имеют Apache-2.0 notices, ICU4J 77.1 декларирует Unicode-3.0
во встроенном Maven POM. JAR notices/дополнительные LICENSE внутри дистрибутива
сохраняются при распаковке; полный независимый аудит всего Java-графа здесь не заявляется.

Java runtime имеет собственные условия поставщика. EPUBCheck, его JAR-библиотеки
и Java не включены в wheel/sdist OpenDoc Formats или release assets. Для локальной/CI
проверки используется неизменённый официальный ZIP. Распространение отдельного набора
с Java/JAR требует сохранения всех notices и выполнения соответствующих условий;
он не должен обозначаться как набор только MIT/BSD-компонентов.
