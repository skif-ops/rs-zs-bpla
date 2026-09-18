# EVT system OTS documentary purchase identity — Rev.A

Status: `DOCUMENTARY PURCHASE IDENTITY PASS / PHYSICAL VALIDATION DURING ASSEMBLY, EOL AND EVT / NOT A PRODUCTION RELEASE`

Configuration: `EVT-PRE-20 Rev.A`

## Decision

The selected EVT-20 lot is the qualification batch for the eight exact OTS system
items below. A separate pre-order qualification unit is not required. Before order,
the controlled chain is:

1. official manufacturer product page and current data sheet or technical manual;
2. exact manufacturer and MPN in the BOM, RFQ and purchase order;
3. supplier catalogue record or quotation that maps the seller entry to that MPN;
4. `NO SUBSTITUTION` plus order-time confirmation of quantity, price and delivery to
   the destination.

Receipt is ordinary commercial reconciliation of PO line, packing slip, quantity and
obvious transit damage. A conforming shipment has no blanket quarantine, mandatory
photography, fixed body-count inspection, future lot/date-code capture or CoC gate.
An obviously discrepant or unsafe unit is isolated, and the scope expands only when
the discrepancy is systemic. Applicable battery transport documents remain required.

This gate controls identity for purchase. It does not infer installed fitness from a
web page. Electrical, thermal, mechanical, RF, seal and environmental confirmation
remains in the normal assembly, EOL and EVT flow.

## Exact controlled set

| BOM item | Exact manufacturer / MPN | Manufacturer authority | Supplier catalogue binding | Open physical route |
|---|---|---|---|---|
| `BAT1` | RELiON `RB40` | [RELiON exact product page](https://www.relionbattery.com/products/lithium/rb40) | [Ameresco Solar exact model page](https://www.amerescosolar.com/relion-rb40-lithium-iron-phosphate-128v-40ah-battery) | every-unit polarity/OCV at installation; capacity, DCIR, BMS and cold-system EVT |
| `PV1` | SLD Tech / Solarland `SLP080S-12M` | [SLD Tech exact product page](https://sldtechinc.com/80w-12v-monocrystalline-solar-panel-s/) | [MrSolar exact model page](https://www.mrsolar.com/solarland-slp080s-12m-80-watt-solar-panel/) | installation damage/Voc; IV, insulation, wet leakage, cold Voc and mechanical EVT |
| `MPPT1` | Victron Energy `SCC075010060R` | [Victron 75/10 technical specifications](https://www.victronenergy.com/media/pg/Manual_SmartSolar_MPPT_75-10_up_to_100-20/en/technical-specifications.html) | [Ameresco Solar exact article page](https://www.amerescosolar.com/victron-charge-controller-mppt-75-10-scc075010060r), [DigiKey exact catalogue entry](https://www.digikey.com/en/products/detail/spartan-power/SCC075010060R/16035431) | profile export, VE.Smart binding, reverse/quiescent current, transient, thermal and cold EVT |
| `MPPT-TEMP` | Victron Energy `SBS050150200` | [Victron technical specifications](https://www.victronenergy.com/media/pg/Smart_Battery_Sense/en/technical-specifications.html) | [SVB exact manufacturer-number page](https://www.svb24.com/en/victron-smart-battery-sense-voltage-and-temperature-sensor-12-24-v.html) | RB40 retention stack, accuracy, pairing, cutoff/reconnect and network-retention EVT |
| `ANT-CELL` | Taoglas `G30.B.108111` | [Taoglas exact product page](https://www.taoglas.com/product/olympian-g30-2g3g4g-lte-antenna/) | [RS exact-MPN page](https://no.rs-online.com/web/p/multi-band-antennas/2884458) | quote records ordered cable construction; installed seal, VSWR, loss, attach and coexistence |
| `ANT-GNSS` | Taoglas `AA.166.A.301111` | [Taoglas exact product page](https://www.taoglas.com/product/aa-166-a-301111-ulysses-miniature-magnetic-mount-beidougpsglonassgalileo-antenna-with-3000mm-rg-174-smam/) and [data sheet](https://www.taoglas.com/datasheets/AA.166.301111.pdf) | [RS exact-MPN page](https://ie.rs-online.com/web/p/multi-band-antennas/2884328) | installed current, sensitivity, PPS, seal and coexistence |
| `ANT-LORA` | Taoglas `TI.89.B.2111W` | [Taoglas exact product page](https://www.taoglas.com/product/ti-89-b-ism-lora-860-930-mhz-white-terminal-mount-antenna-2dbi-smam-fixed-straight-waterproof-enclosure/) and [data sheet](https://www.taoglas.com/datasheets/TI.89.B.2111W.pdf) | [Newark exact-MPN page](https://www.newark.com/taoglas/ti-89-b-2111w/external-antenna-910-920mhz-wht/dp/15AN2917) | installed VSWR, conducted power/sensitivity, coexistence and RU868 radiated campaign |
| `RF-PIGTAIL` | Taoglas `CAB.0243` | [Taoglas exact product page](https://www.taoglas.com/product/cab-0243-i-pex-mhf-i-u-fl-to-150mm-1-13-cable-to-smafbk-st-waterproof/) and [SPE-24-8-147-A](https://www.taoglas.com/datasheets/CAB.0243.pdf) | [DigiKey exact-MPN page](https://www.digikey.com/en/products/detail/taoglas-limited/CAB-0243/24770240) | every installed cable continuity/polarity/route; mate, bend, torque, seal, insertion loss and VSWR |

The G30 manufacturer page contains inconsistent RG-316 versus RG-178 wording. The
record deliberately does not choose between them. The exact `G30.B.108111` MPN is
fixed, and the ordered cable construction must be stated on the supplier quote.

## Non-binding sourcing snapshot

Supplier pages observed on `2026-09-18` showed numerical coverage for the four RF
chain items and the Smart Battery Sense. The MPPT DigiKey entry showed zero stock,
and full RB40/panel/controller quantity coverage was not established. Therefore the
complete power chain and the complete EVT-20 system order are **not** commercially
released. Stock, price and delivery are volatile and must be reconfirmed in the cart
or quote for the actual destination; no displayed quantity guarantees two-week
delivery.

## Controlled machine record

`EVT_SYSTEM_OTS_PROCUREMENT_IDENTITY_REV_A.json`

JSON SHA-256: `6d985fa9260b47a3f52b21a615f146f424be8ccfe3d7c4c74030a913454ac7ad`

## Release boundary

- documentary identity of the eight OTS lines: `PASS`;
- stand-alone pre-order qualification unit: not required;
- receiving quarantine/photo/body-count/lot-date/CoC gate: not required;
- actual quotation and destination delivery confirmation: open;
- physical assembly/EOL/EVT qualification: open;
- PCB, harness, mechanics, purchase and manufacturing release: blocked by their
  remaining gates.
