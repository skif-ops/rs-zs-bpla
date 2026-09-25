#ifndef ZS_STATION_PARAMS_H
#define ZS_STATION_PARAMS_H
/*
 * Runtime station parameters set remotely by CMD_SET_PARAMS (MQTT_TLS_ICD_v0_1 addendum D, table 2): the whitelist
 * with ranges and defaults, whole-command validation (nothing is applied unless every entry is known and in range)
 * and a double-slot NOR record (version + CRC-32, the newer valid slot wins, a commit writes the other slot and
 * reads it back).  The server keeps the same table in station/command_codec.py (STATION_PARAMS).  Portable.
 */
#include "zs_command.h"
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

typedef enum {
  ZS_PARAM_HEARTBEAT_PERIOD_S = 1,
  ZS_PARAM_MIC_CHANNEL = 2,
  ZS_PARAM_EVENT_UPDATE_WINDOWS = 3,
  ZS_PARAM_COMMS_DEGRADED_AFTER = 4,
  ZS_PARAM_GSM_PROBE_S = 5,
  ZS_PARAM_LISTEN_DWELL_S = 6
} zs_param_id_t;

#define ZS_PARAM_COUNT 6u
#define ZS_STATION_PARAMS_RECORD_BYTES 48u
#define ZS_STATION_PARAMS_REJECT_BASE 0x0100u   /* ACK detail: REJECTED 0x0100 | param_id */

typedef struct {
  uint32_t version;                 /* 0 = defaults, never stored */
  int32_t value[ZS_PARAM_COUNT];    /* index = id - 1 */
} zs_station_params_t;

typedef struct {
  void *ctx;
  bool (*read)(void *ctx, uint8_t slot, uint32_t offset, uint8_t *data, size_t size);
  bool (*erase)(void *ctx, uint8_t slot);
  bool (*write)(void *ctx, uint8_t slot, uint32_t offset, const uint8_t *data, size_t size);
} zs_station_params_io_t;

typedef enum {
  ZS_STATION_PARAMS_OK = 0,
  ZS_STATION_PARAMS_NOT_FOUND,      /* no valid slot: defaults returned */
  ZS_STATION_PARAMS_IO_ERROR,
  ZS_STATION_PARAMS_VERIFY_FAILED
} zs_station_params_result_t;

void zs_station_params_defaults(zs_station_params_t *p);
int32_t zs_station_params_get(const zs_station_params_t *p, zs_param_id_t id);
bool zs_station_params_range(zs_param_id_t id, int32_t *min, int32_t *max, int32_t *def);
/* Validates the whole command against the table and builds the resulting set (reset first, then the entries).
   Returns 0 on success, otherwise ZS_STATION_PARAMS_REJECT_BASE | the first offending id; *out is untouched then. */
uint16_t zs_station_params_apply_command(const zs_station_params_t *current, const zs_set_params_command_t *cmd,
                                         zs_station_params_t *out);
zs_station_params_result_t zs_station_params_load(const zs_station_params_io_t *io, zs_station_params_t *out);
/* Stores `p` with version = current + 1 into the slot not holding the current record; p->version is updated. */
zs_station_params_result_t zs_station_params_commit(const zs_station_params_io_t *io, zs_station_params_t *p);
#endif
