# C-IMAGE-RECT-01: общий исходный прямоугольник изображения

Статус: Model реализует draft `ImageSourceRect` и публичные get/set API; конечная
изолированная consumer-проверка API/JSON/лимитов и native prototype пройдена.
Опубликованный API и production adoption ещё требуются. Formats продолжает
использовать опубликованный `opendoc-model==0.19.0`, импорт `opendoc_model`;
основная среда и исходники Model не менялись. Доказательства:
[consumer evidence](image-source-rect-consumer-evidence.json).

## Воспроизводимый пробел

PowerPoint 16 сохраняет допустимый DrawingML `srcRect` с отрицательными insets.
Собственный PNG 120×180 с прозрачностью, PictureFormat.CropLeft = -12 pt,
CropTop = 36 pt, CropRight = 12 pt, CropBottom = 18 pt даёт:

```xml
<a:srcRect l="-13333" t="26667" r="13333" b="13333"/>
```

`tools/pptx_crop_powerpoint_acceptance.ps1 -Stage outset` воспроизводит пример
на fixture `tests.writers.test_pptx_source_crop.own_picture`; исходник открывается
read-only, макросы отключены. Это native viewport с полем слева от исходного
изображения, а не недопустимая отрицательная ширина.

В Model 0.19.0 `ImageCrop.left` требует минимум 0. До защитной обработки Formats
публичный `read_document` выбрасывал `ValueError` при `set_integration`, поскольку
валидация всей Model отклоняла исходную допустимую геометрию. Formats сохраняет
такой viewport в своём namespace как opaque native attributes, ставит `crop=None`
и выдаёт located `pptx.image-crop` / `unrepresentable-source-rectangle`.
Это сохранение исходных данных, а не полная семантическая проекция.

## Требуемый общий API

Предлагается отдельный необязательный `ImageSourceRect` с нормализованными
координатами left/top/right/bottom относительно исходного изображения и публичным
доступом на `Image` или через общий typed API Model. Имена и carrier согласует
владелец Model. Нужен самостоятельный общий DTO, а не OOXML XML/attribute bag.

Для приведённого native примера общий rect:
`left=-0.13333, top=0.26667, right=0.86667, bottom=0.86667`.
Координаты могут выходить за [0, 1], но должны быть конечными; right > left,
bottom > top. Прямоугольник описывает область source space, помещаемую в Image.box;
выход за исходные bounds означает внеизобразительную область, а не экстраполяцию
pixels. Отрисовка/композиция остаётся задачей потребителя.

Существующий `ImageCrop` и его область валидности следует сохранить либо дать
явную совместимую миграцию. Нужна определённая политика, когда заданы оба
представления: конфликт не должен молча менять интерпретацию. Для обычного crop
соответствие: rect=(crop.left, crop.top, 1-crop.right, 1-crop.bottom).

## Приёмка Model

- Публичный экспорт типа/API, официальный dict/JSON codec и два независимых
  round-trip; отсутствие нового rect сохраняет прежние документы и snapshots.
- Поддержка finite signed/outside coordinates, отказ для bool, NaN/Inf,
  вырожденных и перевёрнутых rect; диагностические paths определены.
- Unknown fields, DocumentLimits и независимость вложенных mutable значений
  соответствуют общим правилам Model; atomic set/refusal не оставляет изменений.
- Определены единицы, приоритет/конфликт с ImageCrop и правила fingerprint/layout
  freshness после замены source rectangle.
- Model не получает XML/PPTX/DOCX/PDF парсеры, native units, движки, crop rendering
  или зависимость от Formats.

## Ответственность Formats

Разбор signed OOXML percentages, native image/resource bindings, проекция в
`srcRect`, EMU/percentage precision, source freshness, output validation и native
PowerPoint/Word/PDF приёмка принадлежат Formats. После стабильного API и release
wheel нужна отдельная потребительская проверка negative/outside viewports.
До неё source profile разрешает лишь подтверждённый обычный ImageCrop;
неподтверждённые правки signed viewport отклоняются, исходный package сохраняется.
