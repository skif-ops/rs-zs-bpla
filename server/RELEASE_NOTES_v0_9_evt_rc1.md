# Server 0.9.0 EVT RC1

- Protocol 1.4 decoder accepts time-quality and 3+1 spatial blocks.
- TDOA accepts only HIGH time quality. Legacy packets retain the PPS compatibility rule.
- Localization explicitly reports SINGLE_DOA, TWO_STATION_COARSE, HYBRID_3_2D5D, FULL_3D or CORRIDOR.
- Four collinear stations never imply FULL_3D.

This release does not claim hardware or field localization PASS.
