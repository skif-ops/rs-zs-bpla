# PCB-PWR Review B R4: KiCad 10 parity record

The accompanying JSON is the original Rev E KiCad 10.0.6 `--schematic-parity`
output. The CSV gives an indexed disposition for **each of its 251 records**;
`Index`, `Type`, `Item_UUID`, and `Description` are copied from that JSON.
The Rev E package generator checks this one-to-one correspondence and hashes
both files as inputs. A pinned KiCad 9.0.9 run records its own parity result in
the package. KiCad 9 emits 189 records because it omits the 62 empty board
Datasheet field warnings that KiCad 10 emits.

| Disposition | Records | Decision |
|---|---:|---|
| Hierarchical net name prefix | 171 | Same terminal net name; independent electrical audit PASS |
| U5 NC pad 4 | 1 | Intentionally unconnected |
| Empty board Datasheet field | 62 | Metadata only; schematic field retained |
| Value field | 9 | Synchronize against controlled BOM in a separate ECO |
| Exclude-from-BOM attribute | 8 | R5/R9/R13/R14/R15 are DNP and NT1–NT3 are copper-only; synchronize schematic attributes in a separate ECO |

No physical connectivity difference is identified. The 17 Value/BOM metadata
items remain open and parity is **diagnostic, not PASS**. Neither this record nor
the primary electrical audit is a human Review B signature.
