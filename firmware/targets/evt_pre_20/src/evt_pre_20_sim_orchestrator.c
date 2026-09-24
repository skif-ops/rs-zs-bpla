#include "evt_pre_20_sim_orchestrator.h"
#include "zs_dual_sim_bg95.h"

#include <string.h>

static unsigned idx(zs_dual_sim_slot_t s) { return s == ZS_DUAL_SIM_SLOT_2 ? 1u : 0u; }
static zs_dual_sim_slot_t other(zs_dual_sim_slot_t s) { return s == ZS_DUAL_SIM_SLOT_1 ? ZS_DUAL_SIM_SLOT_2 : ZS_DUAL_SIM_SLOT_1; }
static bool present(const zs_dual_sim_t *c, zs_dual_sim_slot_t s) { return c->presence[idx(s)].stable_present; }
static bool usable(const evt_pre_20_sim_orchestrator_t *o, zs_dual_sim_slot_t s) {
  return present(o->controller, s) && o->bringup_failures[idx(s)] < EVT_PRE_20_SIM_MAX_BRINGUP_FAILURES;
}
static bool complete(evt_pre_20_sim_orchestrator_t *o, zs_dual_sim_action_t a, bool ok, uint32_t now_ms) {
  return zs_dual_sim_complete_action(o->controller, a, ok, now_ms);
}

bool evt_pre_20_sim_orchestrator_init(evt_pre_20_sim_orchestrator_t *o, zs_dual_sim_t *controller,
                                      evt_pre_20_dual_sim_gpio_t *gpio, zs_bg95_t *modem,
                                      zs_dual_sim_slot_t preferred_slot, uint8_t profile) {
  if (!o || !controller || !gpio || !modem || (preferred_slot != ZS_DUAL_SIM_SLOT_1 && preferred_slot != ZS_DUAL_SIM_SLOT_2) ||
      profile >= ZS_DUAL_SIM_MAX_PROFILES)
    return false;
  memset(o, 0, sizeof(*o));
  o->controller = controller; o->gpio = gpio; o->modem = modem;
  o->preferred_slot = preferred_slot; o->profile = profile;
  o->phase = EVT_PRE_20_SIM_PHASE_BUSY;
  return true;
}

void evt_pre_20_sim_orchestrator_start(evt_pre_20_sim_orchestrator_t *o) { if (o) o->want_start = true; }
void evt_pre_20_sim_orchestrator_transport_closed(evt_pre_20_sim_orchestrator_t *o) { if (o) o->transport_closed = true; }
void evt_pre_20_sim_orchestrator_reset_failures(evt_pre_20_sim_orchestrator_t *o) {
  if (!o) return;
  memset(o->bringup_failures, 0, sizeof(o->bringup_failures));
  memset(o->link_failures, 0, sizeof(o->link_failures));
}

/* The slot the next start goes to: preferred when usable, else the other, else none. */
static zs_dual_sim_slot_t pick_slot(const evt_pre_20_sim_orchestrator_t *o) {
  if (usable(o, o->preferred_slot)) return o->preferred_slot;
  if (usable(o, other(o->preferred_slot))) return other(o->preferred_slot);
  return ZS_DUAL_SIM_SLOT_NONE;
}

/* Bring-up did not reach ACTIVE on slot `s`: count it and force the safe-off recovery. */
static void bringup_failed(evt_pre_20_sim_orchestrator_t *o, zs_dual_sim_slot_t s) {
  if (s == ZS_DUAL_SIM_SLOT_1 || s == ZS_DUAL_SIM_SLOT_2) o->bringup_failures[idx(s)]++;
  zs_dual_sim_report_brownout(o->controller);
  o->recoveries++;
  o->want_start = true;
}

