#ifndef EVT_PRE_20_SIM_ORCHESTRATOR_H
#define EVT_PRE_20_SIM_ORCHESTRATOR_H
/*
 * Drives the dual-SIM controller (zs_dual_sim) with the Rev.A GPIO binding (evt_pre_20_dual_sim_gpio)
 * and the BG95 bridge (zs_dual_sim_bg95) from the comms task: safe-off recovery at boot, slot
 * selection, rail / mux / PWRKEY sequence, ICCID verification, link validation, and the graceful
 * switch to the other slot after repeated failures.  The parts that need the modem or the MQTT
 * session are handed back to the caller through the phase:
 *
 *   MODEM_BOOT       PWRKEY was pulsed: tick zs_bg95 until the modem answers, keep calling step()
 *   NEED_LINK        ICCID verified: bring the modem ONLINE (APN of the pending profile) and keep
 *                    calling step(); the orchestrator confirms the link and completes the switch
 *   ACTIVE           the slot is active; run the MQTT session; report failures with fail()
 *   CLOSE_TRANSPORT  a switch is in progress: stop traffic, close the session, call
 *                    transport_closed(), keep calling step()
 *   SAFE_OFF         nothing to start (no SIM present / both slots exhausted): modem off, retry
 *                    with start() later
 *   BUSY             GPIO sequence in progress: call step() again on the next tick
 *
 * Portable and host-tested (test_evt_pre_20_sim_orchestrator.c); no RTOS, no HAL.
 */
#include "evt_pre_20_dual_sim_gpio.h"
#include "zs_bg95.h"
#include "zs_dual_sim.h"

#include <stdbool.h>
#include <stdint.h>

#define EVT_PRE_20_SIM_MAX_BRINGUP_FAILURES 3u
#define EVT_PRE_20_SIM_MAX_LINK_FAILURES 3u      /* then the controller is asked to switch (subject to its hold) */
#define EVT_PRE_20_SIM_MODEM_ON_TIMEOUT_MS 15000u
#define EVT_PRE_20_SIM_GRACEFUL_OFF_TIMEOUT_MS 5000u

typedef enum {
  EVT_PRE_20_SIM_PHASE_BUSY = 0,
  EVT_PRE_20_SIM_PHASE_MODEM_BOOT,
  EVT_PRE_20_SIM_PHASE_NEED_LINK,
  EVT_PRE_20_SIM_PHASE_ACTIVE,
  EVT_PRE_20_SIM_PHASE_CLOSE_TRANSPORT,
  EVT_PRE_20_SIM_PHASE_SAFE_OFF
} evt_pre_20_sim_phase_t;

typedef struct {
  zs_dual_sim_t *controller;
  evt_pre_20_dual_sim_gpio_t *gpio;
  zs_bg95_t *modem;
  zs_dual_sim_slot_t preferred_slot;
  uint8_t profile;
  evt_pre_20_sim_phase_t phase;
  uint8_t bringup_failures[ZS_DUAL_SIM_SLOT_COUNT];   /* failures before ACTIVE, per slot */
  uint8_t link_failures[ZS_DUAL_SIM_SLOT_COUNT];      /* failures while ACTIVE, per slot; the controller's own
                                                         attempt budget resets on every (re)activation, so the
                                                         orchestrator keeps the count that spans the retries */
  bool transport_closed;
  bool want_start;                                    /* start() requested, waiting for SAFE_OFF */
  uint32_t pwrkey_ms, graceful_ms;
  uint32_t starts, switches, recoveries, retries;
} evt_pre_20_sim_orchestrator_t;

bool evt_pre_20_sim_orchestrator_init(evt_pre_20_sim_orchestrator_t *o, zs_dual_sim_t *controller,
                                      evt_pre_20_dual_sim_gpio_t *gpio, zs_bg95_t *modem,
                                      zs_dual_sim_slot_t preferred_slot, uint8_t profile);
/* Ask for a modem on the preferred slot (or the other one when the preferred is absent / exhausted). */
void evt_pre_20_sim_orchestrator_start(evt_pre_20_sim_orchestrator_t *o);
/* One scheduling step; call after zs_bg95_tick. Returns the phase the caller must act on. */
evt_pre_20_sim_phase_t evt_pre_20_sim_orchestrator_step(evt_pre_20_sim_orchestrator_t *o, uint32_t now_ms);
/* The MQTT session is closed and no traffic is pending (answer to CLOSE_TRANSPORT). */
void evt_pre_20_sim_orchestrator_transport_closed(evt_pre_20_sim_orchestrator_t *o);
/* A link failure on the active slot or during bring-up: retried on the same slot up to
   EVT_PRE_20_SIM_MAX_LINK_FAILURES times, then the controller is asked to switch (it may still hold). */
void evt_pre_20_sim_orchestrator_fail(evt_pre_20_sim_orchestrator_t *o, zs_dual_sim_failure_t failure, uint32_t now_ms);
/* Clears the bring-up failure counters (operator action or a long quiet period). */
void evt_pre_20_sim_orchestrator_reset_failures(evt_pre_20_sim_orchestrator_t *o);

#endif
