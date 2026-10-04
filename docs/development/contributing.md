# Участие в проекте

OpenDoc Formats — отдельный пакет обработчиков с обязательной моделью OpenDoc.
Открывайте issue с минимальным файлом, ожидаемым результатом и диагностикой преобразования.
Не добавляйте документы с персональными данными в публичный корпус.

## Проверки

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
```

Изменение поведения сопровождается примером, проверкой и обновлением руководства и CHANGELOG.
API и навигатор создаются генератором; не редактируйте их вручную.
Новые движки загружаются лениво, сохраняют типы OpenDoc и явно описывают потери.
Публичный контракт — `opendoc_formats` и реестры `api` / `export`.
Низкоуровневые парсеры — API для опытных пользователей; в ветке 0.x их сигнатуры могут меняться в minor-выпусках.
Поддержка формата расширяется по конкретному воспроизводимому примеру.
