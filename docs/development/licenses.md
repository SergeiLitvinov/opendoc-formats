# Лицензионный аудит

## Заключение

Собственный код OpenDoc Formats распространяется по MIT, правообладатель —
Sergei Litvinov; права на перенесённые обработчики подтверждены автором.
Единственная обязательная зависимость — OpenDoc Model 0.3.0, тоже MIT.
Импортов приложений, соседних исходников или копии модели нет.

Библиотека предназначена для открытых проектов. AGPL, LGPL и MPL — свободные
лицензии; copyleft не является дефектом зависимости. **Установка всех extras имеет
смешанные условия, а не только MIT.** Условия конкретного состава и способа
распространения перечислены для [каждого профиля](../guide/dependencies.md#лицензия-каждого-профиля).

## Что проверено

- Все 81 записи зависимостей `uv.lock`, включая обе платформенные версии NumPy,
  обязательные, optional, development и docs-профили.
- Метаданные точных выпусков с PyPI и официальный wheel OpenDoc с проверкой SHA-256.
- LICENSE/COPYING/NOTICE в выбранных universal и Windows/Linux x64 wheels;
  контрольные суммы каждого прочитанного лицензионного файла и URL архивов.
- Собственные Python/Lua/CSS/JS/SVG, тема документации, тестовые документы,
  сторонние assets локального поиска и внешние программы.
- Отсутствие поставляемых TTF/OTF и внешних пользовательских документов;
  fixtures создаются проектом. Тестовый PDF с текстом ссылается на невстроенный
  Helvetica; остальные сохранённые PDF-fixtures не содержат встроенных шрифтов.

Проверяемые данные — [JSON-снимок](dependency-licenses.json), читаемый
[автоматический реестр](../reference/dependencies.md), назначение движков —
[руководство](../guide/dependencies.md). SHA lockfile вычисляется после нормализации
CRLF/LF, чтобы CI Windows/Linux сравнивал одинаковое содержание.

В больших wheels прочитаны отдельные ZIP members через HTTP Range;
полный hash архива взят из lockfile, а не пересчитан. Для небольших wheels проверен
весь архив. Не проверены все CPU/OS-варианты и каждый linked binary symbol;
лицензионный комплект upstream не является доказательством состава любой будущей сборки.

## Условия, влияющие на выбор профиля

| Компонент | Вывод |
| --- | --- |
| PyMuPDF / MuPDF | AGPL-3.0 либо отдельная коммерческая лицензия Artifex. Распространение связанного продукта и сетевые сценарии оцениваются по условиям выбранной лицензии; lazy import не снимает их |
| EbookLib | AGPL-3.0-or-later; `epub` нельзя представлять как профиль только MIT. Для распространения совместной программы требуется соблюдение AGPL; модифицированная сетевая версия имеет требование предоставления corresponding source |
| pdf2docx | Его MIT не отменяет AGPL/commercial у обязательного PyMuPDF. Транзитивно использует OpenCV/NumPy/python-docx; upstream указывает отсутствие активного сопровождения |
| lxml wheel | BSD-3-Clause/PSF/ElementTree плюс bundled MIT/zlib/libiconv LGPL-2.1. Для `RNG2Schtrn.xsl`/`XSD2Schtrn.xsl` подтверждено отсутствие explicit license grant: это отдельное исключение, не BSD и не public domain. Подробности и действие — в [статусе XSL](lxml-xslt.md), задача OF16 |
| OpenCV wheel | MIT у Python-обёртки, Apache-2.0 у OpenCV; `LICENSE-3RD-PARTY.txt` перечисляет FFmpeg LGPL и остальные условия. Headless не означает отсутствие таких компонентов |
| NumPy wheel | Смешанные permissive лицензии, BLAS и GPL-3.0-or-later WITH GCC-exception-3.1 у runtime. Исключение существенно; обычный ярлык «GPL» или «BSD» недостаточен |
| Pillow | MIT-CMU и длинный комплект third-party notices; некоторые уведомления относятся к отдельным утилитам/вариантам сборки. Проверяется фактический wheel, а не только Python-обёртка |
| pypdfium2 | Apache-2.0 OR BSD-3-Clause у bindings, PDFium и многочисленные BUILD_LICENSES; CC-BY-4.0 для документации. Все эти условия не заменяются лицензией bindings |
| cryptography | Apache-2.0 OR BSD-3-Clause; условия bundled криптографического runtime проверяются для фактического дистрибутива |
| certifi, pathspec | MPL-2.0; certifi используется tooling HTTP, pathspec — mypy, не базовой моделью документа |
| docutils | Public domain с BSD-исключениями и GPL-3.0-or-later у отдельных редакторских/tooling-файлов; транзитивный dev-пакет, не parser runtime библиотеки |

Первичные источники: [PyMuPDF](https://pymupdf.io/licensing),
[EbookLib 0.20](https://pypi.org/pypi/EbookLib/0.20/json),
[AGPL EbookLib](https://raw.githubusercontent.com/aerkalov/ebooklib/master/LICENSE.txt),
[pdf2docx 0.5.13](https://pypi.org/pypi/pdf2docx/0.5.13/json),
[его MIT](https://raw.githubusercontent.com/ArtifexSoftware/pdf2docx/v0.5.13/LICENSE).
Для bundled-компонентов доказательством служат точные license members и hashes
в реестре, включая `lxml/LICENSES.txt`, `cv2/LICENSE-3RD-PARTY.txt` и PDFium BUILD_LICENSES.

Python-wheel OpenDoc Formats не встраивает эти Python/native зависимости.
MIT собственного пакета совместима с сохранением их самостоятельных уведомлений,
но не разрешает распространить чужой код под MIT вместо его лицензии.
Для AGPL/GPL-сборки соответствующие исходники и права получателей обеспечиваются
по её условиям; для LGPL сохраняются уведомления и права модификации/замены компонента;
для MPL сохраняется лицензия покрытых файлов и доступность соответствующего исходника.

## GitHub Pages и assets

Сайт включает неизменённые файлы поиска, поставляемые MkDocs 1.6.1:

| Asset | Атрибуция / лицензия | Где доступно |
| --- | --- | --- |
| Lunr 2.3.9 | Copyright © 2020 Oliver Nightingale, MIT | `search/lunr.js`; [полный текст MIT](../assets/licenses/lunr-MIT.txt) |
| lunr-languages / Russian | Copyright © 2014 Mihai Valentin, MPL-1.1 | `search/lunr.ru.js`, `search/lunr.multi.js`; [MPL-1.1](../assets/licenses/lunr-languages-MPL-1.1.txt) |
| Snowball stemmer support | Copyright © 2010 Oleg Mazko, MPL-1.1 | `search/lunr.stemmer.support.js`; тот же текст MPL-1.1 |
| UMD wrapper в языковых файлах | UMD contributors, MIT | Исходник wrapper сохранён в JS; [MIT](../assets/licenses/umd-MIT.txt) |

JS публикуется в исходном, не минифицированном виде вместе с сохранёнными headers.
Файлы поиска доступны под `/opendoc-formats/search/`; сайт ссылается на этот аудит.
Собственные тема, стили и viewer assets — MIT; уведомление об адаптированной теме
OpenDoc сохраняется в [NOTICE](notice.md). MathJax автоматически не загружается и
не поставляется. При добавлении сторонних шрифтов, изображений или JS нужен отдельный аудит.

## Внешние инструменты и документы

[LibreOffice](https://www.libreoffice.org/licenses/) имеет MPL-2.0/LGPLv3+ и условия
компонентов; [Pandoc](https://raw.githubusercontent.com/jgm/pandoc/main/COPYING.md) —
GPL-2.0-or-later; [DjVuLibre](https://sourceforge.net/p/djvu/djvulibre-git/ci/master/tree/COPYING)
— GPL-2.0-or-later. Они устанавливаются отдельно и не входят в пакет.
При их включении в собственный дистрибутив сохраняются их notices и source obligations.
Сгенерированный документ не становится GPL/AGPL только из-за вызова конвертера;
права на исходные материалы, шаблоны и встроенные шрифты учитываются отдельно.

Проверка font embedding bits (`fsType`) ограничивает технический экспорт,
но не удостоверяет наличие прав на шрифт. Корпус и assets проекта описаны в
[происхождении fixtures](corpus.md); пользовательские документы не публикуются.

## Контроль изменений

`tools.docs check` проверяет снимок против `uv.lock` и объявления зависимостей,
затем проверяет актуальность автоматически созданного реестра. Изменение графа
без повторного лицензионного рассмотрения останавливает CI и публикацию Pages.
Это проверка актуальности доказательств, не автоматический юридический сертификат.

Для обновления: для каждой новой версии получить metadata и license files точных
архивов, проверить bundled notices, зафиксировать URL/hash/профили/назначение в JSON,
обновить hashes lock/config и выполнить `tools.docs generate`, затем `check`.
`setuptools>=77`, внешний LibreOffice/Pandoc/DjVu и OCR потребителя не зафиксированы
этим lockfile: перед распространением сборочного окружения фиксируются отдельно.

Неурегулированный вопрос — разрешение на распространение двух XSL-ресурсов lxml.
Их статус проверен по исходникам выпуска, wheel и upstream notice;
отсутствие использования не даёт прав на копирование всего комплекта.
Решение и условия закрытия записаны в [OF16](todo.md), первичные доказательства —
в [разборе XSL](lxml-xslt.md). Выбор открытых движков и сокращение избыточных extras — OF17/OF18.
Новых запрещённых заимствований в собственном пакете не обнаружено;
выдавать безусловное заключение о всех возможных установках и дистрибутивах нельзя.
