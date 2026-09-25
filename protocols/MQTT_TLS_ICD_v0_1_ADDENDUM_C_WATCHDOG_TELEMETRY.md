# ICD GSM/LTE MQTT/TLS v0.1 — Addendum C: watchdog telemetry in the heartbeat (2026-09-25)

Статус: DRAFT. Дополняет §3.2 (heartbeat schema 2, ключ 13 — карта детектора) ключами 12–14. Карта остаётся
необязательной; сервер читает её с умолчаниями, поэтому прошивки без новых ключей декодируются как
`reset_cause = UNKNOWN`, `watchdog_missed = 0`.

| Key | Field | Encoding |
|---:|---|---|
| 12 | reset_cause | uint: причина текущей загрузки — 0 неизвестна, 1 питание/BOR, 2 NRST, 3 программный, 4 IWDG, 5 WWDG, 6 low-power, 7 option bytes |
| 13 | watchdog_missed | uint16: маска задач, переставших отмечаться перед сбросом по IWDG (бит = задача: 1 audio, 2 dsp, 3 comms, 4 ble, 5 power, 6 lora, 7 gnss, 8 rec — запись предыстории, аддендум B); 0 — нет |
| 14 | params_version | uint32: версия набора параметров, действующего на станции (аддендум D, `CMD_SET_PARAMS`; 0 — умолчания). Добавлен 2026-09-25; прошивки без ключа декодируются как 0 |

Источник: аппаратный сторожевой таймер станции (`app_watchdog`, `zs_task_watch`) — супервизор кормит IWDG только
пока все задачи отмечаются в окне 10 с; при зависании маска пишется в backup-регистр TAMP и попадает в первый
heartbeat после сброса. Прошивка: `zs_detector_health_t.reset_cause/watchdog_missed`; сервер:
`DetectorHealth.reset_cause/watchdog_missed_tasks`. Проверка: `firmware/tests/test_heartbeat_telemetry.c`,
`server/tools/test_firmware_packet.py`.
