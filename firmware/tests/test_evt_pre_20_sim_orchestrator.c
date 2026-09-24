/* Dual-SIM orchestration on the Rev.A GPIO binding + BG95 bridge: boot recovery, slot 1 bring-up, retries,
   hold, graceful switch to slot 2 after the hold, exhausted slots, missing SIM. */
#include "evt_pre_20_sim_orchestrator.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

#define SLOT1_ICCID "89701012345678901234"
#define SLOT2_ICCID "89702012345678901234"

typedef struct {
  bool level[EVT_PRE_20_PIN_COUNT];
  bool modem_pwrkey;          /* the modem driver's own PWRKEY line (zs_bg95 hal) */
  unsigned pwrkey_writes, rail_on, rail_off;
  char uart[4096]; size_t used;
} mock_t;

static bool gpio_write(void *ctx, evt_pre_20_pin_id_t pin, bool high) {
  mock_t *m = ctx;
  if (pin >= EVT_PRE_20_PIN_COUNT) return false;
  m->level[pin] = high;
  if (pin == EVT_PRE_20_PIN_EN_MODEM) {           /* PCB-PWR: PWR_GOOD follows the rail; a dead rail cannot hold STATUS */
    m->level[EVT_PRE_20_PIN_PWR_GOOD] = high;
    if (high) m->rail_on++; else { m->rail_off++; m->level[EVT_PRE_20_PIN_CELL_STATUS] = false; }
  }
  if (pin == EVT_PRE_20_PIN_CELL_PWRKEY_CMD) m->pwrkey_writes++;
  return true;
}
static bool gpio_read(void *ctx, evt_pre_20_pin_id_t pin, bool *high) { mock_t *m = ctx; if (pin >= EVT_PRE_20_PIN_COUNT) return false; *high = m->level[pin]; return true; }
static int uart_write(void *ctx, unsigned ch, const uint8_t *d, size_t n) { mock_t *m = ctx; (void)ch; if (m->used + n >= sizeof(m->uart)) return -1; memcpy(&m->uart[m->used], d, n); m->used += n; m->uart[m->used] = 0; return 0; }
static void hal_gpio(void *ctx, unsigned id, bool level) { mock_t *m = ctx; (void)id; m->modem_pwrkey = level; m->pwrkey_writes++; }

static const zs_bg95_apn_profile_t profiles[] = {{"25001", "", true, true}, {"25002", "backup.apn", true, false}};

static void modem_online(zs_bg95_t *modem, const char *iccid) {
  strcpy(modem->network_settings.iccid, iccid);
  strcpy(modem->network_settings.imsi, "250011234567890");
  strcpy(modem->network_settings.apn, "network.apn");
  strcpy(modem->network_settings.local_address, "10.10.0.2");
  strcpy(modem->network_settings.gateway, "10.10.0.1");
  strcpy(modem->network_settings.primary_dns, "1.1.1.1");
  modem->network_settings.valid = true;
  modem->selected_apn_profile = 0u;
  modem->command_pending = false;
  modem->mqtt_connected = true; modem->mqtt_open = true;
  modem->state = ZS_BG95_ONLINE;
}

/* Runs the orchestrator from wherever it is up to ACTIVE, playing the modem side; returns the time reached. */
static uint32_t bring_to_active(evt_pre_20_sim_orchestrator_t *o, mock_t *m, zs_bg95_t *modem, const char *iccid, uint32_t t) {
  evt_pre_20_sim_phase_t ph;
  unsigned spins = 0u;
  for (;;) {
    ph = evt_pre_20_sim_orchestrator_step(o, t);
    assert(++spins < 400u);
    switch (ph) {
      case EVT_PRE_20_SIM_PHASE_ACTIVE: return t;
      case EVT_PRE_20_SIM_PHASE_BUSY: t += 10u; break;                                   /* GPIO settle / pulse timing */
      case EVT_PRE_20_SIM_PHASE_MODEM_BOOT:
        t += 800u; zs_bg95_tick(modem, t);                                                /* 700 ms PWRKEY -> AT_SYNC */
        if (modem->state >= ZS_BG95_AT_SYNC) { m->level[EVT_PRE_20_PIN_CELL_STATUS] = true; modem_online(modem, iccid); modem->state = ZS_BG95_AT_SYNC; }
        break;
      case EVT_PRE_20_SIM_PHASE_NEED_LINK: modem->state = ZS_BG95_ONLINE; t += 5u; break;
      case EVT_PRE_20_SIM_PHASE_CLOSE_TRANSPORT: evt_pre_20_sim_orchestrator_transport_closed(o); t += 5u; break;
      case EVT_PRE_20_SIM_PHASE_SAFE_OFF: assert(!"unexpected SAFE_OFF");
    }
    /* the modem answers QPOWD with STATUS low a little later */
    if (modem->state == ZS_BG95_POWERING_OFF) m->level[EVT_PRE_20_PIN_CELL_STATUS] = false;
    /* the hard recovery pulse (1000 ms) also drops STATUS */
    if (o->gpio->fallback_pulse_active && (uint32_t)(t - o->gpio->fallback_pulse_started_ms) >= 1000u) m->level[EVT_PRE_20_PIN_CELL_STATUS] = false;
  }
}

