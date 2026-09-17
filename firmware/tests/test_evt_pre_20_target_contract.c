#include "evt_pre_20_board_pins.h"
#include "evt_pre_20_clock_policy.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

_Static_assert(EVT_PRE_20_PIN_ASSIGNMENT_COUNT == 67u, "unexpected target pin count");
_Static_assert(EVT_PRE_20_EXTERNAL_HSE_ALLOWED == 0, "external HSE is forbidden");
_Static_assert(EVT_PRE_20_LOW_SPEED_REFERENCE_HZ == UINT32_C(32768),
               "low-speed reference mismatch");
_Static_assert(EVT_PRE_20_RUNTIME_CLOCK_FREQUENCIES_RELEASED == 0,
               "unmeasured clock profiles cannot be released");

static const evt_pre_20_pin_contract_t *find_pin(const char *net) {
  for (size_t i = 0u; i < EVT_PRE_20_PIN_ASSIGNMENT_COUNT; ++i) {
    if (strcmp(evt_pre_20_pin_contract[i].net, net) == 0) {
      return &evt_pre_20_pin_contract[i];
    }
  }
  return NULL;
}

static void assert_pin(const char *net,
                       char port,
                       uint8_t gpio_pin,
                       uint8_t package_pin,
                       const char *signal,
                       int8_t alternate_function,
                       evt_pre_20_pin_direction_t direction) {
  const evt_pre_20_pin_contract_t *pin = find_pin(net);
  assert(pin != NULL);
  assert(pin->gpio_port == port);
  assert(pin->gpio_pin == gpio_pin);
  assert(pin->lqfp100_pin == package_pin);
  assert(strcmp(pin->cubemx_signal, signal) == 0);
  assert(pin->alternate_function == alternate_function);
  assert(pin->direction == direction);
}

int main(void) {
  for (size_t i = 0u; i < EVT_PRE_20_PIN_ASSIGNMENT_COUNT; ++i) {
    for (size_t j = i + 1u; j < EVT_PRE_20_PIN_ASSIGNMENT_COUNT; ++j) {
      assert(strcmp(evt_pre_20_pin_contract[i].net, evt_pre_20_pin_contract[j].net) != 0);
      assert(evt_pre_20_pin_contract[i].lqfp100_pin != evt_pre_20_pin_contract[j].lqfp100_pin);
      assert(evt_pre_20_pin_contract[i].gpio_port != evt_pre_20_pin_contract[j].gpio_port ||
             evt_pre_20_pin_contract[i].gpio_pin != evt_pre_20_pin_contract[j].gpio_pin);
    }
  }

  assert_pin("PDM_CLK", 'E', 9u, 37u, "MDF1_CCK0", 6, EVT_PRE_20_DIRECTION_OUT);
  assert_pin("MIC_WAKE", 'A', 8u, 67u, "GPIO", EVT_PRE_20_AF_GPIO,
             EVT_PRE_20_DIRECTION_IN);
  assert_pin("AAD_CFG", 'A', 15u, 77u, "GPIO", EVT_PRE_20_AF_GPIO,
             EVT_PRE_20_DIRECTION_OUT);
  assert_pin("LORA_DIO1", 'C', 2u, 17u, "GPIO", EVT_PRE_20_AF_GPIO,
             EVT_PRE_20_DIRECTION_IN);
  assert_pin("LORA_TXEN", 'B', 15u, 54u, "GPIO", EVT_PRE_20_AF_GPIO,
             EVT_PRE_20_DIRECTION_OUT);
  assert_pin("LORA_RXEN", 'D', 8u, 55u, "GPIO", EVT_PRE_20_AF_GPIO,
             EVT_PRE_20_DIRECTION_OUT);
  assert_pin("CELL_PWRKEY_CMD", 'D', 11u, 58u, "GPIO", EVT_PRE_20_AF_GPIO,
             EVT_PRE_20_DIRECTION_OUT);
  assert_pin("CELL_STATUS", 'D', 13u, 60u, "GPIO", EVT_PRE_20_AF_GPIO,
             EVT_PRE_20_DIRECTION_IN);
  assert_pin("SIM_MUX_SEL", 'E', 0u, 97u, "GPIO", EVT_PRE_20_AF_GPIO,
             EVT_PRE_20_DIRECTION_OUT);
  assert_pin("SIM_MUX_EN", 'E', 2u, 1u, "GPIO", EVT_PRE_20_AF_GPIO,
             EVT_PRE_20_DIRECTION_OUT);
  assert_pin("SIM1_DET", 'E', 3u, 2u, "GPIO", EVT_PRE_20_AF_GPIO,
             EVT_PRE_20_DIRECTION_IN);
  assert_pin("SIM2_DET", 'E', 5u, 4u, "GPIO", EVT_PRE_20_AF_GPIO,
             EVT_PRE_20_DIRECTION_IN);
  assert_pin("I2C2_SCL", 'B', 13u, 52u, "I2C2_SCL", 4,
             EVT_PRE_20_DIRECTION_BIDIR_OD);
  assert_pin("I2C2_SDA", 'B', 14u, 53u, "I2C2_SDA", 4,
             EVT_PRE_20_DIRECTION_BIDIR_OD);
  assert_pin("LSE_IN", 'C', 14u, 8u, "RCC_OSC32_IN", EVT_PRE_20_AF_RCC,
             EVT_PRE_20_DIRECTION_IN);

  assert(strcmp(evt_pre_20_pin_contract[EVT_PRE_20_PIN_CELL_PWRKEY_CMD].net,
                "CELL_PWRKEY_CMD") == 0);
  assert(strcmp(evt_pre_20_pin_contract[EVT_PRE_20_PIN_CELL_STATUS].net,
                "CELL_STATUS") == 0);
  assert(strcmp(evt_pre_20_pin_contract[EVT_PRE_20_PIN_SIM_MUX_SEL].net,
                "SIM_MUX_SEL") == 0);
  assert(strcmp(evt_pre_20_pin_contract[EVT_PRE_20_PIN_SIM_MUX_EN].net,
                "SIM_MUX_EN") == 0);

  puts("evt_pre_20_target_contract_tests: PASS");
  return 0;
}
