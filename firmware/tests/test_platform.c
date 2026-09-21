#include "zs_pdm_capture.h"
#include "zs_power_modes.h"
#include "zs_pps_sync.h"
#include "zs_selftest.h"

#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

/* ------------------------------------------------------------- power modes */
static void test_power_modes(void) {
  zs_mode_scheduler_t s;
  zs_mode_policy_t pol = zs_mode_policy_default();
  zs_mode_transition_t j[ZS_MODE_JOURNAL_DEPTH];
  uint32_t t = 1000u;
  pol.listen_dwell_ms = 3000u; pol.min_sleep_ms = 2000u; pol.heartbeat_period_ms = 100000u;
  zs_mode_init(&s, &pol, t);
  assert(zs_mode_current(&s) == ZS_MODE_S0_SLEEP);
  /* boot -> listen -> nothing -> sleep */
  assert(zs_mode_on_event(&s, ZS_MODE_EV_BOOT_DONE, t) && s.mode == ZS_MODE_S1_LISTEN);
  assert(!zs_mode_tick(&s, t + 2999u));
  assert(zs_mode_tick(&s, t + 3000u) && s.mode == ZS_MODE_S0_SLEEP);
  t += 3000u;
  /* wake storm hysteresis: MIC_WAKE within min_sleep is ignored */
  assert(!zs_mode_on_event(&s, ZS_MODE_EV_MIC_WAKE, t + 500u) && s.mode == ZS_MODE_S0_SLEEP);
  assert(zs_mode_on_event(&s, ZS_MODE_EV_MIC_WAKE, t + 2000u) && s.mode == ZS_MODE_S1_LISTEN);
  t += 2000u;
  /* gate -> dsp -> event -> comms -> done -> listen */
  assert(zs_mode_on_event(&s, ZS_MODE_EV_GATE_POSITIVE, t) && s.mode == ZS_MODE_S2_DSP);
  assert(zs_mode_clock_profile(s.mode) == 2u);
  assert(zs_mode_on_event(&s, ZS_MODE_EV_DSP_DONE_EVENT, t + 100u) && s.mode == ZS_MODE_S3_COMMS && s.outbox_pending);
  assert(zs_mode_power_for(s.mode).modem && !zs_mode_power_for(s.mode).ble);
  assert(zs_mode_on_event(&s, ZS_MODE_EV_COMMS_DONE, t + 5000u) && s.mode == ZS_MODE_S1_LISTEN && !s.outbox_pending);
  t += 5000u;
  /* dsp watchdog */
  assert(zs_mode_on_event(&s, ZS_MODE_EV_GATE_POSITIVE, t) && s.mode == ZS_MODE_S2_DSP);
  assert(zs_mode_tick(&s, t + pol.dsp_max_ms) && s.mode == ZS_MODE_S1_LISTEN && s.fault_code == 2u);
  /* pending outbox from sleep triggers comms immediately */
  assert(zs_mode_tick(&s, t + pol.dsp_max_ms + pol.listen_dwell_ms) && s.mode == ZS_MODE_S0_SLEEP);
  t += pol.dsp_max_ms + pol.listen_dwell_ms;
  assert(zs_mode_on_event(&s, ZS_MODE_EV_OUTBOX_PENDING, t) && s.mode == ZS_MODE_S3_COMMS);
  /* comms watchdog keeps outbox pending */
  assert(zs_mode_tick(&s, t + pol.comms_max_ms) && s.mode == ZS_MODE_S1_LISTEN && s.outbox_pending);
  t += pol.comms_max_ms;
  /* service button wins from any mode, exit returns to comms because outbox pending */
  assert(zs_mode_on_event(&s, ZS_MODE_EV_SERVICE_BUTTON, t) && s.mode == ZS_MODE_S4_SERVICE);
  assert(zs_mode_power_for(s.mode).ble);
  assert(!zs_mode_on_event(&s, ZS_MODE_EV_MIC_WAKE, t) && s.mode == ZS_MODE_S4_SERVICE);
  assert(zs_mode_tick(&s, t + pol.service_window_ms) && s.mode == ZS_MODE_S3_COMMS);
  t += pol.service_window_ms;
  assert(zs_mode_on_event(&s, ZS_MODE_EV_COMMS_DONE, t) && s.mode == ZS_MODE_S1_LISTEN);
  /* heartbeat from sleep */
  assert(zs_mode_tick(&s, t + pol.listen_dwell_ms) && s.mode == ZS_MODE_S0_SLEEP);
  t += pol.listen_dwell_ms;
  assert(!zs_mode_tick(&s, t + 1000u));
  assert(zs_mode_tick(&s, t + pol.heartbeat_period_ms) && s.mode == ZS_MODE_S3_COMMS);
  t += pol.heartbeat_period_ms;
  /* critical battery is terminal */
  assert(zs_mode_on_event(&s, ZS_MODE_EV_BATTERY_CRITICAL, t) && s.mode == ZS_MODE_SHUTDOWN);
  assert(!zs_mode_on_event(&s, ZS_MODE_EV_BOOT_DONE, t) && !zs_mode_tick(&s, t + 1000000u));
  assert(zs_mode_power_for(s.mode).mic_1v8 == false);
  /* journal keeps the most recent transitions oldest-first */
  {
    uint8_t n = zs_mode_journal(&s, j, ZS_MODE_JOURNAL_DEPTH);
    assert(n == ZS_MODE_JOURNAL_DEPTH);
    assert(j[n - 1u].to == ZS_MODE_SHUTDOWN && j[n - 1u].event == ZS_MODE_EV_BATTERY_CRITICAL);
    for (uint8_t i = 1u; i < n; i++) assert(j[i].from == j[i - 1u].to && j[i].at_ms >= j[i - 1u].at_ms);
    assert(zs_mode_journal(&s, j, 3u) == 3u && j[2].to == ZS_MODE_SHUTDOWN);
  }
  assert(strcmp(zs_mode_name(ZS_MODE_S2_DSP), "S2_DSP") == 0);
}

