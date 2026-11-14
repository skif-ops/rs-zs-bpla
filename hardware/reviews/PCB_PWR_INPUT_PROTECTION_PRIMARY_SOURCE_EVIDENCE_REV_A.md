# PCB-PWR Rev.A input-protection primary-source evidence

Status: `PASS SOURCE CONTROL / EXACT ORDERABLES HASH-BOUND / PHYSICAL QUALIFICATION OPEN / NOT FOR MANUFACTURE`

Configuration: `EVT-PRE-20 Rev.A`

This record closes only `PWR-IPQ-001 SOURCE_CONTROL`. It binds the exact
Littelfuse fuse/TVS and Molex connector/terminal orderables to current official
manufacturer payloads retrieved on `2026-09-17`. It does not accept samples,
thermal behavior, transient performance, routing, procurement or manufacture.

Machine-readable companion:
`hardware/reviews/PCB_PWR_INPUT_PROTECTION_PRIMARY_SOURCE_EVIDENCE_REV_A.json`.
Its SHA-256 is
`1ee7d72b7f71bfd53879c43031ba0bf184a0c5d3beb0558ca1e691c585424823`.

The repository follows the existing TI source-evidence policy: third-party
binaries are not copied into Git. Canonical URLs, retrieval date, exact byte
sizes and SHA-256 values identify the reviewed payloads reproducibly. All four
PDFs were rendered and visually checked; text extraction alone was not used to
accept drawing tables.

## 1. Littelfuse `0451008.MRL`

Official 451/453 series data sheet, revision `GD`, dated `2025-12-01`:

- URL: <https://www.littelfuse.com/assetdocs/fuse-451-and-453-datasheet?assetguid=533cd5cc-956c-4243-867f-6ab5a62f6ba1>
- retrieved file: `Littelfuse-Fuse-451-453-Datasheet.pdf`;
- 4 pages, 491,885 bytes;
- SHA-256: `399d3cc9da991aa3192638f807fb568f137407d10a4b0d35d106a82b5c2bace2`.

PDF page 4 defines the part-number fields `0451` + amp code `008.` + quantity
code `M` (1000 pieces) + tape-and-reel code `R` + compliance suffix `L`, which
produces exact orderable `0451008.MRL`. PDF page 2 gives 8 A, 125 V maximum,
400 A at 32 VDC interrupting rating, 7.7 mOhm nominal cold resistance and
20.23 A2s nominal melting I2t. Page 3 states the standard 25%
continuous-current derating; page 4 states the `-55...+125 C` range.

## 2. Littelfuse `SMBJ18A`

Official SMBJ series data sheet, revision `JC v4`, dated `2025-07-04`:

- URL: <https://www.littelfuse.com/assetdocs/tvs-diodes-smbj-series-datasheet?assetguid=ba555e99-a12d-4f72-a0b6-86b06c67171e>
- retrieved file: `TVS-Diode-SMBJ-Datasheet.pdf`;
- 6 pages, 947,504 bytes;
- SHA-256: `d7df155be4b1f612085401e8c946f065e284d65a0e7de22b9225a7b73946e51b`.

PDF page 2 identifies exact unidirectional `SMBJ18A` and gives 18 V standoff,
20.0/22.1 V minimum/maximum breakdown, 29.2 V maximum clamp at 20.6 A and
600 W pulse power. PDF page 6 binds the orderable family to DO-214AA and 3000
pieces on 12 mm tape / 13 inch reel.

## 3. Molex `43045-0213`

Current official product page snapshot:

- canonical URL: <https://www.molex.com/en-us/products/part-detail/430450213>
- retrieved payload: `430450213.html`, 387,340 bytes;
- SHA-256: `d4afc5cdd0705422c61ff5b5698e3479f6e9e0c1022782af2fe41c8d51902d1c`.

The page binds numeric identity `430450213` to formatted orderable
`43045-0213`: two circuits, two rows, vertical through-hole header, gold mating
plating, 8.5 A maximum per contact, 600 V maximum, `-40...+125 C`, and 1.60 mm
recommended PCB thickness.

Official sales drawing `SD-43045-005`, revision `G1`:

- URL: <https://www.molex.com/content/dam/molex/molex-dot-com/products/automated/en-us/salesdrawingpdf/430/43045/430450213_sd.pdf>
- retrieved file: `430450213_sd.pdf`;
- 2 PDF pages (page 2 blank), 284,379 bytes;
- SHA-256: `85db6fbcbbd05643bfebded1b14e02911930151d0234b130d3711ee5fde78ec7`.

The page-1 ordering table maps `02` circuits and finish `B` to
`43045-0213`; finish `B` is select gold in the contact area and select matte tin
on solder tails.

## 4. Molex `43030-0038`

Current official product page snapshot:

- canonical URL: <https://www.molex.com/en-us/products/part-detail/430300038>
- retrieved payload: `430300038.html`, 384,338 bytes;
- SHA-256: `594fa3506fc506446c6a8256839d039a2eeea6b60378a3ff14c693d916db1717`.

The page binds numeric identity `430300038` to formatted orderable
`43030-0038`: female phosphor-bronze terminal, tin mating finish, reel form,
18 AWG / 0.75 mm2, 1.85 mm maximum insulation diameter and 8.5 A maximum per
contact.

Official sales drawing `SD-43030-XXXX`, revision `N10`, released
`2026-04-24`:

- URL: <https://www.molex.com/content/dam/molex/molex-dot-com/products/automated/en-us/salesdrawingpdf/430/43030/430300038_sd.pdf>
- retrieved file: `430300038_sd.pdf`;
- 1 page, 632,077 bytes;
- SHA-256: `87fd5d112565f429a63f4350e1ba37a889fba8310696d541124d460df5bb017d`.

The ordering table maps `43030-0038` to plating `A`, 18 AWG / 0.75 mm2 and
chain form; note 2 defines plating `A` as hot tin dip and note 10 fixes the
1.85 mm maximum insulation diameter.

## 5. Controlled boundary

The four exact orderables match
`PCB_PWR_INPUT_PROTECTION_QUALIFICATION_REV_A.json`; no family-member
substitution is accepted. `PWR-IPQ-001` may therefore be marked `PASS`.

Only `4/20` matrix rows are accepted. Documentary procurement identity is
closed without an incoming quarantine or sampling gate; every physical fuse,
connector/harness, transient, TVS, reverse-polarity, telemetry and final-release
row remains open. Routing, PCBA procurement and manufacturing release remain
false.
