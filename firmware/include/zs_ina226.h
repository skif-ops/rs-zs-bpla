#ifndef ZS_INA226_H
#define ZS_INA226_H

#include "zs_hal_port.h"
#include <stdbool.h>
#include <stdint.h>

#define ZS_INA226_ADDR_REV_A 0x40u
#define ZS_INA226_CONFIG_REV_A 0x4127u
#define ZS_INA226_CAL_REV_A 2560u
#define ZS_INA226_CURRENT_LSB_UA 200
#define ZS_INA226_POWER_LSB_MW 5u

typedef enum {
  ZS_INA226_STATUS_OK = 0u,
  ZS_INA226_STATUS_IO = 1u << 0,
  ZS_INA226_STATUS_ID = 1u << 1,
  ZS_INA226_STATUS_CAL = 1u << 2,
  ZS_INA226_STATUS_DATA = 1u << 3,
  ZS_INA226_STATUS_CONFIG = 1u << 4
} zs_ina226_status_t;

typedef struct {
  const zs_hal_port_t *io;
  unsigned bus;
  uint8_t address;
  uint16_t configuration;
  uint16_t calibration;
  bool configured;
} zs_ina226_t;

typedef struct {
  uint32_t bus_mv;
  int32_t current_ua;
  uint32_t power_mw;
  uint8_t status;
  bool valid;
} zs_ina226_measurement_t;

void zs_ina226_init(zs_ina226_t *dev, const zs_hal_port_t *io, unsigned bus, uint8_t address);
uint8_t zs_ina226_probe_and_configure(zs_ina226_t *dev);
uint8_t zs_ina226_read(zs_ina226_t *dev, zs_ina226_measurement_t *out);

#endif
