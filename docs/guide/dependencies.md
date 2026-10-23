# Зависимости и движки

**Стандартный PDF-профиль — один движок PyMuPDF.** Установка `opendoc-formats[pdf]`
покрывает модель, геометрию, таблицы, рендер и PDF writer; `pdf-rich` — эквивалентный
профиль. В него не входят pypdf, pdfplumber, pdf2docx, OpenCV, NumPy, PDFium,
pdfminer, Pillow или lxml. Лицензия PyMuPDF — AGPL-3.0 либо коммерческая;
для отдельного permissive text-only маршрута остаётся `pdf-text` с BSD-3-Clause pypdf.
Таблица ниже перечисляет все альтернативные профили, а не обязательную общую установку.

Для [JSON → DOCX flow](../development/pdf-word-flow-contract.md) достаточно `docx`
(python-docx: MIT, lxml: BSD-3-Clause с дополнительными notices дистрибутива);
`fonts` добавляет fonttools (MIT) для программ шрифтов. Самому flow-экспорту
PyMuPDF, pdf2docx, OpenCV и Pillow не нужны. Первоначальный разбор PDF использует
отдельный PDF-профиль с его лицензией; экспорт JSON не меняет условий этого движка.

Профили `pdf`, `pdf-rich` и `pdf-docx` ограничивают PyMuPDF веткой `>=1.24,<2`.
В [метаданных PyMuPDF 2.0](https://pypi.org/pypi/PyMuPDF/2.0/json) обязательны
NumPy, ONNX Runtime, networkx, PyYAML, pymupdf-layout, pymupdf4llm, psutil и tabulate.
Эти движки не используются адаптером и не входят в проверенный минимальный
PDF-профиль. Переход на major 2 требует отдельной проверки API, качества и лицензий.

Экспорт EPUB входит в базовый профиль: собственный writer **MIT**, модель OpenDoc
**MIT**, ZIP/XML/HTML parsing — стандартная библиотека Python (**PSF License Agreement**).
EbookLib, lxml и BeautifulSoup для записи не используются. Extra `epub` нужен для импорта;
лицензия каждого такого профиля указана ниже. Для отдельной CI-проверки подключён
[EPUBCheck](../development/epubcheck.md): BSD-3-Clause самого checker,
отдельные условия его JAR dependencies, включая MPL-2.0 Saxon-HE; в пакет не включается.

Единственная обязательная зависимость — **OpenDoc Model 0.18.0 (MIT)**: модель,
ресурсы, единицы, диагностика, JSON и валидация. Исходники приложений не используются.
Базовый пакет читает и пишет TXT/JSON, читает конечный LaTeX source profile,
пишет TeX с заголовками, структурными списками, текстовыми индексами и TeX-формулами и EPUB без дополнительных
движков. Собственные LaTeX parser/writer — MIT; стандартная библиотека Python
имеет PSF License Agreement. LaTeX distribution не включается. Таблицы
и другие объекты вне текстового TeX-профиля используют прежний DOCX bridge с extra
`docx`. Списки, текстовые индексы и формулы вне нативного профиля отклоняются:
bridge не сохраняет их структуру.
lxml для нативного текстового экспорта со списками не требуется.

## Прямые Python-зависимости

Версии ниже — проверенный `uv.lock`; нижние границы extras не фиксируют эти версии
при обычной установке pip. Для такого окружения нужен собственный lock и аудит.

| Пакет / версия | Extra | Назначение | Лицензия / особенность |
| --- | --- | --- | --- |
| opendoc-model 0.18.0 | обязательный | Общий контракт документа; официальный release wheel | MIT |
| pypdf 6.19.0 | pdf-text | Альтернативное извлечение текста | BSD-3-Clause |
| PyMuPDF 1.28.2 | pdf-rich, pdf, pdf-docx | Богатый импорт, геометрия, вектор/растр, рендер и PDF writer | AGPL-3.0 или коммерческая лицензия Artifex |
| pdf2docx 0.5.13 | pdf-docx | Отдельный прямой PDF → DOCX маршрут | MIT; зависит от AGPL/commercial PyMuPDF и OpenCV; upstream помечен как не поддерживаемый активно |
| pdfplumber 0.11.10 | pdf-layout | Альтернативное извлечение текста/геометрии PDF | MIT; pdfminer.six, Pillow, pypdfium2 и их компоненты |
| python-docx 1.2.0 | docx | OOXML DOCX, rich reader/writer и DOCX → TeX | MIT; использует lxml |
| lxml 6.1.3 | docx, pptx; транзитивно pdf-docx | XML и OOXML | BSD-3-Clause; bundled libiconv LGPL-2.1 и другие отдельные условия |
| python-pptx 1.0.2 | pptx | Чтение/создание презентаций и отдельный HTML viewer | MIT; lxml, Pillow, XlsxWriter |
| Pillow 12.3.0 | pptx; транзитивно pdf-layout | Обработка изображений, fallback и измерения | MIT-CMU; комплект лицензий встроенных библиотек |
| beautifulsoup4 4.15.0 | html, epub | Разбор HTML/XHTML | MIT; soupsieve/typing-extensions |
| tinycss2 1.5.1 | html | Токены и разбор статического CSS | BSD-3-Clause; webencodings |
| fonttools 4.66.1 | fonts | Метаданные шрифтов, покрытие глифов и ограничения embedding | MIT; лицензия самих шрифтов отдельно |

`pdf-text` обслуживает `readers.pdf.read_pdf`, а `read_document(...pdf)` использует
PyMuPDF и требует `pdf` либо `pdf-rich`. Это не взаимозаменяемые rich readers.
OCR передаётся фабрикой потребителя; OCR engine и модели не поставляются.

HTML-экспорт исходного MathML проверяет и очищает XML собственным кодом на стандартной
библиотеке Python: установка lxml для этой операции не требуется. Преобразование
OMML в MathML и OOXML-маршруты имеют отдельные требования к движкам;
это изменение не снимает XSL-вопрос с профилей, действительно устанавливающих lxml.

## Разработка и документация

| Группа | Прямые пакеты | Назначение |
| --- | --- | --- |
| dev | pytest 9.1.1 (MIT), ruff 0.16.10 (MIT), mypy 2.4.0 (MIT) | Тесты, линтинг и статическая проверка |
| dev | twine 7.0.0 (Apache-2.0) | Проверка метаданных пакетов; сборку wheel/sdist выполняет `uv build` через изолированный setuptools backend |
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
| Базовый, TXT/JSON, LaTeX reader/text writer и EPUB writer | MIT у библиотеки и OpenDoc; PSF License Agreement стандартной библиотеки Python | Сохранить MIT/copyright; разрешены permissive и совместимые copyleft-проекты; текстовый TeX и EPUB экспорт без extras |
| Внешний EPUBCheck acceptance | MIT обёртки; BSD-3-Clause EPUBCheck; отдельные JAR notices, включая MPL-2.0 Saxon-HE; условия выбранной Java runtime | Инструмент CI/разработки, не runtime extra и не часть release assets; сохранять весь upstream distribution |
| `pdf-text` | MIT + BSD-3-Clause у pypdf | Сохранить notices; это извлечение текста, не полный rich PDF профиль |
| `pdf`, `pdf-rich` | MIT библиотеки; PyMuPDF AGPL-3.0 либо commercial | Чтение модели, геометрия, рендер и PDF writer. Соблюдать выбранные условия PyMuPDF; lxml и его XSL-ресурсы не устанавливаются |
| `pdf-layout` | MIT, MIT-0, BSD-3-Clause, Apache-2.0; MIT-CMU Pillow и bundled notices; PDFium BUILD_LICENSES; CC-BY-4.0 документации pypdfium2 | Извлечение через pdfplumber, не универсальный rich reader. Сохранить notices; lxml/PyMuPDF не устанавливаются |
| `pdf-docx` | MIT/BSD/Apache/PSF, 0BSD/Zlib/CC0; PyMuPDF AGPL-3.0 либо commercial; LGPL FFmpeg/libiconv и GCC runtime exception; условия lxml | Прямой PDF → DOCX; соблюдать AGPL и notices выбранного состава. XSL-исключение остаётся |
| `html` | MIT, BSD-3-Clause, PSF-2.0 | Сохранить лицензии/copyright; разрешён статический HTML импорт без AGPL-движка |
| `fonts` | MIT; права на font assets отдельно | Сохранить MIT; встраиваемые шрифты должны иметь соответствующее разрешение |
| `docx` | MIT, BSD-3-Clause, PSF/ElementTree, Zlib; LGPL-2.1 для bundled libiconv | Сохранить условия lxml и LGPL-компонента; XSL-исключение описано ниже |
| `pptx` | Условия `docx` плюс BSD-2-Clause XlsxWriter и MIT-CMU/third-party notices Pillow | Сохранить весь комплект notices; XSL-исключение остаётся |
| `epub` | MIT; PSF-2.0 у typing-extensions | Собственный ZIP/OPF/spine/nav/NCX слой; BeautifulSoup/soupsieve для XHTML. Сохранить notices; lxml и EbookLib не требуются |
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
Первичный текст: [AGPL-3.0](https://www.gnu.org/licenses/agpl-3.0.html).

Направление развития зависимости — выбор совместимых открытых движков, устранение
неясных прав и уменьшение лишнего состава установки. Переписывание AGPL-движков
только из-за copyleft не является обязательной задачей. Конкретные пункты —
[TODO](../development/todo.md).

## EPUB без лишнего движка

`epub` использует собственный контейнер стандартной библиотеки. Он сохраняет порядок
spine, метаданные title/language/identifier, оглавление EPUB 3 nav и EPUB 2 NCX,
исходные XHTML/CSS и изображения. Archive safety, проверки локальных путей и XML
исключают выход за архив, сетевые обращения и объявления сущностей.
Таблицы и MathML имеют конечный семантический профиль; nonlinear главы включаются
явно. Полнота XHTML/CSS и fixed layout остаётся задачей OF08.

Для импорта устанавливается только `opendoc-formats[epub]`. Контейнер разбирается
собственным кодом, XHTML — BeautifulSoup; EbookLib не входит ни в один профиль.
Используется `backend="native"`. При переходе с версии 0.37 замените установку
`epub-ebooklib` на `epub` и удалите `backend="ebooklib"` из вызовов: прежнее значение
даёт явную ошибку с инструкцией. Формат модели и стандартный маршрут не меняются.

## Минимальные PDF-профили

| Задача | Профиль | Публичный маршрут |
| --- | --- | --- |
| Текст через pypdf | `pdf-text` | `readers.pdf.read_pdf` |
| Модель, геометрия, рендер, PDF export | `pdf` или `pdf-rich` | `read_document`, `PdfDocument`, `read_pdf_geometry`, `write_document` |
| Текст/геометрия через pdfplumber | `pdf-layout` | `readers.pdf.read_pdf` |
| Прямой PDF → DOCX | `pdf-docx` | `Pdf2DocxConverter` |
| PDF → DOCX через PyMuPDF | `pdf-rich` + `docx` | `PyMuPdfConverter` |
| Все альтернативные PDF-маршруты | `pdf,pdf-text,pdf-layout,pdf-docx` | Явный состав extras |

`read_pdf` выбирает установленный маршрут в порядке pdfplumber → pypdf → PyMuPDF;
отсутствующие альтернативы пропускаются. `validate_pdf` и `get_pdf_info` используют
собственный небольшой слой выбора доступного движка: дополнительный pypdf для
`pdf`/`pdf-rich` или `pdf-layout` не нужен. Извлечение Unicode Info полей и отказ
для зашифрованных/повреждённых источников проверены для каждого отдельного движка.

Прямой `Pdf2DocxConverter` требует `pdf-docx`; табличный альтернативный reader —
`pdf-layout`; текстовый pypdf reader — `pdf-text`. Если нужны все альтернативы,
они выбираются явно: `opendoc-formats[pdf,pdf-text,pdf-layout,pdf-docx]`.
`read_document` для PDF требует PyMuPDF и явно сообщает отсутствие backend;
установка `pdf-layout` или `pdf-text` не делает их равнозначными rich reader.
Разделение не меняет алгоритмы и качество выбранного движка. Конечный профиль
нативного векторного экспорта описан в [руководстве](formats.md#векторные-ресурсы-pdf);
остальные пробелы спецификации остаются отдельными задачами в TODO.
Изолированные проверки профилей в CI используют constraints из `uv.lock`, чтобы
состав установки соответствовал проверенному лицензионному реестру.

Нативная PDF-инспекция (`support.inspection.inspect_path`) использует только
`pdf-rich`: проверку шифрования выполняет PyMuPDF, имена AcroForm обходит
собственный ограниченный код. pypdf здесь не импортируется. Он остаётся
полноценным независимым движком профиля `pdf-text`, поэтому удалять пакет из
этого профиля без замены самого извлечения текста нельзя.

## Для чего нужны оставшиеся зависимости

| Зависимость | Использование в библиотеке | Условие замены |
| --- | --- | --- |
| BeautifulSoup | Структурный HTML и XHTML EPUB, обход смешанного содержимого | Равноценный разбор документов и сохранение порядка/диагностики; это не пара utility functions |
| tinycss2 | CSS rules/declarations, selectors и значения цвета | Замена одного color helper не устраняет зависимость CSS parser |
| python-docx и lxml | Нативное OOXML, relationships, стили, drawings и пакет DOCX | Полная приёмка нужного OOXML-профиля; спорные XSL-ресурсы рассматриваются отдельно в OF16 |
| python-pptx и Pillow | Пакет/объекты презентаций; WMF/EMF → PNG в HTML viewer | Сохранение форматов/визуального результата; Pillow также требуется самому python-pptx, удаление одной прямой строки не убирает его из установки |
| fontTools | Имена, cmap, font permissions/metrics, GSUB/ToUnicode и реальное subsetting | Сохранение покрытия шрифтов, glyph mappings и результата subsetting; это не только чтение пары чисел |
| PyMuPDF | PDF text/layout/graphics, изображения, формы и рендер | Сопоставимая полнота PDF и независимый визуальный корпус; регулярные выражения такой заменой не являются |
| pypdf, pdfplumber, pdf2docx | Отдельные text/layout/converter профили | Приёмка соответствующего маршрута; permissive pdf-text сохраняет отдельные условия лицензии |

Таблица описывает реальные вызовы в readers, writers, fonts и PPTX HTML viewer.
Небольшие вспомогательные слои отделены от полноценных движков; удаление зависимости
проверяется установленным минимальным профилем. Открытые замены и лицензионные
вопросы находятся только в [TODO](../development/todo.md).
