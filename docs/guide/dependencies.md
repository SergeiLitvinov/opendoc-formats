# Зависимости и движки

Единственная обязательная зависимость — **OpenDoc 0.1.0 (MIT)**: модель,
ресурсы, единицы, диагностика, JSON и валидация. Исходники приложений не используются.
Базовый пакет читает и пишет TXT/JSON без дополнительных движков.

## Прямые Python-зависимости

Версии ниже — проверенный `uv.lock`; нижние границы extras не фиксируют эти версии
при обычной установке pip. Для такого окружения нужен собственный lock и аудит.

| Пакет / версия | Extra | Назначение | Лицензия / особенность |
| --- | --- | --- | --- |
| opendoc 0.1.0 | обязательный | Общий контракт документа; официальный release wheel | MIT |
| pypdf 6.19.0 | pdf-text, pdf | Низкоуровневое извлечение текста и отдельные PDF-конвертеры | BSD-3-Clause |
| PyMuPDF 1.28.2 | pdf | Богатый импорт, геометрия, вектор/растр, рендер и PDF writer | AGPL-3.0 или коммерческая лицензия Artifex |
| pdf2docx 0.5.13 | pdf | Отдельный прямой PDF → DOCX маршрут | MIT; зависит от AGPL/commercial PyMuPDF и OpenCV; upstream помечен как не поддерживаемый активно |
| pdfplumber 0.11.10 | pdf | Альтернативный анализ таблиц/геометрии в PDF → DOCX | MIT; pdfminer.six, Pillow, pypdfium2 и их компоненты |
| python-docx 1.2.0 | docx | OOXML DOCX, rich reader/writer и DOCX → TeX | MIT; использует lxml |
| lxml 6.1.3 | docx, pptx; транзитивно epub/pdf | XML и OOXML | BSD-3-Clause; bundled libiconv LGPL-2.1 и другие отдельные условия |
| python-pptx 1.0.2 | pptx | Чтение/создание презентаций и отдельный HTML viewer | MIT; lxml, Pillow, XlsxWriter |
| Pillow 12.3.0 | pptx; транзитивно pdf | Обработка изображений, fallback и измерения | MIT-CMU; комплект лицензий встроенных библиотек |
| EbookLib 0.20 | epub | Чтение контейнера/OPF/spine EPUB | **AGPL-3.0-or-later**, использует lxml/six |
| beautifulsoup4 4.15.0 | html, epub | Разбор HTML/XHTML | MIT; soupsieve/typing-extensions |
| tinycss2 1.5.1 | html | Токены и разбор статического CSS | BSD-3-Clause; webencodings |
| fonttools 4.66.1 | fonts | Метаданные шрифтов, покрытие глифов и ограничения embedding | MIT; лицензия самих шрифтов отдельно |

`pdf-text` обслуживает `readers.pdf.read_pdf`, а `read_document(...pdf)` использует
PyMuPDF и требует полный профиль. Это не взаимозаменяемые rich readers.
OCR передаётся фабрикой потребителя; OCR engine и модели не поставляются.

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

## Профили выбора

- TXT/JSON + OpenDoc: обязательный MIT-контракт.
- HTML, fonts, pdf-text: без обязательного AGPL-движка по текущему графу.
- DOCX/PPTX: без обязательного AGPL, но с native/bundled условиями lxml/Pillow.
- Полный PDF: AGPL/commercial PyMuPDF, также через pdf2docx.
- EPUB: AGPL EbookLib.

Ленивый импорт и установка extra не отменяют условий copyleft.
Распространение приложения с движками, модификации и сетевое использование требуют
выбора совместимого лицензионного профиля: [подробный аудит](../development/licenses.md).
