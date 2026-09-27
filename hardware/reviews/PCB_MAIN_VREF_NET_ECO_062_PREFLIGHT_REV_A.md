# PCB-MAIN VREF bypass net correction — candidate 062 (2026-09-27)

## Finding

The approved MCU pin authority assigns U1 pin 20 (`VREF+`) to
`3V3_DIGITAL`, with C10 100 nF and C11 1 µF as its local bypass. The
candidate 061 PCB has U1.20 on `3V3_DIGITAL` but C10.1 and C11.1 on an
otherwise isolated `VREF+` net. Their apparent single DRC open is only
the separation **between the two capacitors**. Joining them without a
source would leave the intended reference bypass unpowered.

The MCU schematic places two `VREF+` labels on the capacitor positive
pins while the pin authority and U1.20 use `3V3_DIGITAL`. The passive
support authority CSV also still names `VREF+` for C10/C11 and the routing
authority lists it as a separate power rail. These records need alignment
before any application to the authoritative design.

## Isolated correction

Candidate 062 changes only the two capacitor labels in a copy of the MCU
schematic and the corresponding two PCB pad nets to `3V3_DIGITAL`.
C11.1 joins C9.1 and C10.1 joins C8.1 on F.Cu; each 0.25 mm segment is
1.25 mm long. No new via or placement change. The shape-screened minimum
other-net copper clearance is 0.30 mm, and both lines lie inside the
In1.Cu `GND_DIGITAL` zone outline. Input PCB SHA-256:
`b733b350b14dcbad0c62e91f7b58a715a891b418bdeac28d17f88277e724b4d0`.
Generated PCB SHA-256:
`ae099f301e6dff1d93cb67141d0b28c416d8cad86b6f46eb120c9e2d0553be43`.

The KiCad 9 native schematic ERC and filled-board comparative DRC are
pending. Do not reduce the confirmed 80 open connections before they run.
At application time, correct the passive support/routing authority and
regenerate schematic-to-PCB net parity from the same decision. Local
decoupling loop and analog-reference noise still require Review B.

No authoritative PCB-MAIN 003 file is modified; manufacturing release
remains blocked.
