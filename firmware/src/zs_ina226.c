#include "zs_ina226.h"

#include <stddef.h>

#define INA226_REG_BUS_V 0x02u
#define INA226_REG_POWER 0x03u
#define INA226_REG_CURRENT 0x04u
#define INA226_REG_CAL 0x05u
#define INA226_REG_MANUFACTURER_ID 0xFEu
#define INA226_REG_DIE_ID 0xFFu
#define INA226_MANUFACTURER_ID 0x5449u
#define INA226_DIE_ID_MASK 0xFFF0u
#define INA226_DIE_ID_VALUE 0x2260u

static int read_reg(const zs_ina226_t *dev, uint8_t reg, uint16_t *value) {
  if (!dev || !dev->io || !dev->io->i2c_mem_read || !value) return -1;
  uint8_t b[2] = {0u, 0u};
  if (dev->io->i2c_mem_read(dev->io->ctx, dev->bus, dev->address, reg, b, sizeof(b)) != 0) return -1;
  *value = (uint16_t)(((uint16_t)b[0] << 8) | b[1]);
  return 0;
}

static int write_reg(const zs_ina226_t *dev, uint8_t reg, uint16_t value) {
  if (!dev || !dev->io || !dev->io->i2c_mem_write) return -1;
  const uint8_t b[2] = {(uint8_t)(value >> 8), (uint8_t)(value & 0xffu)};
  return dev->io->i2c_mem_write(dev->io->ctx, dev->bus, dev->address, reg, b, sizeof(b));
}

void zs_ina226_init(zs_ina226_t *dev, const zs_hal_port_t *io, unsigned bus, uint8_t address) {
  if (!dev) return;
  dev->io = io;
  dev->bus = bus;
  dev->address = address;
  dev->calibration = ZS_INA226_CAL_REV_A;
  dev->configured = false;
}

uint8_t zs_ina226_probe_and_configure(zs_ina226_t *dev) {
  if (!dev || !dev->io) return ZS_INA226_STATUS_IO;

  uint16_t manufacturer = 0u;
  uint16_t die = 0u;
  if (read_reg(dev, INA226_REG_MANUFACTURER_ID, &manufacturer) != 0 ||
      read_reg(dev, INA226_REG_DIE_ID, &die) != 0) {
    dev->configured = false;
    return ZS_INA226_STATUS_IO;
  }
  if (manufacturer != INA226_MANUFACTURER_ID ||
      (die & INA226_DIE_ID_MASK) != INA226_DIE_ID_VALUE) {
    dev->configured = false;
    return ZS_INA226_STATUS_ID;
  }

  if (write_reg(dev, INA226_REG_CAL, dev->calibration) != 0) {
    dev->configured = false;
    return ZS_INA226_STATUS_IO;
  }

  uint16_t calibration = 0u;
  if (read_reg(dev, INA226_REG_CAL, &calibration) != 0) {
    dev->configured = false;
    return ZS_INA226_STATUS_IO;
  }
  if (calibration != dev->calibration || calibration == 0u) {
    dev->configured = false;
    return ZS_INA226_STATUS_CAL;
  }

  dev->configured = true;
  return ZS_INA226_STATUS_OK;
}

uint8_t zs_ina226_read(zs_ina226_t *dev, zs_ina226_measurement_t *out) {
  if (!out) return ZS_INA226_STATUS_DATA;
  out->bus_mv = 0u;
  out->current_ua = 0;
  out->power_mw = 0u;
  out->status = ZS_INA226_STATUS_DATA;
  out->valid = false;

  if (!dev || !dev->configured) {
    out->status = ZS_INA226_STATUS_CAL;
    return out->status;
  }

  uint16_t bus_raw = 0u;
  uint16_t current_raw_u = 0u;
  uint16_t power_raw = 0u;
  uint16_t cal_raw = 0u;
  if (read_reg(dev, INA226_REG_CAL, &cal_raw) != 0 ||
      read_reg(dev, INA226_REG_BUS_V, &bus_raw) != 0 ||
      read_reg(dev, INA226_REG_CURRENT, &current_raw_u) != 0 ||
      read_reg(dev, INA226_REG_POWER, &power_raw) != 0) {
    out->status = ZS_INA226_STATUS_IO;
    return out->status;
  }
  if (cal_raw != dev->calibration || cal_raw == 0u) {
    dev->configured = false;
    out->status = ZS_INA226_STATUS_CAL;
    return out->status;
  }

  /* INA226 LSBs: bus=1.25 mV, current=200 uA for Rev.A calibration,
     power=25*Current_LSB=5 mW. */
  out->bus_mv = ((uint32_t)bus_raw * 125u + 50u) / 100u;
  out->current_ua = (int32_t)(int16_t)current_raw_u * ZS_INA226_CURRENT_LSB_UA;
  out->power_mw = (uint32_t)power_raw * ZS_INA226_POWER_LSB_MW;
  out->status = ZS_INA226_STATUS_OK;
  out->valid = true;
  return out->status;
}
