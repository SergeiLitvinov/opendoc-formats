# Зависимости и движки

Экспорт EPUB входит в базовый профиль: собственный writer **MIT**, модель OpenDoc
**MIT**, ZIP/XML/HTML parsing — стандартная библиотека Python (**PSF License Agreement**).
EbookLib, lxml и BeautifulSoup для записи не используются. Extra `epub` нужен для импорта;
лицензия каждого такого профиля указана ниже. Для отдельной CI-проверки подключён
[EPUBCheck](../development/epubcheck.md): BSD-3-Clause самого checker,
отдельные условия его JAR dependencies, включая MPL-2.0 Saxon-HE; в пакет не включается.

Единственная обязательная зависимость — **OpenDoc Model 0.3.0 (MIT)**: модель,
ресурсы, единицы, диагностика, JSON и валидация. Исходники приложений не используются.
Базовый пакет читает и пишет TXT/JSON без дополнительных движков.

## Прямые Python-зависимости

Версии ниже — проверенный `uv.lock`; нижние границы extras не фиксируют эти версии
при обычной установке pip. Для такого окружения нужен собственный lock и аудит.

| Пакет / версия | Extra | Назначение | Лицензия / особенность |
| --- | --- | --- | --- |
| opendoc-model 0.3.0 | обязательный | Общий контракт документа; официальный release wheel | MIT |
| pypdf 6.19.0 | pdf-text, pdf | Низкоуровневое извлечение текста и отдельные PDF-конвертеры | BSD-3-Clause |
| PyMuPDF 1.28.2 | pdf-rich, pdf; транзитивно pdf-docx | Богатый импорт, геометрия, вектор/растр, рендер и PDF writer | AGPL-3.0 или коммерческая лицензия Artifex |
| pdf2docx 0.5.13 | pdf-docx, pdf | Отдельный прямой PDF → DOCX маршрут | MIT; зависит от AGPL/commercial PyMuPDF и OpenCV; upstream помечен как не поддерживаемый активно |
| pdfplumber 0.11.10 | pdf-layout, pdf | Альтернативное извлечение текста/геометрии PDF | MIT; pdfminer.six, Pillow, pypdfium2 и их компоненты |
| python-docx 1.2.0 | docx | OOXML DOCX, rich reader/writer и DOCX → TeX | MIT; использует lxml |
| lxml 6.1.3 | docx, pptx; транзитивно epub-ebooklib/pdf | XML и OOXML | BSD-3-Clause; bundled libiconv LGPL-2.1 и другие отдельные условия |
| python-pptx 1.0.2 | pptx | Чтение/создание презентаций и отдельный HTML viewer | MIT; lxml, Pillow, XlsxWriter |
| Pillow 12.3.0 | pptx; транзитивно pdf | Обработка изображений, fallback и измерения | MIT-CMU; комплект лицензий встроенных библиотек |
| EbookLib 0.20 | epub-ebooklib | Необязательный прежний backend контейнера/OPF/spine EPUB | **AGPL-3.0-or-later**, использует lxml/six |
| beautifulsoup4 4.15.0 | html, epub, epub-ebooklib | Разбор HTML/XHTML | MIT; soupsieve/typing-extensions |
| tinycss2 1.5.1 | html | Токены и разбор статического CSS | BSD-3-Clause; webencodings |
| fonttools 4.66.1 | fonts | Метаданные шрифтов, покрытие глифов и ограничения embedding | MIT; лицензия самих шрифтов отдельно |

`pdf-text` обслуживает `readers.pdf.read_pdf`, а `read_document(...pdf)` использует
PyMuPDF и требует `pdf-rich` либо полный `pdf`. Это не взаимозаменяемые rich readers.
OCR передаётся фабрикой потребителя; OCR engine и модели не поставляются.

HTML-экспорт исходного MathML проверяет и очищает XML собственным кодом на стандартной
библиотеке Python: установка lxml для этой операции не требуется. Преобразование
OMML в MathML и OOXML-маршруты имеют отдельные требования к движкам;
это изменение не снимает XSL-вопрос с профилей, действительно устанавливающих lxml.

## Разработка и документация

| Группа | Прямые пакеты | Назначение |
| --- | --- | --- |
| dev | pytest 9.1.1 (MIT), ruff 0.16.10 (MIT), mypy 2.4.0 (MIT) | Тесты, линтинг и статическая проверка |
| dev | build 1.6.1 (MIT), twine 7.0.0 (Apache-2.0) | Сборка и проверка метаданных пакетов |
| docs | MkDocs 1.6.1 (BSD-2-Clause) | Статический сайт и локальный поиск; JavaScript поиска имеет отдельные лицензии |
| build-system | setuptools ≥77 (MIT) | Изолированный backend сборки; точная версия не зафиксирована `uv.lock` |

