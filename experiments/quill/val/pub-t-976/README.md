# PUB-T-976 — проверка закона FDPP ↔ конец абзаца CR без Writer

[Исследовательская задача в Notion](https://app.notion.com/p/3f532a84beec8100ba31d1288e332838).

## В чём новизна

[OBS-R27-04](https://app.notion.com/p/3df32a84beec812aaa6fd6a5bc26c0ce) ранее обнаружил на 16 исходных Publisher-документах: все **437** границ FDPP совпадали с позицией сразу после UTF-16 CR=0x000D; **132/132** непустых Story завершались CR. При этом FDPC не везде выделяет CR в отдельный форматный участок.

Здесь проверяется отношение ORIGINAL PUB bytes → Quill descriptor arrays на **другом 47-SHA/37-host наборе**, без вызовов Writer, без нового PUB, без выполнения Publisher. Reader используется лишь для навигации по source bytes и независимой сверки Story slice. Это внешняя проверка модели формата, а не самопроверка Writer guard.

## Вход — зафиксирован до опытов

- Закреплённый отбор: calex794/sk1@cd38c8d6a545737f9f99821076340505db5e149c — 47 original source SHA, 28 191 744 байта, 37 публичных HTTPS-хостов. Это **тот же набор, что T971**, поэтому не утверждать независимость от T971. Прежние 178 SHA исключены.
- Исходная реализация CFB/Quill Reader: Lalalalendia/rar2@703808408fd919e564a90cdc236e81db3c04af8b. Исходники продукта не меняются.
- Манифест: Lalalalendia/lalamu@f78cc6f455f4dc222868f9cc035511a6ca7a91ea.
- Не подменять недоступные источники, учитывать HTTP/redirect/SHA неудачи по полному исходному знаменателю 47.

## Измерения

1. Пройти исходный Quill TEXT сырой UTF-16 LE поток; для каждого CR отметить абсолютный offset **после двух байтов CR**. Не выводить текст.
2. Независимо разобрать payload FDPP и FDPC: u16 count, array DWORD positions в framing 8+count*6, проверить выравнивание/диапазоны, pages, уникальность.
3. Сравнить **мультимножества** CR-end и FDPP boundary positions в обоих направлениях, указать ошибочные числовые смещения (до 30 в файле), количество и тип ошибок. Мismatch — результат, не причина скрыть файл.
4. Сверить raw Story slice с Reader catalog, покрытие TEXT без пропусков/перекрытий; измерить Story terminal CR / non-terminal CR.
5. FDPC: отдельно terminal и internal CR разбить на четыре категории (есть start+end boundary, только start, только end, ни одной).

## Научная приёмка

Граница охвата: >=15 parsed SHA, >=100 непустых Story, >=200 raw CR. Если меньше — сохранить результат как неполный; не называть ограниченность универсальным законом. Source-safe report из ровно plan.json, records.json, report.json с SHA, host, численными счётчиками, boolean и безопасными позициями разногласий. Независимый check_report.py пересчитывает агрегаты, проверяет строгие ключи и provenance, но не читает оригинальные PUB.

В GitHub artifact **нет** PUB, Quill, текста, исходных URL, stdout/stderr или токенов. Native Microsoft Publisher Open/SaveAs NOT_EVALUATED. Writer вообще не используется. Обновление WFS/Core без канонической Claim promotion запрещено.
