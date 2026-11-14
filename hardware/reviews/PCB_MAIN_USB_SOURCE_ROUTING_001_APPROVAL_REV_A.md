# PCB-MAIN USB MCU source routing 001 approval — Rev.A

Decision: `ACCEPT_USB_MCU_SOURCE_ROUTING_SUBGATE`  
Reviewer: `Скиф`  
Date: `2026-09-20`

The user input `ответ подтверждаю. далее идем по наиболее целесообразным
решениям решения одобряю нужно максимально быстро завершать работу по проекту.
дополнительные запросы только в крайнем случае` explicitly confirms the
pending decision. For this bounded subgate it is normalized to the exact token
`ACCEPT_USB_MCU_SOURCE_ROUTING_SUBGATE`.

This approval is bound to evidence commit
`8fdb96c684a935cadeda6ae6ec8c78db32cbd610`, tree
`4fcd1f3a8aeafe9628fabacc03e328ae0c5928d3`, and candidate-board SHA-256
`76f7a6ef35b3f168e8b32f1ff97e650404546e6b839ddd7fdde9a061ede3d7a5`.

The authorized change is exactly the local U1-to-R91/R92 source segment:

| Net | Endpoints | Layer | Length, mm |
|---|---|---|---:|
| `USB_DP_U1` | `U1.71` — `R91.1` | `F.Cu` | 4.178827774173 |
| `USB_DM_U1` | `U1.70` — `R92.1` | `F.Cu` | 4.178827774173 |

The pair uses the public engineering basis `0.1537/0.2032 mm`, adds 13 signal
segments and no signal via. The only additional allowed delta relocates the
existing `GND_DIGITAL` segment/via identified by timestamps
`fb9ade5d-8496-4617-9d20-390d44c347c4` and
`bbd350c1-609d-43b7-9dd0-824ee009466f`; net and via geometry remain unchanged.

The proposal passed CI #559 and PCB Native #286. Comparative KiCad 9 DRC held
violations at `232 -> 232`, introduced zero new errors, and reduced unconnected
items from `429` to `427`. Artifact `10611360741` has digest
`sha256:9cf6e29f613e84f1cea0234987bc14e82467567e042d53c67d97abae761b7cfb`.

This approval does not complete the main-connector or cellular USB segments,
accept a final fabricator stackup or production impedance tolerance, close
Review B, authorize CAM/DFM, or release manufacturing.
