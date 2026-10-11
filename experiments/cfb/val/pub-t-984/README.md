# PUB-T-984 — натуральный SYID на внешнем корпусе и физическая обратимость Writer

Каноническая задача: https://app.notion.com/p/3f632a84beec81bdb872eb4a4dd346e3

## Что новое

Новый вопрос — обратные +1/-1 и -1/+1 Writer-правки на 47 ранее зарегистрированных натуральных PUB SHA, отобранных в PUB-T-971. Это исходные файлы, без изменения SYID на входе. Ранее 31/47 исходников удавалось скачать и подтвердить, но полная Writer-inverse байтовая проверка не проводилась. Не считать 47 вновь обнаруженными документами.

## Неподменяемый корпус

Выборка 47 исходников из T971, calex794/sk1 scientific commit 69989902bfdc87fac1aeb57ccb6a1f78872831fd: исходные 370 SHA из Lalamu pin f78cc6f455f4dc222868f9cc035511a6ca7a91ea, исключены 35/62/27/27/27 ранее использованных SHA, оставшиеся 47 SHA на 37 хостах, суммарная ожидаемая длина 28 191 744 байта. SHA256 списка SHA через LF: b9a0559613179f31e6ee9e0d75210cce523e4dafabfba6a3d2d660f086c0d8e2. Прежний доказательный ZIP T971 #11684723643 SHA256 055c1ec20ebfcbe17c2aad04bba5d11d942c159686ec49f43430463b7eee31bf.

## Переиспользование без второго Writer

prepare.py проверяет точный научный commit T963 2caeec283312b0865054ae6f5f93fc9ac1c76b9d и его git Rust blob, затем создаёт только на временном исполнителе GitHub Actions исследовательский пример из существующего проверенного T963. Единственные изменения метода: выбор Story строго в исходном Quill ordinal, до трёх с минимум двумя ASCII-символами, ровно второй ASCII slot, числовой замер исходного первого DWORD Quill SYID, числа Story и max live ID. Сам Writer, сравнение CFB, контроль Reader/Editor и построение канонических PUB не переписываются.

Единственная исходная реализация — Lalalalendia/rar2@703808408fd919e564a90cdc236e81db3c04af8b, без изменений продукта.

## Проверка

После SHA/size приёмки для каждой натуральной Story выполнить две одиночные правки +1 и -1 с фиксированным ASCII символом, без выбора по результатам Writer. Лишь если обе прошли, выполнить независимые смысловые inverse последовательности insert-then-delete и delete-then-insert. Проверить Reader reopen, siblings, byte-equal EditorProject replay; каждый успешный конечный PUB сравнить по всем сырым байтам с исходным и по Quill/TEXT/всем другим CFB потокам.

В отчёте учитывать естественный SYID old/new +2, точный счёт изменённых little-endian байтов, запреты Writer, возможные несоответствия. Не заменять недоступные PUB, до четырёх параллельных загрузок, только разрешённые HTTPS source hosts. Опубликовать только три source-safe JSON, никогда PUB bytes/Quill raw/Story text/original URL/stderr. Для положительного обобщения требуется минимум 10 разных SHA с успешной инверсией; иначе INCOMPLETE. Native Publisher/SaveAs не проверяется.

GitHub Actions: https://github.com/calex794/sk1/actions/workflows/sk1-cfb-val-pub-t-984.yml

Предыдущие знания: https://app.notion.com/p/3f532a84beec811b9a65cca12f9bf852 и https://app.notion.com/p/3f532a84beec815d9e32e30b5ba583cd
