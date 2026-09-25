#include "zs_power_modes.h"

#include <string.h>

zs_mode_policy_t zs_mode_policy_default(void) {
  zs_mode_policy_t p;
  p.listen_dwell_ms = 3000u;
  p.dsp_max_ms = 20000u;
  p.comms_max_ms = 180000u;
  p.heartbeat_period_ms = 6u * 3600u * 1000u;
  p.service_window_ms = 10u * 60u * 1000u;
  p.min_sleep_ms = 2000u;
  p.boot_session = true;
  return p;
}

static void journal(zs_mode_scheduler_t *s, zs_mode_t to, zs_mode_event_t ev, uint32_t now_ms) {
  zs_mode_transition_t *t = &s->journal[s->journal_head];
  t->at_ms = now_ms;
  t->from = (uint8_t)s->mode;
  t->to = (uint8_t)to;
  t->event = (uint8_t)ev;
  s->journal_head = (uint8_t)((s->journal_head + 1u) % ZS_MODE_JOURNAL_DEPTH);
  if (s->journal_count < ZS_MODE_JOURNAL_DEPTH) s->journal_count++;
}

static void enter(zs_mode_scheduler_t *s, zs_mode_t to, zs_mode_event_t ev, uint32_t now_ms) {
  journal(s, to, ev, now_ms);
  s->mode = to;
  s->entered_at_ms = now_ms;
  if (to == ZS_MODE_S3_COMMS) s->comms_requested = false;
}

void zs_mode_init(zs_mode_scheduler_t *s, const zs_mode_policy_t *policy, uint32_t now_ms) {
  if (!s) return;
  memset(s, 0, sizeof(*s));
  s->policy = policy ? *policy : zs_mode_policy_default();
  s->mode = ZS_MODE_S0_SLEEP; /* boot: stays in S0 until BOOT_DONE, then S1 self-check */
  s->entered_at_ms = now_ms;
  s->last_comms_at_ms = now_ms;
}

static uint32_t elapsed(const zs_mode_scheduler_t *s, uint32_t now_ms) { return now_ms - s->entered_at_ms; }

bool zs_mode_on_event(zs_mode_scheduler_t *s, zs_mode_event_t ev, uint32_t now_ms) {
  if (!s || s->mode == ZS_MODE_SHUTDOWN) return false;

  /* Global, highest priority. */
  if (ev == ZS_MODE_EV_BATTERY_CRITICAL || ev == ZS_MODE_EV_FAULT) {
    if (ev == ZS_MODE_EV_FAULT && s->fault_code == 0u) s->fault_code = 1u;
    enter(s, ZS_MODE_SHUTDOWN, ev, now_ms);
    return true;
  }
  if (ev == ZS_MODE_EV_SERVICE_BUTTON) {
    if (s->mode == ZS_MODE_S4_SERVICE) return false;
    enter(s, ZS_MODE_S4_SERVICE, ev, now_ms);
    return true;
  }
  if (ev == ZS_MODE_EV_OUTBOX_PENDING) {
    s->outbox_pending = true;
    s->comms_requested = true;
    /* S0 and S1 go to the session at once (boot-time flush, outbox retries); S2 finishes the detection first
       (DSP_DONE_* honour comms_requested), S3/S4 are already busy */
    if (s->mode == ZS_MODE_S0_SLEEP || s->mode == ZS_MODE_S1_LISTEN) { enter(s, ZS_MODE_S3_COMMS, ev, now_ms); return true; }
    return false;
  }

  switch (s->mode) {
    case ZS_MODE_S0_SLEEP:
      if (ev == ZS_MODE_EV_BOOT_DONE) {
        enter(s, ZS_MODE_S1_LISTEN, ev, now_ms);
        s->comms_requested = s->policy.boot_session;   /* S1 ends in S3 instead of S0 (GATE_NEGATIVE path) */
        return true;
      }
      if (ev == ZS_MODE_EV_MIC_WAKE) {
        if (elapsed(s, now_ms) < s->policy.min_sleep_ms) return false; /* hysteresis against wake storms */
        enter(s, ZS_MODE_S1_LISTEN, ev, now_ms);
        return true;
      }
      return false;
    case ZS_MODE_S1_LISTEN:
      if (ev == ZS_MODE_EV_GATE_POSITIVE) { enter(s, ZS_MODE_S2_DSP, ev, now_ms); return true; }
      if (ev == ZS_MODE_EV_GATE_NEGATIVE) {
        if (s->comms_requested) { enter(s, ZS_MODE_S3_COMMS, ev, now_ms); return true; }
        enter(s, ZS_MODE_S0_SLEEP, ev, now_ms);
        return true;
      }
      return false;
    case ZS_MODE_S2_DSP:
      if (ev == ZS_MODE_EV_DSP_DONE_EVENT) {
        s->outbox_pending = true;
        enter(s, ZS_MODE_S3_COMMS, ev, now_ms);
        return true;
      }
      if (ev == ZS_MODE_EV_DSP_DONE_NOTHING) {
        enter(s, s->comms_requested ? ZS_MODE_S3_COMMS : ZS_MODE_S1_LISTEN, ev, now_ms);
        return true;
      }
      return false;
    case ZS_MODE_S3_COMMS:
      if (ev == ZS_MODE_EV_COMMS_DONE) {
        s->outbox_pending = false;
        s->last_comms_at_ms = now_ms;
        enter(s, ZS_MODE_S1_LISTEN, ev, now_ms); /* one listen window before sleeping again */
        return true;
      }
      return false;
    case ZS_MODE_S4_SERVICE:
      if (ev == ZS_MODE_EV_SERVICE_EXIT) {
        enter(s, s->outbox_pending ? ZS_MODE_S3_COMMS : ZS_MODE_S1_LISTEN, ev, now_ms);
        return true;
      }
      return false;
    default:
      return false;
  }
}

