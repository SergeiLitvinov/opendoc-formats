# Сборка, версия и выпуск

## Версионирование

Единственный источник версии — `[project].version` в pyproject.toml.
`opendoc_formats.__version__` читает metadata установленного пакета.
Тег выпуска — `vX.Y.Z`; версия тега, wheel, sdist и запись CHANGELOG должны совпадать.
В ветке 0.x minor допускает изменения API, patch — совместимые исправления.
После изменения версии обновите CHANGELOG, ссылки установки, lockfile и документацию.

## Проверка

```sh
uv sync --frozen --all-extras
uv run ruff check
uv run mypy
uv run python -m tools.audit
uv run pytest
uv run python -m tools.docs generate
uv run python -m tools.docs check
uv build --out-dir .opendoc-formats/dist
uv run python -m tools.release check
uv run twine check .opendoc-formats/dist/*.whl .opendoc-formats/dist/*.tar.gz
```

`tools.release check` проверяет версии, состав обоих архивов, необходимые ресурсы,
метаданные и лицензии и создаёт SHA256SUMS. В отдельной среде `tools.package_smoke`
проверяет фактически установленный пакет. CI собирает wheel заново из sdist.
Wheel устанавливается отдельно от checkout с `python -I`, сначала без extras.

## GitHub Actions

`ci.yml` выполняет lint, типы, архитектурный аудит, pytest, документацию и сборку
на Linux (3.11/3.12/3.13) и Windows (3.12), затем проверяет дистрибутивы в изоляции.
`pages.yml` публикует сайт в GitHub Pages после успешного CI основной ветки.
`release.yml` запускается по тегу, выполняет CI для этого тега, проверяет совпадение версии,
собирает wheel и sdist и создаёт GitHub Release с контрольными суммами.
Автоматическое скачивание стороннего CLI для публикации не требуется — используется GitHub API.

В настройках GitHub Pages источник должен быть **GitHub Actions**.
Домен: `https://SergeiLitvinov.github.io/opendoc-formats/`.
Публикация на PyPI в этот процесс не входит; пакеты доступны как assets GitHub Release.
При установке pip нужно явно предоставить официальный wheel OpenDoc, как показано в README.

## Документация

`tools.docs generate` создаёт домашнюю страницу из README, API из AST публичного контракта,
навигатор исходников с методами, сигнатурами и ссылками, копии TODO/CHANGELOG/CONTRIBUTING/NOTICE.
`check` сравнивает с источниками и выполняет строгую сборку MkDocs.
`serve` показывает локальную документацию на порту 8004.
Стиль okidoki адаптирован из OpenDoc: навигация, поиск, светлая/тёмная темы и адаптивный макет;
синяя палитра и слоган принадлежат этой библиотеке.