int main(void) {
  static mock_t m;
  zs_dual_sim_t controller;
  evt_pre_20_dual_sim_gpio_t gpio;
  zs_bg95_t modem;
  evt_pre_20_sim_orchestrator_t o;
  zs_hal_port_t io = {0};
  uint32_t t = 100u;

  memset(&m, 0, sizeof(m));
  io.ctx = &m; io.uart_write = uart_write; io.gpio_write = hal_gpio;
  assert(zs_dual_sim_init(&controller, SLOT1_ICCID, SLOT2_ICCID));
  assert(evt_pre_20_dual_sim_gpio_init(&gpio, &m, gpio_write, gpio_read, NULL));
  zs_bg95_init(&modem, &io, 1u, 2u, NULL);
  assert(zs_bg95_configure_auto_network(&modem, profiles, 2u));
  assert(!evt_pre_20_sim_orchestrator_init(&o, &controller, &gpio, &modem, ZS_DUAL_SIM_SLOT_NONE, 0u));
  assert(evt_pre_20_sim_orchestrator_init(&o, &controller, &gpio, &modem, ZS_DUAL_SIM_SLOT_1, 0u));

  /* boot with the modem still on (STATUS high) and both SIMs present: recovery pulses PWRKEY, then SAFE_OFF */
  m.level[EVT_PRE_20_PIN_CELL_STATUS] = true; m.level[EVT_PRE_20_PIN_EN_MODEM] = true; m.level[EVT_PRE_20_PIN_PWR_GOOD] = true;
  m.level[EVT_PRE_20_PIN_SIM1_DET] = true; m.level[EVT_PRE_20_PIN_SIM2_DET] = true;
  assert(evt_pre_20_sim_orchestrator_step(&o, t) == EVT_PRE_20_SIM_PHASE_BUSY);            /* fallback pulse started */
  assert(m.level[EVT_PRE_20_PIN_CELL_PWRKEY_CMD]);
  t += 1100u; m.level[EVT_PRE_20_PIN_CELL_STATUS] = false;
  assert(evt_pre_20_sim_orchestrator_step(&o, t) == EVT_PRE_20_SIM_PHASE_SAFE_OFF);        /* recovered, nothing requested yet */
  assert(zs_dual_sim_state(&controller) == ZS_DUAL_SIM_STATE_SAFE_OFF && !m.level[EVT_PRE_20_PIN_EN_MODEM] && !m.level[EVT_PRE_20_PIN_SIM_MUX_EN]);

  /* start on slot 1 */
  evt_pre_20_sim_orchestrator_start(&o);
  t = bring_to_active(&o, &m, &modem, SLOT1_ICCID, t);
  assert(zs_dual_sim_active_slot(&controller) == ZS_DUAL_SIM_SLOT_1 && !m.level[EVT_PRE_20_PIN_SIM_MUX_SEL] && m.level[EVT_PRE_20_PIN_SIM_MUX_EN]);
  assert(o.starts == 1u && o.switches == 0u && strstr(m.uart, "AT\r\n") != NULL);
  {
    const uint32_t activated = controller.last_activation_ms;

    /* three link failures inside the hold: retried on the same slot each time (brownout recovery), no switch */
    for (unsigned i = 0u; i < 3u; i++) {
      evt_pre_20_sim_orchestrator_fail(&o, ZS_DUAL_SIM_FAILURE_SUSTAINED_LINK_LOSS, t += 60000u);
      assert(zs_dual_sim_state(&controller) == ZS_DUAL_SIM_STATE_NEEDS_SAFE_OFF);
      m.level[EVT_PRE_20_PIN_CELL_STATUS] = true;                                        /* the modem is still up when the link died */
      t = bring_to_active(&o, &m, &modem, SLOT1_ICCID, t);
      assert(zs_dual_sim_active_slot(&controller) == ZS_DUAL_SIM_SLOT_1);
    }
    assert(o.retries == 3u && o.switches == 0u && o.recoveries >= 3u);

    /* the hold restarts with every activation: after 15 min on the last one the 4th failure switches gracefully
       to slot 2 (session closed, QPOWD, mux re-selected) */
    assert(controller.last_activation_ms > activated);
    t = controller.last_activation_ms + ZS_DUAL_SIM_MIN_HOLD_MS + 1000u;
  }
  {
    const size_t uart_before = m.used;
    evt_pre_20_sim_orchestrator_fail(&o, ZS_DUAL_SIM_FAILURE_SUSTAINED_LINK_LOSS, t);
    assert(o.switches == 1u);
    assert(evt_pre_20_sim_orchestrator_step(&o, t) == EVT_PRE_20_SIM_PHASE_CLOSE_TRANSPORT);
    assert(evt_pre_20_sim_orchestrator_step(&o, t + 1u) == EVT_PRE_20_SIM_PHASE_CLOSE_TRANSPORT);   /* waits for the caller */
    evt_pre_20_sim_orchestrator_transport_closed(&o);
    modem_online(&modem, SLOT1_ICCID);                                                    /* graceful shutdown needs a live modem */
    t = bring_to_active(&o, &m, &modem, SLOT2_ICCID, t + 2u);
    assert(strstr(m.uart + uart_before, "AT+QPOWD") != NULL);
    assert(zs_dual_sim_active_slot(&controller) == ZS_DUAL_SIM_SLOT_2 && m.level[EVT_PRE_20_PIN_SIM_MUX_SEL]);
  }

  /* a wrong card on the pending slot counts as a bring-up failure; three of them exhaust the slot */
  {
    evt_pre_20_sim_orchestrator_t o2; zs_dual_sim_t c2; evt_pre_20_dual_sim_gpio_t g2; zs_bg95_t md2;
    static mock_t m2;
    memset(&m2, 0, sizeof(m2)); io.ctx = &m2;
    assert(zs_dual_sim_init(&c2, SLOT1_ICCID, SLOT2_ICCID));
    assert(evt_pre_20_dual_sim_gpio_init(&g2, &m2, gpio_write, gpio_read, NULL));
    zs_bg95_init(&md2, &io, 1u, 2u, NULL);
    assert(zs_bg95_configure_auto_network(&md2, profiles, 2u));
    assert(evt_pre_20_sim_orchestrator_init(&o2, &c2, &g2, &md2, ZS_DUAL_SIM_SLOT_2, 0u));
    m2.level[EVT_PRE_20_PIN_SIM1_DET] = true; m2.level[EVT_PRE_20_PIN_SIM2_DET] = true;
    evt_pre_20_sim_orchestrator_start(&o2);
    t = 500u;
    for (unsigned i = 0u; i < 3u; i++) {                                                 /* slot 2 preferred, but it holds the slot-1 card */
      evt_pre_20_sim_phase_t ph;
      unsigned spins = 0u;
      do {
        ph = evt_pre_20_sim_orchestrator_step(&o2, t);
        if (ph == EVT_PRE_20_SIM_PHASE_MODEM_BOOT) { t += 800u; zs_bg95_tick(&md2, t); if (md2.state >= ZS_BG95_AT_SYNC) { m2.level[EVT_PRE_20_PIN_CELL_STATUS] = true; modem_online(&md2, SLOT1_ICCID); md2.state = ZS_BG95_AT_SYNC; } }
        else t += 10u;
        if (g2.fallback_pulse_active && (uint32_t)(t - g2.fallback_pulse_started_ms) >= 1000u) m2.level[EVT_PRE_20_PIN_CELL_STATUS] = false;
        assert(++spins < 400u);
      } while (o2.bringup_failures[1] == i);
      assert(ph != EVT_PRE_20_SIM_PHASE_ACTIVE);
    }
    assert(o2.bringup_failures[1] == 3u);
    /* slot 2 exhausted: the next start falls back to slot 1 (which carries the matching card) */
    t = bring_to_active(&o2, &m2, &md2, SLOT1_ICCID, t);
    assert(zs_dual_sim_active_slot(&c2) == ZS_DUAL_SIM_SLOT_1 && o2.starts == 4u);
    evt_pre_20_sim_orchestrator_reset_failures(&o2);
    assert(o2.bringup_failures[1] == 0u);
  }

  /* no SIM at all: SAFE_OFF and nothing driven */
  {
    evt_pre_20_sim_orchestrator_t o3; zs_dual_sim_t c3; evt_pre_20_dual_sim_gpio_t g3; zs_bg95_t md3;
    static mock_t m3;
    memset(&m3, 0, sizeof(m3)); io.ctx = &m3;
    assert(zs_dual_sim_init(&c3, SLOT1_ICCID, SLOT2_ICCID));
    assert(evt_pre_20_dual_sim_gpio_init(&g3, &m3, gpio_write, gpio_read, NULL));
    zs_bg95_init(&md3, &io, 1u, 2u, NULL);
    assert(evt_pre_20_sim_orchestrator_init(&o3, &c3, &g3, &md3, ZS_DUAL_SIM_SLOT_1, 0u));
    evt_pre_20_sim_orchestrator_start(&o3);
    for (t = 0u; t < 200u; t += 10u) (void)evt_pre_20_sim_orchestrator_step(&o3, t);
    assert(evt_pre_20_sim_orchestrator_step(&o3, t) == EVT_PRE_20_SIM_PHASE_SAFE_OFF && !m3.level[EVT_PRE_20_PIN_EN_MODEM] && o3.starts == 0u);
  }

  printf("sim orchestrator: starts %u switches %u retries %u recoveries %u\n", o.starts, o.switches, o.retries, o.recoveries);
  printf("evt_pre_20 sim orchestrator tests passed\n");
  return 0;
}