void evt_pre_20_sim_orchestrator_fail(evt_pre_20_sim_orchestrator_t *o, zs_dual_sim_failure_t failure, uint32_t now_ms) {
  if (!o || !o->controller) return;
  if (zs_dual_sim_state(o->controller) == ZS_DUAL_SIM_STATE_ACTIVE) {
    const zs_dual_sim_slot_t active = zs_dual_sim_active_slot(o->controller);
    zs_dual_sim_request_result_t r = ZS_DUAL_SIM_REQUEST_RETRY_CURRENT;
    if (o->link_failures[idx(active)] < 255u) o->link_failures[idx(active)]++;
    if (o->link_failures[idx(active)] >= EVT_PRE_20_SIM_MAX_LINK_FAILURES) {
      /* spend the controller's per-activation attempt budget so it evaluates the switch (presence, hold) */
      for (unsigned i = 0u; i < ZS_DUAL_SIM_MAX_ATTEMPTS_PER_PROFILE && r == ZS_DUAL_SIM_REQUEST_RETRY_CURRENT; i++)
        r = zs_dual_sim_report_failure(o->controller, failure, other(active), o->profile, now_ms);
    }
    if (r == ZS_DUAL_SIM_REQUEST_ACCEPTED) {      /* graceful switch: the action loop takes it from here */
      o->switches++;
      o->link_failures[idx(active)] = 0u;
      o->transport_closed = false;
      return;
    }
    o->retries++;                                 /* same slot again: budget not spent / 15 min hold / no other SIM */
    zs_dual_sim_report_brownout(o->controller);
    o->recoveries++;
    o->want_start = true;
    return;
  }
  bringup_failed(o, o->controller->pending_slot); /* failure before ACTIVE (bring-up, link validation) */
}