bool zs_mode_tick(zs_mode_scheduler_t *s, uint32_t now_ms) {
  uint32_t dt;
  if (!s || s->mode == ZS_MODE_SHUTDOWN) return false;
  dt = elapsed(s, now_ms);
  switch (s->mode) {
    case ZS_MODE_S0_SLEEP:
      if ((uint32_t)(now_ms - s->last_comms_at_ms) >= s->policy.heartbeat_period_ms) {
        s->comms_requested = true;
        enter(s, ZS_MODE_S3_COMMS, ZS_MODE_EV_NONE, now_ms);
        return true;
      }
      return false;
    case ZS_MODE_S1_LISTEN:
      if (dt >= s->policy.listen_dwell_ms) return zs_mode_on_event(s, ZS_MODE_EV_GATE_NEGATIVE, now_ms);
      return false;
    case ZS_MODE_S2_DSP:
      if (dt >= s->policy.dsp_max_ms) {
        s->fault_code = 2u; /* DSP overrun */
        enter(s, ZS_MODE_S1_LISTEN, ZS_MODE_EV_NONE, now_ms);
        return true;
      }
      return false;
    case ZS_MODE_S3_COMMS:
      if (dt >= s->policy.comms_max_ms) {
        /* give up this session, keep outbox_pending so the next wake retries */
        s->last_comms_at_ms = now_ms;
        enter(s, ZS_MODE_S1_LISTEN, ZS_MODE_EV_NONE, now_ms);
        return true;
      }
      return false;
    case ZS_MODE_S4_SERVICE:
      if (dt >= s->policy.service_window_ms) return zs_mode_on_event(s, ZS_MODE_EV_SERVICE_EXIT, now_ms);
      return false;
    default:
      return false;
  }
}

zs_mode_t zs_mode_current(const zs_mode_scheduler_t *s) { return s ? s->mode : ZS_MODE_SHUTDOWN; }

zs_mode_power_t zs_mode_power_for(zs_mode_t mode) {
  zs_mode_power_t p = {false, false, false, false, false, false};
  switch (mode) {
    case ZS_MODE_S0_SLEEP:   p.mic_1v8 = true; p.stop2_allowed = true; break; /* AAD stand-by needs the rail */
    case ZS_MODE_S1_LISTEN:  p.mic_1v8 = true; p.mdf_clock = true; p.gnss = true; break;
    case ZS_MODE_S2_DSP:     p.mic_1v8 = true; p.mdf_clock = true; p.gnss = true; break;
    case ZS_MODE_S3_COMMS:   p.mic_1v8 = true; p.modem = true; p.gnss = true; break;
    case ZS_MODE_S4_SERVICE: p.mic_1v8 = true; p.modem = true; p.ble = true; p.gnss = true; break;
    default: break;
  }
  return p;
}

uint8_t zs_mode_clock_profile(zs_mode_t mode) {
  switch (mode) {
    case ZS_MODE_S1_LISTEN: return 1u;
    case ZS_MODE_S2_DSP: return 2u;
    case ZS_MODE_S3_COMMS: return 3u;
    case ZS_MODE_S4_SERVICE: return 4u;
    default: return 0u;
  }
}

const char *zs_mode_name(zs_mode_t mode) {
  static const char *const names[] = {"S0_SLEEP", "S1_LISTEN", "S2_DSP", "S3_COMMS", "S4_SERVICE", "SHUTDOWN"};
  return (unsigned)mode < 6u ? names[mode] : "?";
}

uint8_t zs_mode_journal(const zs_mode_scheduler_t *s, zs_mode_transition_t *out, uint8_t cap) {
  uint8_t n, i, start;
  if (!s || !out) return 0u;
  n = s->journal_count < cap ? s->journal_count : cap;
  start = (uint8_t)((s->journal_head + ZS_MODE_JOURNAL_DEPTH - s->journal_count) % ZS_MODE_JOURNAL_DEPTH);
  /* when truncating keep the most recent `cap` entries */
  if (s->journal_count > cap) start = (uint8_t)((start + (s->journal_count - cap)) % ZS_MODE_JOURNAL_DEPTH);
  for (i = 0u; i < n; i++) out[i] = s->journal[(start + i) % ZS_MODE_JOURNAL_DEPTH];
  return n;
}
