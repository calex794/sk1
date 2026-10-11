# PUB-T-995 — живые SYID vs высокий счётчик на настоящих исходных PUB

Каноническая задача: https://app.notion.com/p/3f632a84beec8106a7d8dc838097aa69

**Новый проверяемый вопрос:** первоначальный `SYID.header` действительно может быть больше max(live ID). На двух исходных публичных `ADatumNews.pub` и `ADatumNews_final.pub` из одного официального учебного архива H=1009 и H=1027, count=65, max live=965 и 1020. **Одинаковый count не доказывает одинаковый набор ID.** Проверить, сколько из 65 исходных числовых Story ID реально совпадают, сохранились на одинаковых позициях либо исчезли/добавились.

**Выбор пары зафиксирован до нового чтения IDs**:
- `b4b005a7e6f662546cf07bdd155a1cf936293e6ceb6ac7f424456fee87051f1b`, 471552 B, original H=1009, 65 IDs, max=965;
- `3562f0fe51e5e1dbf42f81f574cea831b0734f6d08a9a1a9cc610c84f44caeff`, 476672 B, original H=1027, 65 IDs, max=1020.

**Все оригиналы**: повторно взять ровно исходный набор T992 из 4 замороженных MicrosoftPress ZIP, 33 archive members / 29 SHA-distinct; авторизованный документ/size/SHA-256 — `Lalalalendia/rar2@703808408fd919e564a90cdc236e81db3c04af8b/tools/corpus/receipts/version-labelled-training-29-input-2026-09-25.json`. Полный retriever только из закреплённого SK1 T992@cfcce7f3f9c425210ee28265d4dbdf79bf742dcc. Все файлы получены и проверены SHA **до** исследования Quill. Никаких новых файлов по исходу проверки.

**Измерение**: использовать реальный неизменённый product `pub_quill::parse_confirmed_story_catalog` внутри того же pinned `rar2`. Для каждого parseable оригинала выдать только H, count, max ID, упорядоченный массив numeric `SYID.ids` (не текст), gap H−max, уникальность IDs. Для фиксированной пары: пересечение distinct IDs, только в A, только в B, позиционные совпадения, разница H и max live. На всём наборе: распределение gaps, строгое `H>=max` и возможные контрпримеры. Один уже известный Quill parse-blocked источник не интерпретировать как нулевой ID.

**Контроль**: независимый `check_report.py` повторно хеширует все 29 исходных PUB внутри GitHub runner, сравнивает с прежним T992 source-safe оригинальным JSON, математически пересчитывает все числовые ID-поля и Pair/итоги. Затем оригинальный ZIP артефакт отдельно загружается и перепроверяется SHA/CRC, только после этого Notion Done. Публикация **строго трёх файлов** `plan.json, records.json, report.json`; никаких PUB/Quill bytes/Story text/исходных ZIP. Числовые идентификаторы — безопасные метаданные из публичных образцов.

**Ограничение**: оригиналы из учебного пакета названы `start/final`, но подлинная история изменений между ними не установлена. Корреляция H/ID поддерживает или опровергает working high-water гипотезу, **не доказывает** механизм выделения ID и поведение Microsoft Publisher при SaveAs. Не запускать Writer — это уже изучено в T993. `rar2` не менять.

[Запуск](https://github.com/calex794/sk1/actions/workflows/sk1-quill-diag-pub-t-995.yml) — [исходная гипотеза OBS-028A](https://app.notion.com/p/3df32a84beec8188bbd3e7c59b681b78), [T992](https://app.notion.com/p/3f632a84beec81d5a716e797ecec7385), [T993](https://app.notion.com/p/3f632a84beec81ebb15bf70b5b0c1c9b).