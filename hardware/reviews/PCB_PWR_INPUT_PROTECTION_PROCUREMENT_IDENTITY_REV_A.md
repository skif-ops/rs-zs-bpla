# PCB-PWR input-protection documentary procurement identity

Status: `DOCUMENTARY PROCUREMENT IDENTITY PASS / NO RECEIVING HOLD / NOT FOR MANUFACTURE`

Configuration: `EVT-PRE-20 Rev.A`

## Decision

`PWR-IPQ-002` is a pre-purchase documentary gate. It is closed from current
manufacturer data sheets, product pages, drawings and exact-MPN supplier
catalogue records. No separate sample order, quarantine, package photography,
five-piece body sample, future lot/date code or certificate of conformance is
required for this gate.

The four exact parts may proceed directly to EVT kitting when the remaining
procurement gates permit. At receipt, ordinary commercial reconciliation may
use the existing PO or packing slip to identify an obvious MPN, quantity or
transit-damage discrepancy. It creates no new evidence package and is not an
input-protection qualification or release gate.

This decision does not infer electrical authenticity or fitness from a web
page. Assembly inspection, electrical end-of-line checks and physical rows
`PWR-IPQ-005` through `PWR-IPQ-020` retain the functional, thermal, fault and
transient confirmation. Routing, PCBA procurement and manufacturing release
remain blocked by their other open gates.

## Controlled documentary identity

| Exact MPN | Manufacturer authority | Supplier catalogue binding | Controlled selection |
|---|---|---|---|
| Littelfuse `0451008.MRL` | The [451/453 data sheet](https://www.littelfuse.com/assetdocs/fuse-451-and-453-datasheet?assetguid=533cd5cc-956c-4243-867f-6ab5a62f6ba1) binds the 8 A orderable, 125 VDC rating, 7.7 mOhm nominal cold resistance, 20.23 A²s nominal melting I²t, `F` plus `8A` marking reference and `MRL` tape-and-reel suffix. | [DigiKey exact-MPN page](https://www.digikey.com/en/products/detail/littelfuse-inc/0451008-MRL/700831) binds the catalogue entry to Littelfuse `0451008.MRL` and its reel/cut-tape order options. | Exact manufacturer and full MPN only; no adjacent 451 rating or ordering-suffix substitution. |
| Littelfuse `SMBJ18A` | The [SMBJ data sheet](https://www.littelfuse.com/assetdocs/tvs-diodes-smbj-series-datasheet?assetguid=ba555e99-a12d-4f72-a0b6-86b06c67171e) binds the unidirectional 18 V device, 20.0–22.1 V breakdown, 29.2 V maximum clamp, 600 W rating, `LT` code and cathode band. | [Mouser exact-MPN page](https://www.mouser.com/ProductDetail/Littelfuse/SMBJ18A?qs=zHiv0nsVGmq6qhYJ9exSJA%3D%3D) binds the catalogue entry to Littelfuse `SMBJ18A` and reel/cut-tape options. | `SMBJ18A` only; reject the bidirectional `SMBJ18CA` and all other voltage codes. |
| Molex `43045-0213` | The [Molex exact product page](https://www.molex.com/en-us/products/part-detail/430450213) binds the black two-circuit vertical header, tray packaging and 8.5 A maximum-current field. | [DigiKey exact numeric-MPN page](https://www.digikey.com/en/products/detail/molex/0430450213/1635000) binds `0430450213` to Molex and tray/small-quantity ordering. | Molex `43045-0213` only; leading-zero supplier notation is the same exact orderable. |
| Molex `43030-0038` | The [Molex exact product page](https://www.molex.com/en-us/products/part-detail/430300038) and [packaging drawing `PK-43030-001-001` Rev.B1](https://www.molex.com/content/dam/molex/molex-dot-com/products/automated/en-us/packagingdesigndrawing/430/43030/PK-43030-001-001.pdf) bind the 18 AWG / 0.75 mm² terminal and 12,000-piece reel. | [DigiKey](https://www.digikey.com/en/products/detail/molex/0430300038/6098601) and [Mouser](https://www.mouser.com/ProductDetail/Molex/43030-0038) bind their catalogue entries to the exact Molex part and reel/cut-tape or small-quantity options. | Molex `43030-0038` only; leading-zero supplier notation is the same exact orderable. |

## Two-week sourcing snapshot

The supplier pages displayed the following inventory on `2026-09-17`. The
controlled EVT-20 quantities include the BOM spare allowance.

| Exact MPN | EVT-20 quantity with spares | Supplier inventory displayed | Supplier standard lead time shown |
|---|---:|---:|---:|
| `0451008.MRL` | 30 | DigiKey 14,150 | 23 weeks |
| `SMBJ18A` | 25 | Mouser 12,758 | not recorded |
| `43045-0213` | 25 | DigiKey 4,507 | 17 weeks |
| `43030-0038` | 252 | DigiKey 670,806 | 8 weeks |

Displayed stock covered the controlled quantities when retrieved. Manufacturer
standard lead time is a replenishment field, not the dispatch time of stock
already displayed. Neither stock nor a generic ship-time statement guarantees
delivery to the project destination; the cart or quote must still confirm the
destination delivery date at order placement.

Manufacturer documents control technical identity and ratings. Supplier pages
control only the mapping between the seller's order entry and the exact
manufacturer MPN. They do not override a manufacturer data sheet or drawing.

## Purchase-order rule

Each order line shall state the manufacturer, exact MPN and `NO SUBSTITUTION`.
The buyer retains the supplier product URL or quotation line mapping the seller
entry to that exact MPN. Material is new and unused and is bought from the
manufacturer or an established component distributor.

Inventory, price, packaging option below a factory pack, ship date and delivery
date are volatile commercial fields. They are reconfirmed in the cart or quote
at PO placement against the two-week schedule; they are deliberately not frozen
as qualification facts.

## Receipt boundary

There is no input-protection quarantine or sampling gate:

- mandatory package/reel/tray photographs: none;
- mandatory body photographs: none;
- minimum inspected bodies per MPN/lot: `0`;
- mandatory manufacturer lot/date record: none;
- mandatory CoC: none;
- new receiving evidence package: none.

Existing commercial records may be used for routine PO/packing-slip and
quantity reconciliation. An obvious mismatch or transit damage is handled as a
normal procurement discrepancy; otherwise the parts proceed to kitting.

## Controlled machine record

`PCB_PWR_INPUT_PROTECTION_PROCUREMENT_IDENTITY_REV_A.json`

JSON SHA-256: `2b3acbc5bcee5b08bb1a45f009d75d57210592d8488f2e5dc29358c072a62250`

## Release boundary

- documentary identity gate `PWR-IPQ-002`: `PASS`;
- stand-alone identity-sample purchase: not required;
- receiving quarantine/photo/body-sample gate: not required;
- physical input-protection qualification: incomplete;
- PCBA procurement authorization: false;
- manufacturing release: false.
