# SK1-CFB-CMP-PUB-T-981

[Notion task](https://app.notion.com/p/3f632a84beec81df8da6dda4e75ab198). Source-safe independent comparison of real OfficeArt records in DOC, XLS, PPT, PUB; **not** a parallel Reader/Writer.

Twelve pinned Apache POI files at commit `ae62bb5116b9aee19ebd5834e3a82066132c9f7f`, with exact Git blob identities and SHA256 observations. No actual document bytes leave the job. XLS BIFF drawing records 0x00EB/0x00EC and 0x003C Continue are gathered separately. Other formats use bounded grammar-validated OfficeArt root scanning, not a claim of full host ownership.

Capture record type, count, offset, SHA256, FOPT property IDs, FDGG/FDG, F010 sizes; compare intersections across four formats. Corrupt-header negative control required. Scientific acceptance requires four formats with at least one validated root and real XLS FOPT; if not, report is PARTIAL even with a successful extraction step.

Results and uncertainty go to the existing [cross-format Notion section](https://app.notion.com/p/3f532a84beec81f58b46f6fb4702a135). No native Publisher oracle; no RAR2 mutation.