# PCB-PWR VBAT_SYS shunt-to-bulk routing candidate 007

This isolated candidate links `RSH1.2` to `C13.1` on F.Cu. The accepted
PCB-PWR 006 board is the frozen predecessor. The new copper consists of a
3.0 mm long, 1.0 mm wide pad escape and a 1.0 mm long, 4.0 mm wide expansion.
The neighbouring `RSH1.4` Kelvin pickup remains a separate net. No vias,
planes, footprints, pad/net assignments, layer definitions or outline change.

The one-way 5 A drop screen at 35 µm copper and +70 °C is 9.577128 mV.
This is a DC-only calculation. Track thermal rise, shunt Kelvin error,
surge/fault current and assembled temperature remain open. Routing from C13
to `C11`, `C12` and the upstream control pin remains outside this candidate.

The static clearance screen and byte-bound candidate generation are audited by
`tools/audit_pcb_pwr_vbat_sys_shunt_bulk_routing_007_candidate_rev_a.py`.
Commit-bound KiCad 9 comparative DRC passed at source commit `d962bf7`,
CI #718 and PCB Native #366: 85 → 85 violations with unchanged severity/type
counts, 108 → 107 unconnected items. PCB Native artifact `10769511337` has
digest `sha256:ed71910195c912c4bd1fba46088e3d48869c9bee2e20dd5055f86a1cd4ad04fb`.
The authoritative board is unchanged. Acceptance and application of this exact candidate, full routing,
Review B, CAM, DFM, physical EVT and manufacturing release remain open.
