# SK1 PUB-T-996 — known 0x13/0x04 importer controls

Canonical Task: https://app.notion.com/p/3f632a84beec81cd8af9cad42cd40acb

This is a controlled sequel to T994, reusing the **same two exact source files** and the **same pinned executable importer harness**. It is not an independent corpus.

Public Apache POI `60685.pub` has 10 explicit paragraph property id`0x13` `SpaceAfter`: perturb first one by +12700 EMU (=1 point), all by +12700 EMU, and all to 0 (without changing property lengths). `51318.pub` has four id`0x04` alignment values `0x5A02`: perturb first/all low bytes to 00 and all high bytes to 00 separately. Real LibreOffice imports ODG and compares uncompressed `content.xml` and `styles.xml`. Two deterministic baseline conversions, a wide TEXT mutation and malformed CFB rejection remain required controls.

The source reader, Quill/STSH parser, CFB same-length patcher and LibreOffice importer are reused from SK1 T994 pinned at scientific SHA `87a6733516ad6ffd1b6b97a3176f359bfeb60ca1` via a separate read-only Actions checkout. No second parser or product Writer implementation. It downloads only two public pinned Git blobs and emits numerical report.json. The actual PUB and ODG bytes remain in ephemeral private runner directories.

A known-field output difference alongside prior unknown id0x30 invariance means a **bounded LibreOffice importer style-carrying differential**. If no visible output differs, report the style-location/input limit rather than inferring unused PUB fields. Native Microsoft Publisher is not run or implied.
