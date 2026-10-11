# PUB-T-988 — реальный Writer доводит натуральный SYID FA до FE и далее

[Каноническая задача в Notion](https://app.notion.com/p/3f632a84beec81b3ad6acea92f5d45de)

**Новый вопрос:** может ли неизменённый реальный Writer без прямого вмешательства в счётчик `SYID` дойти от настоящего оригинального PUB с `SYID.header=0x000000FA` до **Writer-generated** `0x000000FE`, а затем двушаговой обратной правкой перейти к `0x00000100`, изменив только два исходных байта всего PUB? Это НЕ доказывает наличие природного original Publisher FE.

## Оригинал и строгий контроль

Единственный заранее выбранный source SHA: `ba0b30328b7fdf4d8c6209de0925d6113dc95b917b95caa2d64218869970dd79`; `99 328` bytes; Quill original SYID.header `250 (FA)`, count `21`, max live `250`. Неизменный raw PUB в pinned `Lalalalendia/lalamu@87094c23e2a9eaa2aa9e95d72ec52f72ef109f11`, tree `8146fa9fdd2f577ebe02bc7205a61bb14e20d3e7`. Научное доказательство натурального source: [PUB-T-987](https://app.notion.com/p/3f632a84beec814fb63edc9c99460b8a), 625/625 immutable SHA census и 0/382 natural original FE/FF.

Путь состоит из **3 последовательных пар настоящих Writer операций insert→delete** на одном и том же исходном содержимом Story: (250→252→254→256). До трёх Story выбираются строго из original Quill ordinal по исходной возможности редактирования и наличию второго ASCII-символа. Запрещён выбор другой позиции на основании Writer результата. Все блокировки учитываются.

В начале каждого цикла Writer заново редактирует текущий PUB в памяти: первая вставка +1, второе удаление +1, конечный текст возвращается к исходному. После каждого реального Writer шага Reader reopen + siblings + byte replay гарантирует допустимость записи; после каждого полного цикла сравнивается **каждый физический байт файла** с исходным и с началом этого цикла, Quill `TEXT`, остальные Quill чанки, CFB paths и все прочие потоки. Для третьей пары проверяется исходный **Writer-generated FE → Writer-generated 0x100**, но исходным настоящим Publisher-файлом остаётся FA.

Исходные функции Writer/Reader/Quill/CFB берутся без изменений из `Lalalalendia/rar2@703808408fd919e564a90cdc236e81db3c04af8b`. Существующий научный `step`, полный physical CFB diff и source-immutable контроллинг наследуются через pinned T984@14ac75ae0346b3bdbeeada110e1f463dda6cbb27 → T963@2caeec283312b0865054ae6f5f93fc9ac1c76b9d, T971@cd38c8d6a545737f9f99821076340505db5e149c. Ни второй Writer, ни изменение upstream/source original.

Результаты `plan.json`, `records.json`, `report.json` не содержат PUB, Quill raw, текста Story, URL и stderr. Независимый проверяющий повторно открывает original PUB, проверяет SHA и каждую числовую Quill/CFB/multi-step последовательность. Два разных исхода — PASS (если реально сделаны 6 Writer операций) и INCOMPLETE (если штатный guard запретил какую-то операцию); оба научно полезны, ни один не подменяется синтетикой. Native Microsoft Publisher не проверяется.

[Запуск в GitHub Actions](https://github.com/calex794/sk1/actions/workflows/sk1-cfb-exp-pub-t-988.yml).
