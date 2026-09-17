# PCB-PWR input-protection procurement identity

Status: `PREPURCHASE DOCUMENTARY IDENTITY PASS / FIRST-LOT RECEIVING INSPECTION PENDING / NOT FOR MANUFACTURE`

Configuration: `EVT-PRE-20 Rev.A`

## Decision

No separate engineering-sample purchase is required for identity checking.
The exact components may be bought as part of the controlled EVT test-batch
order when the other procurement gates permit. The first received lot supplies
the physical samples for `PWR-IPQ-002`; it stays quarantined until the incoming
identity record passes.

Internet evidence closes only the pre-purchase documentary subgate. It cannot
state the lot/date code of a future shipment and cannot replace inspection of
the delivered reel, tray, cut tape or distributor package. Electrical,
transient, thermal, routing, PCBA procurement and manufacturing gates remain
open.

## Internet evidence and expected identity

| Exact MPN | Online physical/marking evidence | Factory packaging | Receipt acceptance |
|---|---|---|---|
| Littelfuse `0451008.MRL` | The [official 451/453 family photo](https://cdn2.webdamdb.com/1280_zgItXhA5UB36gelf.jpg?1780344435) is representative only. The [official data sheet](https://www.littelfuse.com/assetdocs/fuse-451-and-453-datasheet?assetguid=533cd5cc-956c-4243-867f-6ab5a62f6ba1) says the body carries brand plus ampere rating and shows the `F`/rating layout. Therefore `F` plus `8A` is the expected exact-rating marking; this is a derived expectation because the drawing itself uses a 7 A example. | 1,000 pieces, 12 mm tape and reel, ordering fields `0451` + `008.` + `M` + `R` + `L`. | Body `F` + `8A`; label/paperwork must state `0451008.MRL` and preserve date/lot traceability. Body marking alone does not identify the suffix or lot. |
| Littelfuse `SMBJ18A` | The [official SMBJ family photo](https://cdn2.webdamdb.com/1280_6zIX8CKqMpw652t7.jpg?1732720291) shows another voltage code and is representative only. The [official data sheet](https://www.littelfuse.com/assetdocs/tvs-diodes-smbj-series-datasheet?assetguid=ba555e99-a12d-4f72-a0b6-86b06c67171e) gives exact device code `LT`. The marking system gives trace format `YMXXX`: year, month, three-character lot. A cathode band is required for the unidirectional part. `BT` is the bidirectional `SMBJ18CA` and is rejected. | 3,000 pieces, 12 mm tape on 13-inch reel, EIA RS-481. | Every inspected body must show `LT`, legible `YMXXX` and the cathode band; label/paperwork must state `SMBJ18A`. |
| Molex `43045-0213` | [Exact official product photo](https://www.molex.com/content/dam/molex/molex-dot-com/products/manual/en-us/images/430/43045/0430450213_hires.jpg?wid=480&hei=327), SHA-256 `d0fdbe0b053d81cc0001bc228c8a30ef07962d9f3b6902f4518d1d037419d49c`. | Molex currently states `Tray`; UPC `800754370066`. | Black two-circuit dual-row vertical geometry must match the official image/drawing. Full MPN and date/lot are accepted from the tray or authorized-distributor trace record, not inferred from the body. |
| Molex `43030-0038` | [Exact official product photo](https://www.molex.com/content/dam/molex/molex-dot-com/products/manual/en-us/images/430/43030/0430300038_hires.jpg?wid=480&hei=327), SHA-256 `3964a86c3efa3975f59f4ed95a92d85532617434f98f59f4ed95eff79cb32`. An [exact-MPN reel photo](https://www.customconnectorkits.com/cdn/shop/products/43030-0038__42466.1676073238.1200.1200.jpg?v=1686744312&width=760) is retained as third-party illustration only, never as qualification authority. | [Official drawing `PK-43030-001-001` Rev.B1](https://www.molex.com/content/dam/molex/molex-dot-com/products/automated/en-us/packagingdesigndrawing/430/43030/PK-43030-001-001.pdf): 12,000 pieces on a 24-inch reel, product-label location shown, seven reels per carton. Drawing SHA-256 `2f60beee920157c12547322ae81cfcf13d62e084180fb67c3b0d9d1df38efb86`; UPC `889056413237`. | Terminal geometry must match the official image/drawing. Exact MPN and date/lot must come from the reel or authorized-distributor trace record. |

The illustrative Molex reel photo is useful only for recognizing the package
and label layout. Its visible lot/date belongs to somebody else's historical
reel and must never be copied into the EVT receiving record.

## Purchase-channel rule

Use the exact MPN from the manufacturer or a manufacturer-listed authorized
distributor. The purchase order must require date/lot traceability on the
manufacturer label, distributor label, packing slip, invoice or certificate.
Cut tape and distributor repack are acceptable only when this trace chain is
preserved.

Current exact-MPN catalogue examples include:

- [DigiKey `0451008.MRL`](https://www.digikey.ca/en/products/detail/littelfuse-inc/0451008-MRL/700831): exact MPN, tape/reel and cut-tape ordering, 1,000-piece manufacturer pack;
- [DigiKey `0430450213`](https://www.digikey.com/en/products/detail/molex/0430450213/1635000): exact Molex numeric MPN and tray packaging, with small-quantity ordering;
- [Newark `43030-0038`](https://www.newark.com/molex/43030-0038/contact-socket-18awg-crimp/dp/56AC9968): exact MPN and advertised date/lot traceability.

Marketplace or broker stock without an authorized chain of custody, unlabeled
loose parts, adjacent family members and unsegregated mixed lots are rejected.

## First-lot receiving gate

Before any material is released from quarantine to EVT kitting or assembly:

1. Photograph 100% of received reels, trays and shipping packages.
2. Inspect at least five bodies per MPN per date/lot, or all bodies when fewer
   than five are present.
3. Record PO, supplier, manufacturer, exact MPN, quantity, date/lot, country of
   origin when present, factory pack versus repack, photo hashes, inspector,
   UTC date, disposition and storage location.
4. Capture the package label in full, the fuse `F` + `8A` marking, and the TVS
   `LT` + `YMXXX` marking with cathode band. For Molex parts, bind the geometry
   photo and package label in one receiving record.
5. Reject missing/illegible traceability, marking mismatch, unexplained
   relabeling, unsegregated mixed lots, or packaging damage/contamination.

`PWR-IPQ-002` therefore remains `PENDING_PHYSICAL_TEST`, but its pre-purchase
documentary subgate is complete. It will pass using the actual EVT test-batch
receipt; no sample-only PO is needed.

## Controlled machine record

`PCB_PWR_INPUT_PROTECTION_PROCUREMENT_IDENTITY_REV_A.json`

JSON SHA-256: `f6baf0cc053396ef98d91d28b3f52c4839f7fb4d345a49f30cc3ef073dd532ae`

## Release boundary

- stand-alone identity-sample purchase: not required;
- first received lot released to EVT kitting: no, pending inspection;
- physical qualification: incomplete;
- PCBA procurement authorization: false;
- manufacturing release: false.
