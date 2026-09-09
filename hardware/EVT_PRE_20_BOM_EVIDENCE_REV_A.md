# EVT-PRE-20 Rev.A BOM component evidence

Status: `CONTROLLED INPUT / NOT A PRODUCTION RELEASE`

This register records the source used to normalize exact orderable identity, package,
and temperature data in the Rev.A BOM. Electrical suitability, layout, sourcing, and
sample validation remain governed by the line blockers and QG-2.

| BOM item | Exact identity | Controlled fact | Primary evidence |
|---|---|---|---|
| U2 | `W25Q512JVFIQ` | SOIC-16, industrial `-40..85 C` suffix | [Winbond W25Q512JV product guide](https://www.winbond.com/hq/new-online-purchasing-guide/?__locale=en&pLine=%2Fproduct%2Fcode-storage-flash%2Fqspi-nor%2F&pNo=W25Q512JV) and W25Q512JV datasheet |
| U3 | `LIS2DW12TR` | LGA-12 2 x 2 mm, `-40..85 C` | [ST LIS2DW12 product page](https://www.st.com/en/mems-and-sensors/lis2dw12.html) and DS11811 |
| U4 | `STTS22HTR` | UDFN-6L 2 x 2 mm, `-40..125 C`; supersedes the erroneous WLCSP-4 description | [ST STTS22H product page](https://www.st.com/en/mems-and-sensors/stts22h.html) and [DS12606](https://www.st.com/resource/en/datasheet/stts22h.pdf) |
| U8 | `BG95-M3` | `-35..75 C` operating, `-40..85 C` extended | Quectel BG95 Series Hardware Design; extended-range operation remains a project qualification item |
| U10 | `E22-900M22S` | SMD 14 x 20 mm, `-40..85 C` | [Ebyte E22-900M22S manual](https://www.cdebyte.com/pdf-down.aspx?id=1822) |
| X1 | `SiT1552AI-JE-DCC-32.768D` | CSP-4 1.5 x 0.8 mm, `-40..85 C` | [SiTime exact-orderable product page](https://www.sitime.com/parts/sit1552ai-je-dcc-32768) and [SiT1552 datasheet](https://www.sitime.com/datasheet/SiT1552) |
| PWR-TVS-01 | `SMBJ18A` | SMB/DO-214AA, `-65..150 C` junction operating range | [Littelfuse SMBJ18A product page](https://www.littelfuse.com/products/overvoltage-protection/tvs-diodes/surface-mount/smbj/smbj18a) and [SMBJ series datasheet](https://www.littelfuse.com/assetdocs/tvs-diodes-smbj-series-datasheet?assetguid=ba555e99-a12d-4f72-a0b6-86b06c67171e) |
| PWR-FUSE-01 | `0451005.MRL` | Nano2 451 5 A, `-55..125 C` | [Littelfuse 0451005 product page](https://www.littelfuse.com/products/fuses-overcurrent-protection/fuses/surface-mount-fuses/nano-2-fuses/451/0451005) and [451/453 series datasheet](https://www.littelfuse.com/assetdocs/fuse-451-and-453-datasheet?assetguid=533cd5cc-956c-4243-867f-6ab5a62f6ba1) |
| PWR-COUT-3V8/3V3 | `CGA6P3X7R1E226M250AB` | four physical 22 uF, 25 V, X7R, 1210 MLCCs per rail; refs `C3/C14-C16` and `C5/C17-C19` | [TDK exact product page](https://product.tdk.com/en/search/capacitor/ceramic/mlcc/info?part_no=CGA6P3X7R1E226M250AB) |
| MK1 | `MMICT5838-00-012` | LGA-CAV-5 3.5 x 2.65 x 0.98 mm, `-40..85 C`; exact order code already present in native PCB-MIC | [TDK T5838 product page](https://www.invensense.tdk.com/en-us/products/microphone/t5838) and DS-000383 v1.2 |
| J-RF-CELL/GNSS/LORA | `U.FL-R-SMT-1(60)` | board receptacle `-40..90 C`; cable assemblies are separate open system items | [Hirose exact product page](https://www.hirose.com/en/product/p/CL0331-0472-2-60) and [U.FL series catalog](https://www.hirose.com/en/product/document?clcode=&documentid=ed_U.FL_CAT&documenttype=Catalog&lang=en&productname=&series=U.FL) |

For every candidate or pending line, current manufacturer documentation shall be
captured into the release data pack at the revision used by the design review. Links
above are evidence pointers, not permission to substitute a family member or suffix.
