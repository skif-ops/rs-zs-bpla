# Power monitor task (INA226 on I2C2) — 2026-09-24

`app_power` samples the Rev.A battery monitor (INA226 @0x40, `zs_ina226`: probe/ID/config/calibration, bus
voltage, current, power) every `APP_POWER_PERIOD_MS` (1 s) over `bsp_i2c` (I2C2 PB13/PB14, 100 kHz from HSI16,
blocking register access with a 20 ms timeout) and keeps one `zs_power_t` snapshot:

- `battery_bus_mv` / `battery_mv` — INA226 bus voltage; `battery_current_ma` (signed), `battery_power_mw`;
- `battery_pct` — linear between `APP_BATTERY_EMPTY_MV` (11.8 V) and `APP_BATTERY_FULL_MV` (14.2 V), a 4S LiFePO4
  assumption until the pilot pack is final;
- `monitor_status` — 0 while the last read was valid, otherwise the `zs_ina226_status_t` bits of the failed read
  (values stay the last good sample). Five consecutive failures re-probe the device after an I2C re-init.

Consumers: heartbeat key 6 (`comms_fill_heartbeat`), detection events (`pl_emit` copies the snapshot into key 10,
INA226 fields full-packet only per the MQTT ICD), self-test `power_good` detail (bus mV; PWR_GOOD/PWR_FAULT still
decide PASS/FAIL), console `power`.

Placeholders removed: `battery_pct 100 / battery_mv 12000 / monitor_status 1` of B1/B2.

Target Release: FLASH 154 KB, RAM 83.7 % (power task stack 512 words on the heap).

Open on hardware: I2C2 pull-ups and bus idle level with the modem rail off, INA226 shunt value vs
`ZS_INA226_CAL_REV_A`, sign convention of the current (charge vs discharge), the battery map.