/* ------------------------------------------------------------- pdm capture */
#define BLK 64u
static int32_t dma_buf[ZS_PDM_CHANNELS][2u * BLK];
static int16_t ring_storage[ZS_AUDIO_CHANNELS * 4096u];

static void fill_block(unsigned block, uint32_t start_sample, int lag_ch3) {
  for (uint32_t k = 0u; k < BLK; k++) {
    uint32_t n = start_sample + k;
    for (unsigned ch = 0u; ch < ZS_PDM_CHANNELS; ch++) {
      int shift = ch == 3u ? lag_ch3 : 0;
      double v = 8000.0 * sin(2.0 * 3.14159265 * 1000.0 * ((double)n - shift) / 32000.0) +
                 3000.0 * sin(2.0 * 3.14159265 * 3700.0 * ((double)n - shift) / 32000.0);
      dma_buf[ch][block * BLK + k] = ((int32_t)v) << 16; /* 24-bit left aligned in 32 */
    }
  }
}

static void test_pdm_capture(void) {
  zs_audio_ring_t ring;
  zs_pdm_capture_t cap;
  zs_pdm_config_t cfg = zs_pdm_config_default();
  const int32_t *const dma[ZS_PDM_CHANNELS] = {dma_buf[0], dma_buf[1], dma_buf[2], dma_buf[3]};
  int lag = 99;
  cfg.block_samples = BLK;
  cfg.dc_alpha_q15 = 0;
  zs_audio_ring_init(&ring, ring_storage, 4096u, 32000u);
  assert(zs_pdm_capture_init(&cap, &cfg, dma, &ring));
  {
    zs_pdm_config_t bad = cfg; bad.block_samples = 0u;
    zs_pdm_capture_t tmp;
    assert(!zs_pdm_capture_init(&tmp, &bad, dma, &ring));
    bad = cfg; bad.sample_rate = 48000u;
    assert(!zs_pdm_capture_init(&tmp, &bad, dma, &ring)); /* ring rate mismatch */
  }
  assert(!zs_pdm_capture_process(&cap) && !zs_pdm_capture_pending(&cap));
  /* 40 blocks, channel 3 lagging by 3 samples */
  for (uint32_t b = 0u; b < 40u; b++) {
    unsigned block = b & 1u;
    fill_block(block, b * BLK, 3);
    if (block == 0u) zs_pdm_capture_on_dma_half(&cap); else zs_pdm_capture_on_dma_full(&cap);
    assert(zs_pdm_capture_pending(&cap));
    assert(zs_pdm_capture_process(&cap));
  }
  assert(cap.blocks_processed == 40u && zs_pdm_capture_sample_counter(&cap) == 40u * BLK);
  assert(cap.overruns == 0u && cap.sequence_errors == 0u);
  assert(cap.peak[0] > 9000 && cap.peak[0] < 11500);
  /* aligned channels report lag 0, the delayed channel reports its delay */
  assert(zs_pdm_capture_channel_lag(&cap, 1u, 1024u, 8, &lag) && lag == 0);
  assert(zs_pdm_capture_channel_lag(&cap, 3u, 1024u, 8, &lag) && lag == 3);
  assert(!zs_pdm_capture_channel_lag(&cap, 0u, 1024u, 8, &lag)); /* channel 0 is the reference */
  /* the ring got the int16 samples (top 16 bits) */
  {
    int16_t out[8];
    assert(zs_audio_ring_copy_mono(&ring, 40u * BLK, 8u, out, 0u));
    assert(out[7] == (int16_t)(dma_buf[1][2u * BLK - 1u] >> 16));
  }
  /* overrun: same block twice without processing */
  zs_pdm_capture_on_dma_half(&cap);
  zs_pdm_capture_on_dma_half(&cap);
  assert(cap.overruns == 1u && cap.sequence_errors == 1u);
  assert(zs_pdm_capture_process(&cap));
  /* order violation: the same half arrives again where the other one was expected */
  {
    uint32_t seq;
    zs_pdm_capture_on_dma_full(&cap);          /* block 1 as expected after the overrun block 0 */
    assert(zs_pdm_capture_process(&cap));
    seq = cap.sequence_errors;
    zs_pdm_capture_on_dma_full(&cap);          /* block 1 again where block 0 was expected */
    assert(zs_pdm_capture_process(&cap));
    assert(cap.sequence_errors == seq + 2u);   /* ISR-side repeat + task-side resync */
  }
  /* DC blocker removes an offset */
  {
    zs_pdm_capture_t cap2;
    zs_audio_ring_t ring2;
    zs_pdm_config_t cfg2 = cfg;
    int16_t out[16];
    cfg2.dc_alpha_q15 = 32440;
    zs_audio_ring_init(&ring2, ring_storage, 4096u, 32000u);
    assert(zs_pdm_capture_init(&cap2, &cfg2, dma, &ring2));
    for (unsigned ch = 0u; ch < ZS_PDM_CHANNELS; ch++) for (uint32_t k = 0u; k < 2u * BLK; k++) dma_buf[ch][k] = 5000 << 16;
    for (uint32_t b = 0u; b < 200u; b++) {
      if ((b & 1u) == 0u) zs_pdm_capture_on_dma_half(&cap2); else zs_pdm_capture_on_dma_full(&cap2);
      assert(zs_pdm_capture_process(&cap2));
    }
    assert(zs_audio_ring_copy_mono(&ring2, 200u * BLK, 16u, out, 2u));
    for (unsigned i = 0u; i < 16u; i++) assert(out[i] > -40 && out[i] < 40);
  }
}

