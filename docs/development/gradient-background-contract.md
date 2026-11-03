# C-BACKGROUND-GRADIENT-01: нейтральный градиент фона

Статус: общий `BackgroundPaint/GradientPaint` доступен в закреплённом `opendoc-model==0.1.0`.
[Потребительская приёмка SDK](model-api-acceptance.json) проверяет установленный
wheel, публичные экспорты, JSON и ограничения. Подключение к нативным readers/writers
и полная приёмка Formats остаются отдельными задачами; наличие DTO не означает
готовую проекцию или визуальную эквивалентность.

## Назначение контракта

`BackgroundPaint` и `GradientPaint` задают общие роли фона, stops и геометрии.
Нативный DrawingML hint и проекция в конкретные форматы принадлежат Formats. PPTX хранит редактируемые linear/path backgrounds, включая тему, направление,
fillToRect/tileRect, stops и modifiers. Сплошной цвет не представляет такой фон.

Formats реализует конечное нативное сохранение через ограниченный DrawingML hint
в своих properties, рядом с текущими цветами/позициями stops. Это форматные данные,
не общий DTO/codec и не утверждение о межформатной семантике градиента.

## Требования к Model

- Предложить нейтральную роль фона section/page и gradient paint, совместимую с
  существующим Paint/ColorValue; конкретные имена API согласует Model.
- Определить stops: позиция, цвет/alpha, порядок и допустимые совпадающие позиции.
  Не сводить градиент к первому цвету и не восстанавливать удалённые stops из extra.
- Явно определить геометрию/координатную систему для поддержанных linear/radial
  или других общих профилей; неизвестность geometry должна оставаться явной.
  Native `ang/scaled/path/fillToRect/tileRect` не переносить в общий DTO как DrawingML API.
- Установить правила отсутствующего/no-paint/solid/gradient background, правок и
  удаления. Значения общего API управляют результатом; native hints не подменяют их.
- Обеспечить штатные JSON codecs, validation, resource/reference walk и общие
  nodes/depth/bytes limits. Не добавлять XML, Office, PDF или image dependencies.
- Сохранить совместимость существующего solid Paint; неизвестные расширения
  остаются инертными. Не исполнять строки source markup.

## Граница Formats

Парсинг, safe XML, theme/style-matrix/color-map resolution, направление/единицы
DrawingML, точность исходных цветов, source bindings, рендер и сравнение в приложении
принадлежат Formats. Общие DTO/codec/validation и ссылки принадлежат Model.
После опубликованного API требуется отдельная consumer-проверка и native приёмка
проекций; наличие DTO не закрывает весь градиентный профиль PPTX.

## Приёмка

Два JSON-цикла общих solid/no-paint/gradient roles, alpha, coincident stops,
явная правка/удаление, отказы на неверных диапазонах/версиях/лимитах. Общий
contract не объявляет произвольный path gradient линейным или радиальным по догадке.
Закреплённый SDK проверять по точному SHA в отдельной среде; нативные проекции принимать отдельно.

## Принятый конечный API

`BackgroundPaint` различает absent carrier, unknown, none, solid Paint и gradient.
`GradientPaint` сохраняет неизвестный набор stops/geometry, общую opacity, spread
и interpolation. `GradientStop` сохраняет порядок совпадающих позиций, неизвестный
цвет отдельно от прозрачного ColorValue. LinearGradient задаёт endpoints в явных
relative/points coordinates, RadialGradient — концентрический круг; произвольный
DrawingML path не объявляется радиальным по догадке.

Section setter и page with-operation независимы, автоматического наследования нет.
Общий carrier `opendoc.background` версии 1 не исполняет native hints Formats.
Явная замена/удаление авторитетны. Unknown DTO/envelope fields проходят независимые
codec/getter snapshots; `iter_backgrounds` возвращает отдельные scopes с адресами,
не добавляя body nodes. ICC profile остаётся непрозрачной строкой ColorValue,
не новой ресурсной ссылкой.

`tools/background_gradient_consumer.py`
в изолированной Python 3.12.16 среде, содержащей только Model, проверяет шесть
сценариев: все DTO codecs и два document JSON-цикла; alpha/coincident stops/CMYK/
ICC/blend и неизвестность; независимость snapshots и правки/удаление; separate walk
и scopes; merge с явным keep_last и section extract; 18 явных отказов и квоты.
Сохранён [отчёт с SHA consumer](background-gradient-consumer-evidence.json).

| Квота fixture | Парный JSON transport | Section setter | Page with | Background walk |
| --- | --- | --- | --- | --- |
| max_nodes | 235 | 123 | 73 | 235 |
| max_depth | 14 | 9 | 9 | 13 |
| max_bytes | 3766 | 556 | 475 | 805 |

Точная граница проходит, значение на единицу меньше даёт ArtifactLimitError;
при отказе сохраняются mapping и wire. Числа относятся к этому fixture и разным
областям учёта, не к универсальному размеру градиента.

```powershell
python -I tools/background_gradient_consumer.py --candidate .opendoc-formats/gradient-model-candidate --output .opendoc-formats/gradient-model-candidate/consumer-evidence.json
```

Это приёмка общего DTO/codec/validation, не source parsing, native gradient projection,
межформатный рендер или полное закрытие OF06. Основной SDK и dependency pin не меняются;
production-интеграция требует опубликованного API и отдельной нативной приёмки Formats.