evt_pre_20_sim_phase_t evt_pre_20_sim_orchestrator_step(evt_pre_20_sim_orchestrator_t *o, uint32_t now_ms) {
  bool status_high = false;
  if (!o || !o->controller) return EVT_PRE_20_SIM_PHASE_SAFE_OFF;
  (void)evt_pre_20_dual_sim_gpio_sample_presence(o->gpio, o->controller, now_ms);
  for (unsigned guard = 0u; guard < 16u; guard++) {
    const zs_dual_sim_action_t a = zs_dual_sim_next_action(o->controller);
    const zs_dual_sim_slot_t pend = o->controller->pending_slot;
    evt_pre_20_dual_sim_io_result_t r;
    switch (a) {
      case ZS_DUAL_SIM_ACTION_NONE:
        if (zs_dual_sim_state(o->controller) == ZS_DUAL_SIM_STATE_ACTIVE) return (o->phase = EVT_PRE_20_SIM_PHASE_ACTIVE);
        /* SAFE_OFF */
        if (!o->want_start) return (o->phase = EVT_PRE_20_SIM_PHASE_SAFE_OFF);
        {
          const zs_dual_sim_slot_t s = pick_slot(o);
          if (s == ZS_DUAL_SIM_SLOT_NONE) return (o->phase = EVT_PRE_20_SIM_PHASE_SAFE_OFF);
          if (zs_dual_sim_request_start(o->controller, s, o->profile) != ZS_DUAL_SIM_REQUEST_ACCEPTED)
            return (o->phase = EVT_PRE_20_SIM_PHASE_SAFE_OFF);
          o->want_start = false;
          o->starts++;
          o->transport_closed = false;
        }
        break;
      case ZS_DUAL_SIM_ACTION_REQUEST_MODEM_OFF_GRACEFUL_OR_FALLBACK_1000_MS:
        r = evt_pre_20_dual_sim_gpio_drive_recovery_fallback(o->gpio, true, now_ms);
        if (r == EVT_PRE_20_DUAL_SIM_IO_WAITING) return (o->phase = EVT_PRE_20_SIM_PHASE_BUSY);
        if (r == EVT_PRE_20_DUAL_SIM_IO_FAILED) return (o->phase = EVT_PRE_20_SIM_PHASE_BUSY);   /* GPIO read failed: retry next tick */
        o->modem->state = ZS_BG95_OFF;          /* the hard pulse made the modem's own state stale */
        (void)complete(o, a, true, now_ms);
        break;
      case ZS_DUAL_SIM_ACTION_VERIFY_MODEM_OFF:
        if (zs_dual_sim_state(o->controller) == ZS_DUAL_SIM_STATE_RECOVERY_VERIFYING_MODEM_OFF) {
          if (!evt_pre_20_dual_sim_gpio_verify_modem_off(o->gpio)) return (o->phase = EVT_PRE_20_SIM_PHASE_BUSY);
          (void)complete(o, a, true, now_ms);
          break;
        }
        (void)evt_pre_20_dual_sim_gpio_read_cell_status(o->gpio, &status_high);
        if (zs_dual_sim_bg95_confirm_shutdown(o->controller, o->modem, !status_high, now_ms)) { o->gpio->modem_off_observed = true; break; }
        if ((uint32_t)(now_ms - o->graceful_ms) >= EVT_PRE_20_SIM_GRACEFUL_OFF_TIMEOUT_MS) { (void)complete(o, a, false, now_ms); o->recoveries++; break; }   /* -> safe-off recovery */
        return (o->phase = EVT_PRE_20_SIM_PHASE_BUSY);
      case ZS_DUAL_SIM_ACTION_DISABLE_MUX:
        if (!complete(o, a, evt_pre_20_dual_sim_gpio_disable_mux(o->gpio), now_ms)) return (o->phase = EVT_PRE_20_SIM_PHASE_BUSY);
        break;
      case ZS_DUAL_SIM_ACTION_VERIFY_MUX_HIGH_Z:
        r = evt_pre_20_dual_sim_gpio_verify_mux_disabled(o->gpio);
        if (r == EVT_PRE_20_DUAL_SIM_IO_WAITING) return (o->phase = EVT_PRE_20_SIM_PHASE_BUSY);
        if (!complete(o, a, r != EVT_PRE_20_DUAL_SIM_IO_FAILED, now_ms)) return (o->phase = EVT_PRE_20_SIM_PHASE_BUSY);
        break;
      case ZS_DUAL_SIM_ACTION_DISABLE_MODEM_RAIL:
        if (!complete(o, a, evt_pre_20_dual_sim_gpio_disable_modem_rail(o->gpio), now_ms)) return (o->phase = EVT_PRE_20_SIM_PHASE_BUSY);
        break;
      case ZS_DUAL_SIM_ACTION_RECORD_SWITCH_INTENT:
      case ZS_DUAL_SIM_ACTION_STOP_NEW_TRAFFIC:
      case ZS_DUAL_SIM_ACTION_PERSIST_QUEUE_AND_SESSION:   /* the outbox is durable NOR: nothing to flush */
      case ZS_DUAL_SIM_ACTION_RECORD_SWITCH_COMMIT:
      case ZS_DUAL_SIM_ACTION_RESUME_PRESERVED_QUEUE:
        (void)complete(o, a, true, now_ms);
        break;
      case ZS_DUAL_SIM_ACTION_CLOSE_TRANSPORT_AND_DETACH:
        if (!o->transport_closed) return (o->phase = EVT_PRE_20_SIM_PHASE_CLOSE_TRANSPORT);
        (void)complete(o, a, true, now_ms);
        break;
      case ZS_DUAL_SIM_ACTION_GRACEFUL_MODEM_OFF:
        if (zs_dual_sim_bg95_begin_graceful_shutdown(o->controller, o->modem, now_ms)) { o->graceful_ms = now_ms; break; }
        if (zs_dual_sim_next_action(o->controller) != a) { o->recoveries++; break; }   /* rejected: the controller went to recovery */
        return (o->phase = EVT_PRE_20_SIM_PHASE_BUSY);                                /* modem busy: retry next tick */
      case ZS_DUAL_SIM_ACTION_SELECT_PENDING_SLOT:
        if (!complete(o, a, evt_pre_20_dual_sim_gpio_select_slot(o->gpio, o->controller->pending_slot), now_ms)) return (o->phase = EVT_PRE_20_SIM_PHASE_BUSY);
        break;
      case ZS_DUAL_SIM_ACTION_ENABLE_MODEM_RAIL:
        if (!complete(o, a, evt_pre_20_dual_sim_gpio_enable_modem_rail(o->gpio), now_ms)) return (o->phase = EVT_PRE_20_SIM_PHASE_BUSY);
        break;
      case ZS_DUAL_SIM_ACTION_VERIFY_POWER_GOOD_30_MS:
        r = evt_pre_20_dual_sim_gpio_check_power_good(o->gpio, now_ms);
        if (r == EVT_PRE_20_DUAL_SIM_IO_WAITING) return (o->phase = EVT_PRE_20_SIM_PHASE_BUSY);
        if (r == EVT_PRE_20_DUAL_SIM_IO_FAILED) { (void)complete(o, a, false, now_ms); bringup_failed(o, pend); break; }
        if (!complete(o, a, true, now_ms)) return (o->phase = EVT_PRE_20_SIM_PHASE_BUSY);   /* < 30 ms since the rail: wait */
        break;
      case ZS_DUAL_SIM_ACTION_ENABLE_MUX:
        if (!complete(o, a, evt_pre_20_dual_sim_gpio_enable_mux(o->gpio), now_ms)) return (o->phase = EVT_PRE_20_SIM_PHASE_BUSY);
        break;
      case ZS_DUAL_SIM_ACTION_VERIFY_MUX_ENABLED:
        r = evt_pre_20_dual_sim_gpio_verify_mux_enabled(o->gpio);
        if (r == EVT_PRE_20_DUAL_SIM_IO_WAITING) return (o->phase = EVT_PRE_20_SIM_PHASE_BUSY);
        if (r == EVT_PRE_20_DUAL_SIM_IO_FAILED) { (void)complete(o, a, false, now_ms); bringup_failed(o, pend); break; }
        (void)complete(o, a, true, now_ms);
        break;
      case ZS_DUAL_SIM_ACTION_PULSE_PWRKEY_700_MS:
        if (!zs_dual_sim_bg95_begin_power_on(o->controller, o->modem, now_ms)) { bringup_failed(o, pend); break; }
        o->pwrkey_ms = now_ms;
        return (o->phase = EVT_PRE_20_SIM_PHASE_MODEM_BOOT);
      case ZS_DUAL_SIM_ACTION_VERIFY_MODEM_ON:
        (void)evt_pre_20_dual_sim_gpio_read_cell_status(o->gpio, &status_high);
        if (zs_dual_sim_bg95_confirm_modem_on(o->controller, o->modem, status_high, now_ms)) break;
        if (o->modem->state == ZS_BG95_ERROR || (uint32_t)(now_ms - o->pwrkey_ms) >= EVT_PRE_20_SIM_MODEM_ON_TIMEOUT_MS) { (void)complete(o, a, false, now_ms); bringup_failed(o, pend); break; }
        return (o->phase = EVT_PRE_20_SIM_PHASE_MODEM_BOOT);
      case ZS_DUAL_SIM_ACTION_READ_AND_VERIFY_ICCID:
        if (zs_dual_sim_bg95_verify_iccid(o->controller, o->modem)) break;
        if (zs_dual_sim_state(o->controller) != ZS_DUAL_SIM_STATE_VERIFYING_ICCID) { bringup_failed(o, pend); break; }   /* wrong card: the controller dropped to safe-off */
        if (o->modem->state == ZS_BG95_ERROR) { bringup_failed(o, pend); break; }
        return (o->phase = EVT_PRE_20_SIM_PHASE_MODEM_BOOT);                                                        /* ICCID not read yet */
      case ZS_DUAL_SIM_ACTION_ATTACH_VALIDATE_DNS_TLS:
        if (zs_dual_sim_bg95_confirm_link(o->controller, o->modem, now_ms)) break;
        if (o->modem->state == ZS_BG95_ERROR) { bringup_failed(o, pend); break; }
        return (o->phase = EVT_PRE_20_SIM_PHASE_NEED_LINK);
      default:
        return (o->phase = EVT_PRE_20_SIM_PHASE_BUSY);
    }
  }
  return (o->phase = EVT_PRE_20_SIM_PHASE_BUSY);
}
