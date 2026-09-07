# EVT-MB assembly release v1.2

Полный сборочный комплект паяной макетной станции разделен на восемь неизмененных бинарных частей из-за ограничений канала загрузки.

Восстановление Linux:

```bash
bash ../../../reassemble.sh parts РС_Дионея_EVT_MB_v1_2_ASSEMBLY_RELEASE_OPEN.zip
sha256sum -c ARCHIVE_SHA256.txt
unzip -t РС_Дионея_EVT_MB_v1_2_ASSEMBLY_RELEASE_OPEN.zip
```

Восстановление Windows PowerShell:

```powershell
..\..\..\reassemble.ps1 -PartsDirectory parts -OutputZip РС_Дионея_EVT_MB_v1_2_ASSEMBLY_RELEASE_OPEN.zip
Get-FileHash -Algorithm SHA256 РС_Дионея_EVT_MB_v1_2_ASSEMBLY_RELEASE_OPEN.zip
```

Ожидаемый SHA-256: `e5b1a2619d6048c0bf67f5e3b37c3ff8c1cc07930802f876f4f202cbfa795f57`.

