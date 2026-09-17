# PCB-PWR Rev.A input-protection qualification

Status: `CONTROLLED PLAN / F1 NATIVE VALUE ECO APPLIED / REPEAT ERC, PDF, HUMAN REVIEW AND PHYSICAL EVIDENCE PENDING / NOT FOR MANUFACTURE`

Configuration: `EVT-PRE-20 Rev.A`

This packet controls the PCB-PWR input fuse and TVS decision. The bounded F1
value-only ECO is applied without changing footprint, placement, topology, nets
or pad mapping. The previously accepted five-page source remains historical
evidence only; repeat commit-bound ERC/PDF evidence and a new independent human
hierarchy decision are required before any PCB assembly procurement.

## 1. Controlled decision

The prior signed native source and PDF contain F1 value `0451005.MRL`. That part
is rejected for the project 5 A continuous-current basis. The active native
schematic, PCB and their generators now contain `0451008.MRL`. Littelfuse specifies
a standard 25% derating for continuous operation in addition to the temperature
rerating curve:

- `5 A x 0.75 = 3.75 A`, below the project load;
- `7 A x 0.75 = 5.25 A`, leaving only 5% before the additional +70 C
  temperature rerating;
- `8 A x 0.75 = 6.0 A`, so `0451008.MRL` is the minimum selected candidate
  that provides a usable desk margin before the mandatory hot test.

The exact EVT qualification pair is:

| Function | Candidate | Controlled rating | State |
|---|---|---|---|
| F1 PCB input fuse | Littelfuse `0451008.MRL` | 8 A; 7.7 mOhm nominal cold resistance; 20.23 A²s nominal melting I²t; 400 A at 32 VDC interrupting rating | Native value ECO applied; repeat ERC/PDF/human review and physical qualification pending |
| D1 transient clamp | Littelfuse `SMBJ18A` | 18 V standoff; 20.0–22.1 V breakdown; 29.2 V maximum clamp at 20.6 A; 600 W at 10/1000 us | Selected for qualification; measured transient envelope pending |

At 5 A the fuse's nominal cold loss is:

`P = I²R = 5² x 0.0077 = 0.1925 W`.

The J1 `43045-0213` header and `43030-0038` 18 AWG / 0.75 mm² terminal each
publish a maximum of 8.5 A per contact. This does not release an 8 A continuous
system current. The operating envelope stays 5 A, and the complete
connector/crimp/wire path must pass the +70 C test.

## 2. Native-source interlock

This is a two-stage ECO gate:

1. The controlled BOM and qualification contract select `0451008.MRL` and
   prohibit procurement of `0451005.MRL`.
2. The bounded value-only native ECO changes F1 in the generator,
   `.kicad_sch` and `.kicad_pcb`. Independent semantic checks retain the exact
   F1 footprint, placement, topology, nets and pad mapping.

The existing commit-bound ERC, PDF and human acceptance remain the historical
record for the superseded 5 A value. They do not approve the active 8 A value.
Fresh KiCad 9 ERC, a new five-page PDF, source hashes and a repeat independent
hierarchy decision are mandatory.

Until then:

- no PCB-PWR PCBA procurement is authorized;
- no BOM line may claim `CONTROLLED` release for F1;
- `0451005.MRL` may appear only in historical/provenance text, never in an
  active native or generator value field;
- manufacturing release remains false.

## 3. TVS acceptance boundary

`SMBJ18A` is a pulse clamp, not a sustained-overvoltage regulator. Its
tabulated 29.2 V maximum clamp leaves 6.8 V to the 36 V absolute maximum input
of the selected buck regulators before layout overshoot and tolerance.

The qualification candidate limit is therefore:

- `<=32.0 V` measured at the protected node for every accepted battery and
  MPPT event;
- any measured value `>=36.0 V` is an immediate reject;
- sustained overvoltage must be prevented by the battery/BMS/MPPT architecture,
  not absorbed continuously by D1.

The final criterion may be tightened after the measured source impedance and
transient envelope are available. It may not be relaxed above the 36 V hard
ceiling.

## 4. Measurement boundary

The INA226 normal-operation calibration remains `200 uA/bit` for the released
5 A operating envelope. Its positive signed current range is approximately
`6.5534 A`. It is not the instrument for fuse-opening or fault-energy tests.

Every overload, short-circuit and TVS-coordination test above that range uses an
external calibrated current probe and oscilloscope. Firmware must not report a
register wrap or overflow as a plausible valid current.

## 5. Safe test sequence

Tests run in the order controlled by
`PCB_PWR_INPUT_PROTECTION_TEST_MATRIX_REV_A.csv`:

1. source control, sample identity and bounded native ECO;
2. repeat ERC/PDF/human hierarchy gate;
3. 25 C, +70 C and -40 C operating tests;
4. inrush and modem-burst tests;
5. overload, prospective-short and primary-fuse coordination using a
   current/energy-limited fixture;
6. connector/harness thermal and voltage-drop tests;
7. battery and MPPT transient capture;
8. bounded TVS pulse, reverse-polarity and TVS fail-short tests;
9. INA226 range/error-state verification;
10. independent evidence audit.

An unprotected direct short of an RB40 is prohibited. The test fixture must limit
available current and energy, provide remote shutdown, use a guarded enclosure
and capture source impedance before the fault is applied.

## 6. Release rule

The plan audit may pass while every physical test remains pending. Qualification
is complete only when all 20 rows are `PASS`, each row names an operator and
date, every required artifact has a SHA-256, the native F1 value equals
`0451008.MRL`, and repeat hierarchy evidence is accepted.

This packet never closes PCB-PWR routing, DIM-003, stackup/copper, DRC, CAM, DFM,
Review B or manufacturing release.

## 7. Primary evidence

- [Littelfuse 0451008 product page](https://www.littelfuse.com/products/fuses-overcurrent-protection/fuses/surface-mount-fuses/nano-2-fuses/451/0451008)
- [Littelfuse 451/453 series data sheet](https://www.littelfuse.com/assetdocs/fuse-451-and-453-datasheet?assetguid=533cd5cc-956c-4243-867f-6ab5a62f6ba1)
- [Littelfuse SMBJ18A product page](https://www.littelfuse.com/products/overvoltage-protection/tvs-diodes/surface-mount/smbj/smbj18a)
- [Littelfuse SMBJ series data sheet](https://www.littelfuse.com/assetdocs/tvs-diodes-smbj-series-datasheet?assetguid=ba555e99-a12d-4f72-a0b6-86b06c67171e)
- [Molex 43045-0213 product page](https://www.molex.com/en-us/products/part-detail/430450213)
- [Molex 43030-0038 product page](https://www.molex.com/en-us/products/part-detail/430300038)
