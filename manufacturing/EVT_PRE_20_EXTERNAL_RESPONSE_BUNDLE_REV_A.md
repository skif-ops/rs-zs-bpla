# EVT-PRE-20 external-response bundle — Rev.A

Status: `SUPERSEDED / EVT ENGINEERING BASELINE ACCEPTED / NOT FOR MANUFACTURE`

Decision date: `2026-09-21`

The original outbound request set is retained only for traceability. The
customer owns PCB/PCBA checkout and authorized use of public manufacturer data,
standard engineering processes and calculated values for this test program.
Therefore a factory e-mail, signed response or named-site quotation is no longer
an engineering prerequisite.

The controlling replacement is:

- `hardware/reviews/EVT_ENGINEERING_MANUFACTURING_BASELINE_REV_A.json`;
- `hardware/reviews/EVT_ENGINEERING_MANUFACTURING_BASELINE_REV_A.md`;
- `hardware/PCB_PWR_CURRENT_GEOMETRY_BASIS_REV_A.csv`;
- `hardware/HARNESS_EVT_LENGTH_BASIS_REV_A.csv`.

## Program and lot boundary

The configuration remains `EVT-PRE-20`: every production lot is controlled as
20 stations. The procurement program contains two independent EVT-20 lots plus
one bench station, 41 stations total. Each EVT-20 lot receives its own reserve
pool; the bench station does not create a third reserve pool. Serial allocation
is reserved in `LOT_SERIAL_REGISTER_LOT2_AND_BENCH.csv`; individual travellers
for the second lot and bench station must be issued before build.

## Closed response registers

| Packet | Rows closed | External reply required |
|---|---:|---:|
| PCB-MAIN stackup/impedance | 22/22 | no |
| PCB-MAIN assembly/DFM/stencil | 14/14 | no |
| PCB-PWR stackup/copper | 24/24 | no |
| PCB-MIC DFM/acoustic process | 9/9 | no |
| Harness process/capability | 16/16 | no |

The `Responder` fields identify the project engineering decision, not a factory
reply. No supplier statement has been fabricated.

## Order boundary

- Full PCBA remains the primary order track; bare-board rows are alternatives
  and must not be added to the same quantity total.
- At checkout the customer must select the stackup, copper, finish, impedance
  and assembly options from the controlled baseline.
- Any upload parser or DFM error, mismatch in stackup/copper, or proposed source
  edit is a stop condition and returns as a controlled ECO.
- PCB-MAIN and PCB-PWR contain accepted partial-routing subgates, but routing is
  incomplete. DRC, CAM review and independent Review B are mandatory before
  their files may be uploaded.
- PCB-MIC likewise requires current native DRC/CAM evidence and Review B.
- Two PCBA first articles per build lot and harness first-off crimp qualification
  precede the remainder of that lot.

## What remains open

External reply waiting is closed. The following are intentionally not waived:

1. remaining native routing, DRC and CAM evidence;
2. independent Review B and manufacturing-release signatures;
3. first-article inspection and functional smoke tests;
4. PCB-PWR current/thermal and protection qualification;
5. harness continuity, crimp pull, resistance, strain, `+70 C`/`-40 C`, I2C
   and PDM/AAD checks;
6. full assembled EVT electrical, RF, acoustic and environmental validation.

At series transfer, repeat supplier/site, DFM, process-capability, tooling and
environmental qualification. The EVT closure is not a serial-production waiver.

## Archive control

The deterministic historical archive may still be built with:

```bash
python tools/build_evt_pre_20_packages.py
```

It is evidence of the controlled source set, not an order or a manufacturing
release.