/* ------------------------------------------------------------- pps sync */
typedef struct { uint32_t ticks; uint64_t samples; } sim_t;
#define SIM_HZ 16000000u
#define SIM_BLOCK_TICKS 5000u      /* 10 ms blocks */
#define SIM_BLOCK_SAMPLES 320u

static void sim_block(zs_pps_sync_t *p, sim_t *s) {
  zs_pps_sync_on_block(p, s->ticks, s->samples);
  s->ticks += SIM_BLOCK_TICKS;
  s->samples += SIM_BLOCK_SAMPLES;
}

/* Pushes blocks until `target` is covered and one block beyond; returns the tick of the PPS edge at `target`. */
static uint32_t sim_pps_at(zs_pps_sync_t *p, sim_t *s, uint64_t target) {
  uint32_t pps_ticks = 0u;
  while (s->samples < target + SIM_BLOCK_SAMPLES) {
    if (s->samples <= target && target < s->samples + SIM_BLOCK_SAMPLES)
      pps_ticks = s->ticks + (uint32_t)(((target - s->samples) * SIM_BLOCK_TICKS) / SIM_BLOCK_SAMPLES);
    sim_block(p, s);
  }
  return pps_ticks;
}

static void test_pps_sync(void) {
  zs_time_sync_t time;
  zs_pps_sync_t p;
  sim_t s = {0xFFFFA000u, 0u}; /* 24576 ticks before the 32-bit wrap */
  uint64_t target;
  zs_time_init(&time, 32000.0);
  zs_pps_sync_init(&p, &time, SIM_HZ, 900u);
  for (int b = 0; b < 5; b++) sim_block(&p, &s);
  assert(!zs_pps_sync_poll(&p, s.ticks));
  /* PPS 1500 ticks into the last block (across the timer wrap): interpolated to 96 samples */
  zs_pps_sync_on_pps(&p, s.ticks - SIM_BLOCK_TICKS + 1500u);
  assert(!zs_pps_sync_poll(&p, s.ticks));           /* bracketed, no label yet */
  assert(p.pps_sample_valid && p.pps_sample == s.samples - SIM_BLOCK_SAMPLES + 96u);
  assert(s.ticks < 0x00010000u);                    /* the wrap happened inside the marks */
  zs_pps_sync_on_utc(&p, 1800000000000000LL);
  assert(zs_pps_sync_poll(&p, s.ticks + 100u) && p.bound_count == 1u);
  assert(time.trust == ZS_TIME_TRUST_GNSS_TRUSTED && time.pps_sample_counter == p.pps_sample);
  /* PPS inside the newest block, whose end mark is not reported yet: extrapolated from the last span */
  target = s.samples - 64u;                         /* 4000 ticks past the newest mark = 256 samples */
  zs_pps_sync_on_pps(&p, s.ticks - 1000u);
  zs_pps_sync_on_utc(&p, 1800000001000000LL);
  assert(zs_pps_sync_poll(&p, s.ticks - 900u) && p.bound_count == 2u && p.pps_sample == target);
  /* next second has 32032 samples: +1000 ppm against the nominal rate */
  target += 32032u;
  {
    uint32_t pps_ticks = sim_pps_at(&p, &s, target);
    zs_pps_sync_on_pps(&p, pps_ticks);
    zs_pps_sync_on_utc(&p, 1800000002000000LL);
    assert(zs_pps_sync_poll(&p, s.ticks) && p.bound_count == 3u && p.pps_sample == target);
    assert(zs_pps_sync_rate_error_ppm(&p) == 1000);
  }
  /* label without PPS times out; PPS without label times out */
  zs_pps_sync_on_utc(&p, 1800000003000000LL);
  assert(!zs_pps_sync_poll(&p, s.ticks));
  sim_block(&p, &s);
  assert(!zs_pps_sync_poll(&p, s.ticks + 20000000u) && p.dropped_no_pps == 1u && !p.label_pending);
  zs_pps_sync_on_pps(&p, s.ticks);
  sim_block(&p, &s);
  sim_block(&p, &s);
  assert(!zs_pps_sync_poll(&p, s.ticks + 20000000u) && p.dropped_no_label == 1u && !p.pps_armed);
  assert(p.bound_count == 3u);
  /* a second PPS before the first got its label drops the first */
  zs_pps_sync_on_pps(&p, s.ticks);
  zs_pps_sync_on_pps(&p, s.ticks + 100u);
  assert(p.dropped_no_label == 2u && p.pps_count == 6u);
}

