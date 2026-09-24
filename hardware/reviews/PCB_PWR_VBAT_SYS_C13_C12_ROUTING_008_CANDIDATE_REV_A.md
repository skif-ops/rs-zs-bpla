# PCB-PWR VBAT_SYS C13-to-C12 routing candidate 008

This isolated candidate connects central bulk capacitor `C13.1` to the lower
buck local input capacitor `C12.1`. It adds two F.Cu `VBAT_SYS` segments at the
controlled 3.0 mm / 4 A branch width: 10.2 mm vertically through the empty
lower corridor and 3.525 mm horizontally into `C12.1`. The applied candidate
007 board is the frozen predecessor.

The static copper screen reports 0.875 mm minimum edge clearance, limited by
the same-net route endpoint next to `C12.2` foreign copper. The conservative
one-way 4 A drop screen at 35 µm copper and +70 °C is 10.785319 mV. This is a
DC-only calculation; current crowding, thermal rise, transient/fault behaviour
and assembled temperature remain unqualified.

The upper branch from C13 to `C11.1` crosses the constrained U2 region and is
deliberately deferred to a separate candidate. The U2 `VBAT_SYS` control-pin
branch, ground return completion, global planes, Review B, CAM, DFM and physical
EVT evidence also remain outside this candidate.

The candidate is byte-bound by
`tools/generate_pcb_pwr_vbat_sys_c13_c12_routing_008_candidate_rev_a.py` and
independently checked by
`tools/audit_pcb_pwr_vbat_sys_c13_c12_routing_008_candidate_rev_a.py`.
Commit-bound CI and KiCad 9 comparative DRC are pending. The authoritative
board is unchanged, and application is not authorized.

After the machine gate passes, the exact decision tokens are:

- `ACCEPT_PCB_PWR_VBAT_SYS_C13_C12_ROUTING_008_SUBGATE`
- `REJECT_PCB_PWR_VBAT_SYS_C13_C12_ROUTING_008_SUBGATE`
