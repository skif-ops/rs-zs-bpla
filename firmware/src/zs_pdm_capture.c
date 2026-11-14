#include "zs_pdm_capture.h"

#include <stdlib.h>
#include <string.h>

zs_pdm_config_t zs_pdm_config_default(void) {
  zs_pdm_config_t c;
  c.sample_rate = 32000u;
  c.block_samples = 320u; /* 10 ms */
  c.shift_bits = 16u;
  c.dc_alpha_q15 = 32440;
  return c;
}

bool zs_pdm_capture_init(zs_pdm_capture_t *c, const zs_pdm_config_t *cfg,
                         const int32_t *const dma[ZS_PDM_CHANNELS], zs_audio_ring_t *ring) {
  if (!c || !cfg || !dma || !ring) return false;
  if (cfg->block_samples == 0u || cfg->block_samples > ZS_PDM_MAX_BLOCK_SAMPLES || cfg->shift_bits > 24u) return false;
  if (cfg->sample_rate == 0u || ring->sample_rate != cfg->sample_rate) return false;
  if (cfg->dc_alpha_q15 < 0 || cfg->dc_alpha_q15 >= 32768) return false;
  memset(c, 0, sizeof(*c));
  c->cfg = *cfg;
  for (unsigned i = 0u; i < ZS_PDM_CHANNELS; i++) {
    if (!dma[i]) return false;
    c->dma[i] = dma[i];
  }
  c->ring = ring;
  return true;
}

static void mark_ready(zs_pdm_capture_t *c, uint8_t block) {
  uint8_t bit = (uint8_t)(1u << block);
  if (c->pending_mask & bit) c->overruns++;                 /* previous instance never processed */
  if (c->ready_seen && c->last_ready == block) c->sequence_errors++; /* same half twice in a row */
  c->ready_seen = 1u;
  c->pending_mask |= bit;
  c->last_ready = block;
}

void zs_pdm_capture_on_dma_half(zs_pdm_capture_t *c) { if (c) mark_ready(c, 0u); }
void zs_pdm_capture_on_dma_full(zs_pdm_capture_t *c) { if (c) mark_ready(c, 1u); }

bool zs_pdm_capture_pending(const zs_pdm_capture_t *c) { return c && c->pending_mask != 0u; }

static int16_t sat16(int32_t v) {
  if (v > 32767) return 32767;
  if (v < -32768) return -32768;
  return (int16_t)v;
}

bool zs_pdm_capture_process(zs_pdm_capture_t *c) {
  uint8_t block, bit;
  uint32_t n, base;
  int16_t frame[ZS_PDM_CHANNELS];
  if (!c || c->pending_mask == 0u) return false;
  /* Consume in order; if only the other block is ready we lost one: resynchronize. */
  block = c->next_block;
  bit = (uint8_t)(1u << block);
  if ((c->pending_mask & bit) == 0u) {
    c->sequence_errors++;
    block = (uint8_t)(block ^ 1u);
    bit = (uint8_t)(1u << block);
  }
  n = c->cfg.block_samples;
  base = block == 0u ? 0u : n;
  for (unsigned i = 0u; i < ZS_PDM_CHANNELS; i++) c->peak[i] = 0;
  for (uint32_t k = 0u; k < n; k++) {
    for (unsigned ch = 0u; ch < ZS_PDM_CHANNELS; ch++) {
      int32_t x = c->dma[ch][base + k] >> c->cfg.shift_bits;
      int32_t y = x;
      if (c->cfg.dc_alpha_q15 != 0) {
        /* y[n] = x[n] - x[n-1] + a*y[n-1] */
        int64_t acc = (int64_t)x - c->dc_x1[ch] + (((int64_t)c->cfg.dc_alpha_q15 * c->dc_state[ch]) >> 15);
        c->dc_x1[ch] = x;
        if (acc > INT32_MAX) acc = INT32_MAX;
        if (acc < INT32_MIN) acc = INT32_MIN;
        c->dc_state[ch] = (int32_t)acc;
        y = (int32_t)acc;
      }
      frame[ch] = sat16(y);
      {
        int16_t a = frame[ch] < 0 ? (int16_t)-frame[ch] : frame[ch];
        if (frame[ch] == -32768) a = 32767;
        if (a > c->peak[ch]) c->peak[ch] = a;
      }
    }
    zs_audio_ring_push(c->ring, frame);
  }
  c->samples_total += n;
  c->blocks_processed++;
  c->next_block = (uint8_t)(block ^ 1u);
  c->pending_mask = (uint8_t)(c->pending_mask & (uint8_t)~bit);
  return true;
}

uint64_t zs_pdm_capture_sample_counter(const zs_pdm_capture_t *c) { return c ? c->samples_total : 0u; }

bool zs_pdm_capture_channel_lag(const zs_pdm_capture_t *c, unsigned ch, uint32_t count, int max_lag, int *lag_out) {
  /* cross-correlation straight out of the ring (no window copies: the bench self-test runs beside the DSP scratch) */
  int64_t best = INT64_MIN, energy_ref = 0, energy_other = 0;
  int best_lag = 0;
  uint64_t end;
  if (!c || ch == 0u || ch >= ZS_PDM_CHANNELS || !lag_out || count < 64u || count > 4096u || max_lag < 1) return false;
  if (c->samples_total < count + (uint64_t)max_lag) return false;
  end = c->samples_total;
  if (!zs_audio_ring_range_ok(c->ring, end, count)) return false;
  for (uint32_t i = 0u; i < count; i++) {
    const int32_t a = zs_audio_ring_at(c->ring, end, count, i, 0u), b = zs_audio_ring_at(c->ring, end, count, i, ch);
    energy_ref += (int64_t)a * a;
    energy_other += (int64_t)b * b;
  }
  if (energy_ref < (int64_t)count * 16 || energy_other < (int64_t)count * 16) return false; /* effectively silence */
  for (int lag = -max_lag; lag <= max_lag; lag++) {
    int64_t acc = 0;
    for (uint32_t i = (uint32_t)max_lag; i + (uint32_t)max_lag < count; i++)
      acc += (int64_t)zs_audio_ring_at(c->ring, end, count, i, 0u) * zs_audio_ring_at(c->ring, end, count, (uint32_t)((int)i + lag), ch);
    if (acc > best) { best = acc; best_lag = lag; }
  }
  *lag_out = best_lag;
  return true;
}