Транзитивные зависимости всех групп, включая platform markers, перечислены с
назначением и первичными доказательствами в [автоматическом реестре](../reference/dependencies.md).
Наличие GPL-файла в development-пакете не означает автоматического перелицензирования
всего собственного кода: нужно учитывать конкретный компонент и способ использования.

## Внешние программы

| Инструмент | Где используется | Условия |
| --- | --- | --- |
| LibreOffice | `office.convert_office_to_pdf` и отдельные converter routes | MPL-2.0, LGPLv3+ и лицензии компонентов; ставится отдельно, не включён в wheel |
| Pandoc | Отдельный DOCX → LaTeX маршрут и converters | GPL-2.0-or-later; ставится отдельно |
| DjVuLibre / djvutxt | Текст DjVu | GPL-2.0-or-later; ставится отдельно |
| Системные шрифты | PDF/DOCX/PPTX render/export | Условия конкретного font asset; проверка fsType не заменяет лицензию шрифта |

Версию и дистрибутив внешнего инструмента фиксирует потребитель/CI. Библиотека
не скачивает эти программы и не исполняет макросы документов.

## Лицензия каждого профиля

Собственный код библиотеки во всех профилях остаётся **MIT**. Extra — способ выбрать
зависимости, а не новая лицензия пакета. Таблица указывает условия выбранного состава;
полный граф и точные notices находятся в [реестре](../reference/dependencies.md).

| Профиль | Лицензии и существенные условия зависимостей | Для открытого проекта |
| --- | --- | --- |
| Базовый, TXT/JSON и EPUB writer | MIT у библиотеки и OpenDoc; PSF License Agreement стандартной библиотеки Python | Сохранить MIT/copyright; разрешены permissive и совместимые copyleft-проекты; EPUB экспорт без extras |
| Внешний EPUBCheck acceptance | MIT обёртки; BSD-3-Clause EPUBCheck; отдельные JAR notices, включая MPL-2.0 Saxon-HE; условия выбранной Java runtime | Инструмент CI/разработки, не runtime extra и не часть release assets; сохранять весь upstream distribution |
| `pdf-text` | MIT + BSD-3-Clause у pypdf | Сохранить notices; это извлечение текста, не полный rich PDF профиль |
| `pdf-rich` | MIT библиотеки; PyMuPDF AGPL-3.0 либо commercial | Чтение модели, геометрия, рендер и PDF writer. Соблюдать выбранные условия PyMuPDF; lxml и его XSL-ресурсы не устанавливаются |
| `pdf-layout` | MIT, MIT-0, BSD-3-Clause, Apache-2.0; MIT-CMU Pillow и bundled notices; PDFium BUILD_LICENSES; CC-BY-4.0 документации pypdfium2 | Извлечение через pdfplumber, не универсальный rich reader. Сохранить notices; lxml/PyMuPDF не устанавливаются |
| `pdf-docx` | MIT/BSD/Apache/PSF, 0BSD/Zlib/CC0; PyMuPDF AGPL-3.0 либо commercial; LGPL FFmpeg/libiconv и GCC runtime exception; условия lxml | Прямой PDF → DOCX; соблюдать AGPL и notices выбранного состава. XSL-исключение остаётся |
| `html` | MIT, BSD-3-Clause, PSF-2.0 | Сохранить лицензии/copyright; разрешён статический HTML импорт без AGPL-движка |
| `fonts` | MIT; права на font assets отдельно | Сохранить MIT; встраиваемые шрифты должны иметь соответствующее разрешение |
| `docx` | MIT, BSD-3-Clause, PSF/ElementTree, Zlib; LGPL-2.1 для bundled libiconv | Сохранить условия lxml и LGPL-компонента; XSL-исключение описано ниже |
| `pptx` | Условия `docx` плюс BSD-2-Clause XlsxWriter и MIT-CMU/third-party notices Pillow | Сохранить весь комплект notices; XSL-исключение остаётся |
| `pdf` | PyMuPDF AGPL-3.0 либо commercial; MIT/BSD/Apache/PSF, MIT-0, Zlib/0BSD/CC0 у остальных пакетов; LGPL FFmpeg/libiconv, GCC runtime exception; PDFium BUILD_LICENSES | При выборе AGPL распространять охватываемую объединённую программу на совместимых условиях с corresponding source. Коммерческая ветвь PyMuPDF не требуется для соблюдающего AGPL открытого проекта. XSL-исключение остаётся |
| `epub` | MIT; PSF-2.0 у typing-extensions | Собственный ZIP/OPF/spine/nav/NCX слой; BeautifulSoup/soupsieve для XHTML. Сохранить notices; lxml и EbookLib не требуются |
| `epub-ebooklib` | EbookLib AGPL-3.0-or-later; MIT/BSD/PSF и условия lxml/libiconv | Прежний backend выбирается явно. Совместимые AGPL-условия для охватываемой объединённой программы, source и notices; XSL-исключение остаётся |
| `dev` | MIT/BSD/Apache/PSF, MIT-0, MPL-2.0; docutils Public domain/BSD и GPL у отдельных tooling-файлов | Это инструменты разработки; их применение не назначает всему выходному wheel их лицензии. При распространении самого окружения учитывать все компоненты |
| `docs` | BSD-2-Clause MkDocs; MIT/BSD/Apache и MPL-2.0 зависимостей; MIT и MPL-1.1 JavaScript поиска | Для публикуемых assets сохранить headers/полные license texts и доступность MPL source; это сделано на Pages |
| build-system | MIT setuptools; версия выбирается из `>=77` при изолированной сборке | Фиксировать и проверять точный backend при распространении сборочного окружения |
| Все extras вместе | Объединение перечисленных условий, включая AGPL и XSL-исключение | Не обозначать весь комплект только MIT; применять требования фактически используемых/распространяемых компонентов |

