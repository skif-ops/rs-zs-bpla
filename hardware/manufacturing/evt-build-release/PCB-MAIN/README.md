# PCB-MAIN EVT-PRE-20 8-layer production candidate

Primary source: **PCB-MAIN COMPLETE-105 Rev.B, 8 copper layers**. This directory imports the exact PCB-MAIN order package from `EVT_PRE_20_ПЛАТЫ_ЗАКАЗ_И_МОНТАЖ_20261013_REV_D6.zip` and adds fresh 2026-10-16 verification.

The package contains all eight copper Gerbers (`F.Cu`, `In1.Cu` through `In6.Cu`, `B.Cu`), mask/paste/silkscreen/profile, plated and non-plated drill, IPC-D-356, BOM, positions, assembly drawings, KiCad source and the 76-site POFV order control.

Fresh KiCad 10.0.6 checks: ERC 0 violations; DRC 0 errors, 0 unconnected items and 30 warnings (7 dangling-via and 23 silk-over-copper).

Status: **HOLD**. Fabrication requires selected-stack dielectric/impedance confirmation, POFV acceptance, Altium antenna-warning disposition, upload DFM, Review B and first-article controls.
