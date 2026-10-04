# Предложения для модели OpenDoc

Основание — контракт официального `opendoc==0.1.0`, которым пользуется адаптер.
Это предложения к развитию модели, не утверждение о реализованных функциях.
Парсеры TeX/OOXML/PDF, внешние движки и выбор способов чтения остаются в OpenDoc Formats.

OpenDoc уже предоставляет `DocumentModel`, `PackageGraph`, `Formula`, `Provenance`,
`VisualSurrogate`, ресурсы, таблицы с объединениями, стили, единицы, цвета,
валидацию/лимиты и расширения. Эти механизмы следует развивать, а не дублировать.
В 0.1 структурные unions ограничены `Paragraph | Table` и `TextRun | Formula | Image`;
многие сложные объекты адаптер вынужден кодировать в `properties`.

## Приоритеты

| Приоритет | Дополнение | Зачем и критерий контракта |
| --- | --- | --- |
| 1 | Версионированные capability profiles и типизированный отчёт сохранения | На уровне feature различать semantic/opaque/visual/lost/rejected; location, reason и provenance. Развить существующие `DiagnosticIssue` и `Provenance`, не вводить конкурирующие отчёты. JSON сохраняет отчёт; валидатор проверяет ссылки на объекты |
| 1 | `SourceSpan` / `SourceMap` и unknown nodes | Для TeX, HTML, XML и вложенных файлов: URI/part, смещения, строка/столбец, связь с исходным объектом и раскрытием макроса. Unknown fragment имеет media type, resource ID, предел размера и политику экспорта. Оригинальный синтаксис дополняет нормализованную модель, без исполнения |
| 1 | Поля, ссылки, цитаты и диапазоны | Общие типы field/reference/citation/bibliography, комментарии и revisions с ranges/IDs, content controls как optional schema. Текстовый диапазон переживает редактирование и JSON; field code не исполняется. Существующие headings/anchors/internal links используются как основа |
| 1 | Векторная сцена | `Path`, `Paint`, affine transform, group, clip/mask, z-order; ограниченные команды и ссылки на ресурсы. Общие единицы/Color сохраняются. Объект сериализуется, валидируется с лимитами, экспортёры объявляют поддержанное подмножество. Полезно PDF/SVG/PPTX/DOCX |
| 2 | Типизированные diagram/chart data и style inheritance | Series/axes/categories/caches, группы фигур, разрешение theme/master/layout; отделить данные от visual fallback. Заменять согласованные `properties` схемами постепенно, без переноса OOXML namespaces в базовые универсальные типы |
| 2 | Страницы, tagged semantics, annotation/form и media/timing | Явный reading order, accessibility роли/alt/lang, форма и аннотация, аудио/видео и временные связи как версионированные optional extensions. Actions — данные с запретом выполнения. Табличная книга требует отдельной sheet/cell/formula extension, не подмены обычной `Table` |
| 2 | Нормализованная структура математики | Дополнить существующую `Formula` optional AST и связи с оригинальным LaTeX/MathML/OMML. Сохранить исходное значение и surrogate, проверять глубину/число узлов. Разбор пакетов и макросов TeX остаётся адаптеру |
| 2 | Эволюция расширений и проверки соответствия | Версия schema, migration и feature negotiation; corpus JSON roundtrip и стабильные IDs. Unknown extension допускается по policy, не объявляется семантически понятной. Использовать существующие extension schemas и limits |

## Последовательность

Сначала общий отчёт потерь и source mapping: они делают неполный импорт проверяемым.
Далее диапазоны/поля и векторная сцена: это основные препятствия для LaTeX, DOCX и PDF.
После этого — chart/scene/media и специализированные расширения.

«Полный парсинг» следует задавать как конечный профиль спецификации с corpus и
критериями roundtrip. Произвольные TeX-программы, динамический HTML и неизвестные
Office extensions не имеют единственного универсального семантического перевода.
Для них нужны сохранение оригинала, ограниченный fallback и честная диагностика.

Обязательная граница: OpenDoc не импортирует PyMuPDF, EbookLib, python-docx,
LibreOffice или приложения; модель остаётся самостоятельной MIT-библиотекой.