**XSL-исключение:** `RNG2Schtrn.xsl` и `XSD2Schtrn.xsl` в lxml 6.1.3 не имеют
подтверждённого разрешения на распространение. Общая BSD-лицензия lxml прямо выделяет
их как исключение. Они входят в установленный lxml wheel, но не используются и не
копируются в wheel OpenDoc Formats. Открытость проекта не устраняет эту неопределённость;
перед включением полного lxml в готовую сборку решить [OF16](../development/todo.md).
Подробные доказательства: [статус XSL](../development/lxml-xslt.md).

## Совместимость открытых проектов

Цель библиотеки — использование в открытых проектах, в том числе в экосистеме okidoki.
**AGPL — свободная лицензия; её наличие само по себе не является дефектом зависимости.**
Открытые проекты могут использовать PDF/EPUB, соблюдая её условия. При этом ярлыка
«open source» недостаточно: GPL-2.0-only, собственная permissive лицензия и AGPL-3.0
дают разные условия для объединённой программы.

MIT позволяет включать собственный код в совместимую AGPL-сборку с сохранением MIT
уведомлений. Это не требует автоматически менять лицензию всех самостоятельно
распространяемых исходников библиотеки. При распространении охватываемой AGPL
программы нужны corresponding source, права получателей и лицензии компонентов;
для модифицированной версии с удалённым сетевым взаимодействием применяется §13.
Само размещение кода на GitHub и установка движка отдельно не заменяют эти требования.
Первичный текст: [AGPL-3.0](https://raw.githubusercontent.com/aerkalov/ebooklib/master/LICENSE.txt).

Направление развития зависимости — выбор совместимых открытых движков, устранение
неясных прав и уменьшение лишнего состава установки. Переписывание AGPL-движков
только из-за copyleft не является обязательной задачей. Конкретные пункты —
[TODO](../development/todo.md).

## EPUB без лишнего движка

`epub` использует собственный контейнер стандартной библиотеки. Он сохраняет порядок
spine, метаданные title/language/identifier, оглавление EPUB 3 nav и EPUB 2 NCX,
исходные XHTML/CSS и изображения. Archive safety, проверки локальных путей и XML
исключают выход за архив, сетевые обращения и объявления сущностей.
Существующий профиль XHTML/CSS не расширяется этим изменением: таблицы, MathML,
nonlinear content и полный fixed layout остаются задачами OF08.

Прежний маршрут доступен после установки `epub-ebooklib`:
`read_epub_model(path, backend="ebooklib")` и `read_epub(path, backend="ebooklib")`.
По умолчанию и в `read_document` используется `backend="native"`.

## Минимальные PDF-профили

| Задача | Профиль | Публичный маршрут |
| --- | --- | --- |
| Текст через pypdf | `pdf-text` | `readers.pdf.read_pdf` |
| Модель, геометрия, рендер, PDF export | `pdf-rich` | `read_document`, `PdfDocument`, `read_pdf_geometry`, `write_document` |
| Текст/геометрия через pdfplumber | `pdf-layout` | `readers.pdf.read_pdf` |
| Прямой PDF → DOCX | `pdf-docx` | `Pdf2DocxConverter` |
| PDF → DOCX через PyMuPDF | `pdf-rich` + `docx` | `PyMuPdfConverter` |
| Все прежние PDF-движки | `pdf` | Совместимый полный состав |

`read_pdf` выбирает доступный маршрут в порядке pdfplumber → pypdf → PyMuPDF.
`read_document` для PDF требует PyMuPDF и явно сообщает отсутствие backend;
установка `pdf-layout` или `pdf-text` не делает их равнозначными rich reader.
Разделение не меняет алгоритмы и качество выбранного движка. Конечный профиль
нативного векторного экспорта описан в [руководстве](formats.md#векторные-ресурсы-pdf);
остальные пробелы спецификации остаются отдельными задачами в TODO.
Изолированные проверки профилей в CI используют constraints из `uv.lock`, чтобы
состав установки соответствовал проверенному лицензионному реестру.
