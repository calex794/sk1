# PUB-T-992 — натуральный высокий SYID в 29 учебных PUB

Каноническая задача: https://app.notion.com/p/3f632a84beec8184b9c8d90fb53fcdc4

## Новая проверка

После T987+T991 точно проверено 408 SHA-различных оригинальных Quill/SYID, 0 исходных младших FE/FF. T988 подтвердил двухбайтовый перенос FE→0x100, но только в состоянии, созданном настоящим Writer из натурального original FA. Следующий источник — **ранее зарегистрированные 29 различных учебных PUB**, часто объёмных (самый большой 25 241 088 B), из официальных публичных загрузочных ZIP Microsoft Press. Это **не 29 новых документов основного корпуса**: все 29 входят в прежний Rar exact 1556 authority.

Изначально выбраны ровно 4 архива / 33 PUB-строки / 29 distinct SHA из замороженного T720 input:
- Publisher 2007 SBS: 13 PUB SHA.
- Publisher 2010 SBS: 2 PUB SHA.
- Office 2013 SBS: 11 PUB в ZIP, 9 различных SHA.
- Office 2003 SBS: 7 PUB в ZIP, 5 различных SHA.

Источник SHA/size и пути в ZIP: `Lalalalendia/rar2@703808408fd919e564a90cdc236e81db3c04af8b/tools/corpus/receipts/version-labelled-training-29-input-2026-09-25.json`. Digest sorted LF SHA: `eb2cd6ad8f21860f93d33763a8f630135c12c128e0160e0d1909c0c3ae228ae8`.

Прежде чем запустить Reader, предъявляется exact SHA-dedup против исходных 625 Lalamu и точного корпуса T991 из [сохранённого source-safe ZIP #11700236587](https://github.com/calex794/sk1/actions/runs/38133589540/artifacts/11700236587), чьи 27 SHA имеют строго закреплённый LF digest `f20c891cfbe04a517f0298372d5d407cf9dce78915c28a48da7a799749dcedb3`. На предварительной проверке 29/29 SHA отсутствуют среди 625 и 29/29 входят в существующий Rar-1556; другой overlap фиксируется отдельно.

## Обработка без подмены

- Скачивается только строго исходный HTTPS-архив из каждой из четырёх ранее зарегистрированных ссылок. Ограничения исходных байтов: 512 MiB на ZIP, 40 MiB на PUB. ZIP целиком не извлекается: читаются только заранее указанные members. Каждый PUB SHA/длина/CFB magic подтверждается **до** Quill. При недоступности пакета 29 остаются знаменателем; его члены становятся `ARCHIVE_UNAVAILABLE`, не заменяются другими.
- Quill header, count, max live ID, младший байт, флаг `header>=254` и истинные `FE/FF` читаются оригинальным pinned Rust Quill/Cfb reader [PUB-T-987@fa714fe](https://github.com/calex794/sk1/tree/fa714fe958999325649430dad53c10edac42246a/experiments/cfb/diag/pub-t-987). Только верхнее число файлов и schema имя изменены временным генератором; никаких самописных Quill-парсеров.
- Только подтверждённые оригиналы с реальным FE/FF (если такие есть) отправляются на неизменённый проверенный Writer/Reader/CFB `rar2@703808408fd919e564a90cdc236e81db3c04af8b`, исследовательский механизм T984@14ac75ae0346b3bdbeeada110e1f463dda6cbb27. Фиксированный второй ASCII в исходно доступных Story, два одиночных шага, обе inverse-последовательности при двойном допуске, полный raw PUB и Quill/CFB diff, честные Writer guards и контрпримеры.
- Три source-safe отчёта: `plan.json`, `records.json`, `report.json`. Никаких исходных ZIP/PUB, ссылок исходного скачивания, текста Story, Quill bytes, временных Writer PUB или traceback/нефильтрованных сообщений.
- Независимый check_report.py повторно сверяет pinned manifests/625+27+1556 SHA, 33/29, каждый статус, все подтверждённые входные счётчики, целую summary и Writer Step/CFB receipts через прежние T991/T963 проверяющие; после CI скачивается архив доказательства и снова проверяется SHA/CRC/результат до Notion Done.

Если хотя бы один исходный архив недоступен, общий вывод о 29 помечается `INCOMPLETE`, а не 0/29; подтверждённые файлы остаются отдельным фактом. Название учебного набора/версия не являются доказательством способа первичной сериализации конкретного PUB. Native Microsoft Publisher Open/SaveAs не проверяется, продуктовый rar2 не изменяется.

[Actions](https://github.com/calex794/sk1/actions/workflows/sk1-cfb-diag-pub-t-992.yml) • [T987](https://app.notion.com/p/3f632a84beec814fb63edc9c99460b8a) • [T991](https://app.notion.com/p/3f632a84beec81f4b334ffec20ea5acb) • [T988](https://app.notion.com/p/3f632a84beec81cd887df660673fb7b3).