/* ------------------------------------------------------------- selftest */
static zs_selftest_code_t st_pass(void *ctx, uint32_t *d) { *d = *(uint32_t *)ctx; return ZS_ST_PASS; }
static zs_selftest_code_t st_fail(void *ctx, uint32_t *d) { (void)ctx; *d = 7u; return ZS_ST_FAIL; }
static zs_selftest_code_t st_skip(void *ctx, uint32_t *d) { (void)ctx; *d = 0u; return ZS_ST_SKIPPED; }
static zs_selftest_code_t st_broken(void *ctx, uint32_t *d) { (void)ctx; (void)d; return ZS_ST_NOT_RUN; }

static void test_selftest(void) {
  zs_selftest_registry_t r;
  uint32_t vbat = 3900u;
  uint8_t buf[64];
  size_t n;
  zs_selftest_init(&r);
  assert(zs_selftest_register(&r, ZS_ST_ID_POWER_INA226, "power", st_pass, &vbat, true));
  assert(zs_selftest_register(&r, ZS_ST_ID_MODEM_AT, "modem", st_skip, NULL, false));
  assert(zs_selftest_register(&r, ZS_ST_ID_LORA_SPI, "lora", st_fail, NULL, false));
  assert(!zs_selftest_register(&r, ZS_ST_ID_POWER_INA226, "dup", st_pass, &vbat, true));
  assert(!zs_selftest_register(&r, 0u, "zero", st_pass, &vbat, true));
  assert(!zs_selftest_required_ok(&r)); /* not run yet */
  assert(zs_selftest_run_all(&r, 10u));  /* required test passes, optional failure tolerated */
  assert(r.result[ZS_ST_ID_POWER_INA226] == ZS_ST_PASS && r.detail[ZS_ST_ID_POWER_INA226] == 3900u);
  assert(r.result[ZS_ST_ID_LORA_SPI] == ZS_ST_FAIL && r.detail[ZS_ST_ID_LORA_SPI] == 7u);
  n = zs_selftest_encode(&r, buf, sizeof(buf));
  /* map(3){1:[1,3900], 8:[2,7], 9:[3,0]} */
  {
    const uint8_t expect[] = {0xa3, 0x01, 0x82, 0x01, 0x19, 0x0f, 0x3c, 0x08, 0x82, 0x02, 0x07, 0x09, 0x82, 0x03, 0x00};
    assert(n == sizeof(expect) && memcmp(buf, expect, n) == 0);
  }
  assert(zs_selftest_encode(&r, buf, 4u) == 0u);
  /* a required test that fails blocks boot */
  assert(zs_selftest_register(&r, ZS_ST_ID_NOR_SFDP, "nor", st_broken, NULL, true));
  assert(!zs_selftest_run_all(&r, 20u));
  assert(r.result[ZS_ST_ID_NOR_SFDP] == ZS_ST_FAIL); /* NOT_RUN from a test is reported as FAIL */
  assert(zs_selftest_run_one(&r, ZS_ST_ID_POWER_INA226, 30u) == ZS_ST_PASS && r.last_run_ms == 30u);
  assert(zs_selftest_run_one(&r, ZS_ST_ID_SD_CARD, 30u) == ZS_ST_NOT_RUN);
  assert(strcmp(zs_selftest_code_name(ZS_ST_SKIPPED), "SKIPPED") == 0);
}

int main(void) {
  test_power_modes();
  test_pdm_capture();
  test_pps_sync();
  test_selftest();
  printf("platform tests passed\n");
  return 0;
}
