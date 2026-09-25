#ifndef ZS_POWER_MODES_H
#define ZS_POWER_MODES_H

/*
 * Station operating-mode scheduler (EVT-PRE-20 power architecture).
 *
 *   S0 SLEEP    STOP2, microphones in AAD stand-by, wake on MIC_WAKE / RTC / service button
 *   S1 LISTEN   MDF capture + gate detector on short windows
 *   S2 DSP      full feature extraction + classification of a window series
 *   S3 COMMS    modem session: outbox flush, heartbeat, command poll
 *   S4 SERVICE  BLE service window (button held 5 s), everything else paused
 *   SHUTDOWN    safe power-down (critical battery or fault): terminal state
 *
 * Pure state machine, no HAL: the supervisor task feeds events and the
 * millisecond clock, reads the requested mode, clock profile and peripheral
 * power flags, and applies them.  Every transition is journaled in a small
 * ring for diagnostics.
 */

#include <stdbool.h>
#include <stdint.h>

typedef enum {
  ZS_MODE_S0_SLEEP = 0,
  ZS_MODE_S1_LISTEN,
  ZS_MODE_S2_DSP,
  ZS_MODE_S3_COMMS,
  ZS_MODE_S4_SERVICE,
  ZS_MODE_SHUTDOWN
} zs_mode_t;

typedef enum {
  ZS_MODE_EV_NONE = 0,
  ZS_MODE_EV_BOOT_DONE,        /* self-tests passed, enter normal operation */
  ZS_MODE_EV_MIC_WAKE,         /* AAD wake (PA8) */
  ZS_MODE_EV_GATE_POSITIVE,    /* gate detector found candidate activity */
  ZS_MODE_EV_GATE_NEGATIVE,    /* listen window ended without activity */
  ZS_MODE_EV_DSP_DONE_EVENT,   /* classifier produced an event (outbox has data) */
  ZS_MODE_EV_DSP_DONE_NOTHING, /* classifier: nothing to report */
  ZS_MODE_EV_OUTBOX_PENDING,   /* queued events waiting (e.g. after power loss) */
  ZS_MODE_EV_COMMS_DONE,       /* session finished (success or gave up) */
  ZS_MODE_EV_SERVICE_BUTTON,   /* button held for the service hold time */
  ZS_MODE_EV_SERVICE_EXIT,     /* service session closed by the phone or engineer */
  ZS_MODE_EV_BATTERY_CRITICAL, /* below shutdown threshold */
  ZS_MODE_EV_FAULT             /* unrecoverable fault reported by a task */
} zs_mode_event_t;

typedef struct {
  uint32_t listen_dwell_ms;      /* max time in S1 without a gate decision */
  uint32_t dsp_max_ms;           /* watchdog for S2 */
  uint32_t comms_max_ms;         /* watchdog for S3 */
  uint32_t heartbeat_period_ms;  /* S0 -> S3 for heartbeat when nothing else happens */
  uint32_t service_window_ms;    /* S4 auto-exit */
  uint32_t min_sleep_ms;         /* hysteresis: stay in S0 at least this long before MIC_WAKE is honoured */
  bool boot_session;             /* BOOT_DONE requests a comms session after the self-check listen window: the reset
                                    cause reaches the server and queued commands are delivered without waiting a
                                    heartbeat period (default on) */
} zs_mode_policy_t;

typedef struct {
  bool mic_1v8;     /* microphone rail */
  bool mdf_clock;   /* PDM clock running */
  bool modem;       /* BG95 powered */
  bool ble;         /* nRF52840 enabled */
  bool gnss;        /* GNSS receiver powered */
  bool stop2_allowed;
} zs_mode_power_t;

#define ZS_MODE_JOURNAL_DEPTH 16u

typedef struct {
  uint32_t at_ms;
  uint8_t from;
  uint8_t to;
  uint8_t event;
} zs_mode_transition_t;

typedef struct {
  zs_mode_policy_t policy;
  zs_mode_t mode;
  uint32_t entered_at_ms;
  uint32_t last_comms_at_ms;
  bool outbox_pending;
  bool comms_requested;
  uint32_t fault_code;
  zs_mode_transition_t journal[ZS_MODE_JOURNAL_DEPTH];
  uint8_t journal_head;
  uint8_t journal_count;
} zs_mode_scheduler_t;

/* Default policy for the pilot: listen 3 s, DSP 20 s, comms 180 s, heartbeat 6 h, service 10 min, min sleep 2 s. */
zs_mode_policy_t zs_mode_policy_default(void);

void zs_mode_init(zs_mode_scheduler_t *s, const zs_mode_policy_t *policy, uint32_t now_ms);

/* Feeds an event; returns true when the mode changed. */
bool zs_mode_on_event(zs_mode_scheduler_t *s, zs_mode_event_t ev, uint32_t now_ms);

/* Advances timers; returns true when a timer-driven transition happened. */
bool zs_mode_tick(zs_mode_scheduler_t *s, uint32_t now_ms);

zs_mode_t zs_mode_current(const zs_mode_scheduler_t *s);
zs_mode_power_t zs_mode_power_for(zs_mode_t mode);
uint8_t zs_mode_clock_profile(zs_mode_t mode); /* maps to evt_pre_20_clock_profile_t */
const char *zs_mode_name(zs_mode_t mode);

/* Oldest-first copy of the transition journal; returns count copied. */
uint8_t zs_mode_journal(const zs_mode_scheduler_t *s, zs_mode_transition_t *out, uint8_t cap);

#endif
