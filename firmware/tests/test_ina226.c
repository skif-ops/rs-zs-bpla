#include "zs_ina226.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

typedef struct {
  uint16_t regs[256];
  bool fail_read;
  bool fail_write;
  uint8_t last_addr;
  unsigned last_bus;
} mock_i2c_t;

static int mr(void *ctx, unsigned bus, uint8_t addr, uint8_t reg, uint8_t *data, size_t len) {
  mock_i2c_t *m = ctx;
  if (m->fail_read || !data || len != 2u) return -1;
  m->last_bus = bus;
  m->last_addr = addr;
  const uint16_t v = m->regs[reg];
  data[0] = (uint8_t)(v >> 8);
  data[1] = (uint8_t)(v & 0xffu);
  return 0;
}

static int mw(void *ctx, unsigned bus, uint8_t addr, uint8_t reg, const uint8_t *data, size_t len) {
  mock_i2c_t *m = ctx;
  if (m->fail_write || !data || len != 2u) return -1;
  m->last_bus = bus;
  m->last_addr = addr;
  m->regs[reg] = (uint16_t)(((uint16_t)data[0] << 8) | data[1]);
  return 0;
}

int main(void) {
  mock_i2c_t m;
  memset(&m, 0, sizeof(m));
  m.regs[0xFE] = 0x5449u;
  m.regs[0xFF] = 0x2260u;

  zs_hal_port_t io = {.ctx = &m, .i2c_mem_read = mr, .i2c_mem_write = mw};
  zs_ina226_t dev;
  zs_ina226_init(&dev, &io, 2u, ZS_INA226_ADDR_REV_A);
  assert(zs_ina226_probe_and_configure(&dev) == ZS_INA226_STATUS_OK);
  assert(dev.configured);
  assert(m.regs[0x00] == ZS_INA226_CONFIG_REV_A);
  assert(m.regs[0x05] == ZS_INA226_CAL_REV_A);
  assert(m.last_addr == 0x40u && m.last_bus == 2u);

  /* 12.750 V / 1.25 mV = 10200 counts. 1.000 A / 200 uA = 5000.
     12.750 W / 5 mW = 2550. */
  m.regs[0x02] = 10200u;
  m.regs[0x04] = 5000u;
  m.regs[0x03] = 2550u;
  zs_ina226_measurement_t x;
  assert(zs_ina226_read(&dev, &x) == ZS_INA226_STATUS_OK);
  assert(x.valid);
  assert(x.bus_mv == 12750u);
  assert(x.current_ua == 1000000);
  assert(x.power_mw == 12750u);

  m.regs[0x04] = (uint16_t)(int16_t)-2500;
  assert(zs_ina226_read(&dev, &x) == ZS_INA226_STATUS_OK);
  assert(x.current_ua == -500000);

  m.regs[0x00] = 0u;
  assert(zs_ina226_read(&dev, &x) == ZS_INA226_STATUS_CONFIG);
  assert(!x.valid && !dev.configured);

  m.regs[0x00] = ZS_INA226_CONFIG_REV_A;
  m.regs[0x05] = ZS_INA226_CAL_REV_A;
  dev.configured = true;
  m.regs[0x05] = 0u;
  assert(zs_ina226_read(&dev, &x) == ZS_INA226_STATUS_CAL);
  assert(!x.valid && !dev.configured);

  m.regs[0x05] = ZS_INA226_CAL_REV_A;
  dev.configured = true;
  m.fail_read = true;
  assert(zs_ina226_read(&dev, &x) == ZS_INA226_STATUS_IO);
  assert(!x.valid);

  puts("zs_ina226_tests: OK");
  return 0;
}
