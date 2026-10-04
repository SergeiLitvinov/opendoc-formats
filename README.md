<img src="https://raw.githubusercontent.com/SergeiLitvinov/opendoc-formats/main/docs/assets/documentation-logo.svg" width="64" height="64" align="right" alt="OpenDoc Formats">

# OpenDoc Formats

**Файлы → модель OpenDoc → файлы.**

[![CI](https://github.com/SergeiLitvinov/opendoc-formats/actions/workflows/ci.yml/badge.svg)](https://github.com/SergeiLitvinov/opendoc-formats/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/SergeiLitvinov/opendoc-formats)](https://github.com/SergeiLitvinov/opendoc-formats/releases)
[![MIT](https://img.shields.io/badge/license-MIT-blue)](docs/development/LICENSE)

[Документация](https://SergeiLitvinov.github.io/opendoc-formats/) · [Руководство](docs/guide/index.md) · [API](docs/reference/api.md) · [Выпуски](https://github.com/SergeiLitvinov/opendoc-formats/releases)

Импорт и экспорт файлов через модель OpenDoc, с диагностикой преобразований.
Пакет: `opendoc-formats`, импорт: `opendoc_formats`; Python 3.11+.
**Обязательная зависимость — OpenDoc 0.1.0.** Собственной копии модели и зависимости от приложений нет.

Проект экосистемы [okidoki](https://github.com/search?q=user%3ASergeiLitvinov+topic%3Aokidoki&type=repositories), со своими версиями, тестами и выпусками.

| Формат | Импорт | Экспорт | Движок / extra |
| --- | --- | --- | --- |
| TXT / JSON OpenDoc | Да | Да | Базовый пакет |
| HTML / CSS | Да | Да | `html` для импорта |
| DOCX | Да | Да | `docx` |
| PPTX | Да | Да | `pptx` |
| PDF | Да | Да | `pdf` |
| EPUB | Да | — | `epub` |
| DjVu | Текст | — | Внешний `djvutxt` |
| LaTeX | — | DOCX-мост | `docx`; Pandoc для отдельного маршрута |

Дополнительные инструменты: внедряемый OCR для PDF, шрифты (`fonts`),
прямой PDF → DOCX и PPTX → HTML-просмотрщик с локальными CSS/JS и браузерным MathML.
Подробные [границы форматов](docs/guide/formats.md) включают потери, непрозрачные объекты и доступ к ресурсам.

## Установка

Из исходников: `uv sync --frozen --all-extras`. Для нужных движков:
`uv sync --frozen --extra docx --extra html`. Python 3.11–3.13.

Из [GitHub Release](https://github.com/SergeiLitvinov/opendoc-formats/releases), без зависимости от публикации на PyPI:

```sh
python -m pip install "opendoc @ https://github.com/SergeiLitvinov/opendoc/releases/download/v0.1.0/opendoc-0.1.0-py3-none-any.whl" "opendoc-formats[docx,html] @ https://github.com/SergeiLitvinov/opendoc-formats/releases/download/v0.2.0/opendoc_formats-0.2.0-py3-none-any.whl"
```

Необязательные движки импортируются только при выборе обработчика. TXT/JSON работают с базовой установкой.

## Пример

```python
from opendoc_formats import read_document, write_document
result = read_document("report.docx")
if result.success:
    report = write_document(result.document, "report.html")
    print(report.to_dict())  # Потери нужно читать и при успешной записи.
```

[Документация](https://SergeiLitvinov.github.io/opendoc-formats/) ·
[Руководство](docs/guide/index.md) · [API](docs/reference/api.md) ·
[Аудит](docs/development/audit.md) · [История изменений](docs/development/changelog.md)

## Разработка

`uv run ruff check` · `uv run mypy` · `uv run pytest` · `uv run python -m tools.audit`

Документация: `uv run python -m tools.docs generate`, затем `check` или `serve`.
Сборка: `uv build --out-dir .opendoc-formats/dist`;
проверка пакетов: `uv run python -m tools.release check`.
CI проверяет Linux на Python 3.11/3.12/3.13 и Windows на 3.12, базовую установку и wheel из sdist.
GitHub Pages публикуется после успешного CI. Тег `vX.Y.Z` запускает проверку версии и выпуск пакетов.

MIT; происхождение кода и сохранённые уведомления — в [NOTICE](docs/development/notice.md).
