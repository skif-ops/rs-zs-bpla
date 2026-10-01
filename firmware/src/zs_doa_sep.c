#include "zs_doa_sep.h"

#include <math.h>
#include <string.h>

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

#define FS_DEC (32000.0f / (float)ZS_COMB_BEARING_DECIM)
#define BIN_HZ (FS_DEC / (float)ZS_COMB_BEARING_N)
#define CELL_DEG (360.0f / (float)ZS_DOA_CELLS)
#define SPREAD_DEG 3.0f
#define SPREAD_CELLS 4
#define BG_HALF 15u                /* background: median of the 31 bins around */
#define MAX_RESIDUAL_US 25.0f
#define MAX_NORM_ERROR 0.35f
#define LABEL_STEP_HZ 0.5f
#define LABEL_FOLD 0.06f
#define LABEL_FOLLOW 0.1f
#define MASK_FS 32000.0f
#define MASK_DOMINANCE 2.0f          /* another direction takes a bin when its weight is this many times the target's */
#define MASK_EPS 0.02f               /* the misfit of the right direction with real phase errors (calibration, sigma) */

static float wrap360(float a) {
  a = fmodf(a, 360.0f);
  return a < 0.0f ? a + 360.0f : a;
}

static float ang_dist(float a, float b) { return fabsf(fmodf(a - b + 540.0f, 360.0f) - 180.0f); }

void zs_doa_sep_init(zs_doa_sep_t *s) {
  if (!s) return;
  memset(s, 0, sizeof(*s));
  s->next_id = 1u;
}

void zs_doa_sep_reset(zs_doa_sep_t *s) {
  if (!s) return;
  memset(s->memory, 0, sizeof(s->memory));
  memset(s->track, 0, sizeof(s->track));
  memset(s->recent, 0, sizeof(s->recent));
}

/* a lost track remembered (the oldest memory makes room) */
static void remember_lost(zs_doa_sep_t *s, const zs_doa_track_t *tr) {
  if (tr->since_bearing == 255u) return;                       /* never had a bearing: nothing to come back to */
  unsigned slot = 0u;
  for (unsigned i = 0u; i < ZS_DOA_MAX_TRACKS; i++) {
    if (!s->recent[i].id) { slot = i; break; }
    if (s->recent[i].last_bearing_window < s->recent[slot].last_bearing_window) slot = i;
  }
  s->recent[slot].id = tr->id;
  s->recent[slot].last_az_deg = tr->last_az_deg;
  s->recent[slot].rate_deg = tr->rate_deg;
  s->recent[slot].label_hz = tr->label_hz;
  s->recent[slot].last_bearing_window = s->windows - tr->since_bearing;
}

/* a remembered track a new peak at az continues: where it would be now; -1 when none */
static int recall(const zs_doa_sep_t *s, float az) {
  int best = -1;
  float best_d = 1e9f;
  for (unsigned i = 0u; i < ZS_DOA_MAX_TRACKS; i++) {
    const zs_doa_recent_t *r = &s->recent[i];
    if (!r->id) continue;
    const uint32_t gap = s->windows - r->last_bearing_window;
    if (gap > ZS_DOA_RECALL_WINDOWS + ZS_DOA_MISS_MAX + 1u) continue;
    const float pred = wrap360(r->last_az_deg + r->rate_deg * (float)gap);
    const float d = ang_dist(az, pred), gate = 2.0f * ZS_DOA_GATE_DEG + 0.5f * fabsf(r->rate_deg) * (float)gap;
    if (d <= gate && d < best_d) { best_d = d; best = (int)i; }
  }
  return best;
}

/* k-th smallest of v[0..n) (v is reordered) */
static float select_kth(float *v, unsigned n, unsigned k) {
  unsigned lo = 0u, hi = n - 1u;
  while (lo < hi) {
    const float pivot = v[(lo + hi) / 2u];
    unsigned i = lo, j = hi;
    while (i <= j) {
      while (v[i] < pivot) i++;
      while (v[j] > pivot) { if (j == 0u) break; j--; }
      if (i <= j) {
        const float t = v[i]; v[i] = v[j]; v[j] = t;
        i++;
        if (j == 0u) break;
        j--;
      }
    }
    if (k <= j) hi = j;
    else if (k >= i) lo = i;
    else return v[k];
  }
  return v[k];
}

/* One bin's direction from the three averaged normalised cross spectra.  The vertical pair (mic 4, 15 cm up) can wrap
   above ~1 kHz, the triangle's pairs near 1.4 kHz: every delay within the pair's reach is tried. */
static bool bin_direction(const zs_bearing_ctx_t *ctx, const zs_complex_t m[ZS_SPATIAL_REF_TDOA_COUNT], float f_hz,
                          float temperature_c, float *az, float *el) {
  const float c = zs_spatial_speed_of_sound(temperature_c);
  const float period_us = 1.0e6f / f_hz;
  float cand[ZS_SPATIAL_REF_TDOA_COUNT][3];
  unsigned nc[ZS_SPATIAL_REF_TDOA_COUNT];
  for (unsigned j = 0u; j < ZS_SPATIAL_REF_TDOA_COUNT; j++) {
    const float *a = ctx->geometry.position_m[j + 1u], *r = ctx->geometry.position_m[0];
    const float d = sqrtf((a[0] - r[0]) * (a[0] - r[0]) + (a[1] - r[1]) * (a[1] - r[1]) + (a[2] - r[2]) * (a[2] - r[2]));
    const float reach_us = d / c * 1.0e6f + 5.0f;
    const float tau = -atan2f(m[j].im, m[j].re) / (2.0f * (float)M_PI * f_hz) * 1.0e6f;
    nc[j] = 0u;
    for (int w = -1; w <= 1; w++) {
      const float t = tau + (float)w * period_us;
      if (fabsf(t) <= reach_us && nc[j] < 3u) cand[j][nc[j]++] = t;
    }
    if (nc[j] == 0u) return false;
  }
  float best_res = 1e30f;
  bool found = false;
  for (unsigned a = 0u; a < nc[0]; a++)
    for (unsigned b = 0u; b < nc[1]; b++)
      for (unsigned e = 0u; e < nc[2]; e++) {
        const float tau[ZS_SPATIAL_REF_TDOA_COUNT] = {cand[0][a], cand[1][b], cand[2][e]};
        zs_spatial_solution_t sol;
        (void)zs_spatial_direction_from_reference_tdoas(&ctx->geometry, tau, temperature_c, &sol);
        if (sol.raw_vector_norm <= 0.0f || fabsf(sol.raw_vector_norm - 1.0f) > MAX_NORM_ERROR || sol.residual_us > MAX_RESIDUAL_US)
          continue;
        if (sol.residual_us < best_res) { best_res = sol.residual_us; *az = sol.azimuth_deg; *el = sol.elevation_deg; found = true; }
      }
  return found;
}

/* The window's bins with a direction: ws->bins[], returns their number. */
static unsigned window_bins(const zs_bearing_ctx_t *ctx, const float *memory, float temperature_c, zs_doa_workspace_t *ws) {
  const unsigned kmin = (unsigned)ceilf(ZS_DOA_FMIN_HZ / BIN_HZ), kmax = (unsigned)floorf(ZS_DOA_FMAX_HZ / BIN_HZ);
  const unsigned klo = kmin > BG_HALF ? kmin - BG_HALF : 0u, khi = kmax + BG_HALF;
  memset(ws->cross, 0, sizeof(ws->cross));
  memset(ws->power, 0, sizeof(ws->power));
  for (unsigned f = 0u; f < ZS_COMB_BEARING_FRAMES; f++) {
    if (!zs_comb_bearing_frame_spectra(memory, f, ws->spectrum)) return 0u;
    for (unsigned k = klo; k <= khi; k++) {
      const zs_complex_t R = ws->spectrum[0][k];
      ws->power[k] += R.re * R.re + R.im * R.im;
      for (unsigned j = 0u; j < ZS_SPATIAL_REF_TDOA_COUNT; j++) {
        const zs_complex_t X = ws->spectrum[j + 1u][k];
        ws->power[k] += X.re * X.re + X.im * X.im;
        if (k < kmin || k > kmax) continue;
        const float cr = X.re * R.re + X.im * R.im, ci = X.im * R.re - X.re * R.im;
        const float mag = sqrtf(cr * cr + ci * ci);
        if (mag > 1e-20f) { ws->cross[j][k].re += cr / mag; ws->cross[j][k].im += ci / mag; }
      }
    }
  }
  unsigned n = 0u;
  for (unsigned k = kmin; k <= kmax && n < ZS_DOA_MAX_BINS; k++) {
    float around[2u * BG_HALF + 1u];
    unsigned na = 0u;
    for (unsigned i = (k >= klo + BG_HALF ? k - BG_HALF : klo); i <= k + BG_HALF && i <= khi; i++) around[na++] = ws->power[i];
    const float bg = select_kth(around, na, na / 2u);
    if (!(ws->power[k] > 0.0f) || !(bg > 0.0f)) continue;
    const float excess = 10.0f * log10f(ws->power[k] / bg);
    if (excess < ZS_DOA_MIN_EXCESS_DB) continue;
    zs_complex_t m[ZS_SPATIAL_REF_TDOA_COUNT];
    float coherence = 1.0f;
    for (unsigned j = 0u; j < ZS_SPATIAL_REF_TDOA_COUNT; j++) {
      m[j].re = ws->cross[j][k].re / (float)ZS_COMB_BEARING_FRAMES;
      m[j].im = ws->cross[j][k].im / (float)ZS_COMB_BEARING_FRAMES;
      const float a = sqrtf(m[j].re * m[j].re + m[j].im * m[j].im);
      if (a < coherence) coherence = a;
    }
    if (coherence < ZS_DOA_MIN_COHERENCE) continue;
    float az = 0.0f, el = 0.0f;
    if (!bin_direction(ctx, m, (float)k * BIN_HZ, temperature_c, &az, &el)) continue;
    zs_doa_bin_t *b = &ws->bins[n++];
    b->k = (uint16_t)k;
    b->az_deg = az;
    b->el_deg = el;
    b->coherence = coherence;
    b->excess_db = excess;
    b->power = ws->power[k];
  }
  return n;
}

static float bin_weight(const zs_doa_bin_t *b) {
  return (b->coherence - ZS_DOA_MIN_COHERENCE) / (1.0f - ZS_DOA_MIN_COHERENCE) * fminf(b->excess_db, 20.0f);
}

static void add_to_hist(float *hist, float az, float w) {
  const int centre = (int)lroundf(az / CELL_DEG);
  for (int d = -SPREAD_CELLS; d <= SPREAD_CELLS; d++) {
    const int cell = ((centre + d) % (int)ZS_DOA_CELLS + (int)ZS_DOA_CELLS) % (int)ZS_DOA_CELLS;
    const float off = (float)cell * CELL_DEG;
    const float dist = ang_dist(off, az);
    hist[cell] += w * expf(-0.5f * (dist / SPREAD_DEG) * (dist / SPREAD_DEG));
  }
}

/* sub-cell position of a memory peak */
static float peak_az(const float *h, unsigned i) {
  const float l = h[(i + ZS_DOA_CELLS - 1u) % ZS_DOA_CELLS], c = h[i], r = h[(i + 1u) % ZS_DOA_CELLS];
  const float den = l - 2.0f * c + r;
  float frac = 0.0f;
  if (fabsf(den) > 1e-12f) frac = 0.5f * (l - r) / den;
  if (frac > 0.5f) frac = 0.5f;
  if (frac < -0.5f) frac = -0.5f;
  return wrap360(((float)i + frac) * CELL_DEG);
}

static unsigned memory_peaks(const float *h, unsigned out[ZS_DOA_MAX_TRACKS]) {
  bool blocked[ZS_DOA_CELLS];
  unsigned n = 0u;
  float first = 0.0f;
  memset(blocked, 0, sizeof(blocked));
  while (n < ZS_DOA_MAX_TRACKS) {
    int best = -1;
    for (unsigned i = 0u; i < ZS_DOA_CELLS; i++) if (!blocked[i] && (best < 0 || h[i] > h[best])) best = (int)i;
    if (best < 0 || h[best] < ZS_DOA_PEAK_ABS || (n > 0u && h[best] < ZS_DOA_PEAK_REL * first)) break;
    const unsigned i = (unsigned)best;
    const bool local = h[i] >= h[(i + ZS_DOA_CELLS - 1u) % ZS_DOA_CELLS] && h[i] >= h[(i + 1u) % ZS_DOA_CELLS];
    for (unsigned j = 0u; j < ZS_DOA_CELLS; j++) if (ang_dist((float)j * CELL_DEG, (float)i * CELL_DEG) < ZS_DOA_PEAK_SEP_DEG) blocked[j] = true;
    if (!local) continue;                                   /* the shoulder of a stronger peak */
    if (n == 0u) first = h[i];
    out[n++] = i;
  }
  return n;
}

static unsigned popcount4(uint8_t v) {
  unsigned n = 0u;
  for (unsigned i = 0u; i < ZS_DOA_CONFIRM_N; i++) n += (v >> i) & 1u;
  return n;
}

/* score of a fundamental: weight of the lines on its harmonics minus a penalty for its harmonics below 1.5 kHz that
   are not there */
static float sieve_score(const float *f, const float *w, unsigned n, float f0) {
  float expl = 0.0f;
  uint32_t seen = 0u;
  for (unsigned i = 0u; i < n; i++) {
    const float h = roundf(f[i] / f0);
    if (h < 1.0f) continue;
    const float tol = fmaxf(BIN_HZ, 0.012f * h * f0);
    if (fabsf(f[i] - h * f0) <= tol) { expl += w[i]; if (h <= 31.0f) seen |= 1u << (unsigned)h; }
  }
  unsigned missing = 0u;
  for (unsigned h = 1u; (float)h * f0 <= 1500.0f && h <= 31u; h++) if (!(seen & (1u << h))) missing++;
  return expl - 0.35f * (float)missing;
}

/* fundamental 100..400 Hz explaining the lines: the highest within 85 % of the best score (harmonic sieve) */
static float sieve(const float *f, const float *w, unsigned n) {
  const unsigned nc = (unsigned)((ZS_DOA_LABEL_MAX_HZ - ZS_DOA_LABEL_MIN_HZ) / LABEL_STEP_HZ) + 1u;
  float best = -1e30f, chosen = 0.0f;
  if (n < 2u) return 0.0f;
  for (unsigned c = 0u; c < nc; c++) {
    const float sc = sieve_score(f, w, n, ZS_DOA_LABEL_MIN_HZ + (float)c * LABEL_STEP_HZ);
    if (sc > best) best = sc;
  }
  if (!(best > 0.0f)) return 0.0f;
  for (unsigned c = nc; c-- > 0u;) {
    const float f0 = ZS_DOA_LABEL_MIN_HZ + (float)c * LABEL_STEP_HZ;
    if (sieve_score(f, w, n, f0) >= 0.85f * best) { chosen = f0; break; }
  }
  return chosen;
}

/* an estimate in an integer ratio to the label (within LABEL_FOLD) folded onto it; 0 when unrelated */
static float fold_onto(float v, float label) {
  if (v <= 0.0f || label <= 0.0f) return 0.0f;
  const float r = v >= label ? v / label : label / v, k = roundf(r);
  if (k < 1.0f || fabsf(r - k) > LABEL_FOLD * k) return 0.0f;
  return v >= label ? v / k : v * k;
}

static void update_label(zs_doa_track_t *t, float estimate) {
  if (estimate <= 0.0f) return;
  if (t->label_hz <= 0.0f) {
    t->label_start[t->label_count++] = estimate;
    if (t->label_count < ZS_DOA_LABEL_START) return;
    float v[ZS_DOA_LABEL_START];
    memcpy(v, t->label_start, sizeof(v));
    t->label_hz = select_kth(v, ZS_DOA_LABEL_START, ZS_DOA_LABEL_START / 2u);
    t->label_count = 0u;
    return;
  }
  const float folded = fold_onto(estimate, t->label_hz);
  if (folded > 0.0f) t->label_hz += LABEL_FOLLOW * (folded - t->label_hz);
}

unsigned zs_doa_sep_push(zs_doa_sep_t *s, const zs_bearing_ctx_t *ctx, const float *memory, float temperature_c,
                         zs_doa_workspace_t *ws, zs_doa_target_t out[ZS_DOA_MAX_TRACKS]) {
  if (!s || !ctx || !memory || !ws || !out) return 0u;
  const unsigned nb = window_bins(ctx, memory, temperature_c, ws);
  s->windows++;
  s->bins_used += nb;

  memset(ws->window_hist, 0, sizeof(ws->window_hist));
  for (unsigned i = 0u; i < nb; i++) add_to_hist(ws->window_hist, ws->bins[i].az_deg, bin_weight(&ws->bins[i]));
  for (unsigned c = 0u; c < ZS_DOA_CELLS; c++) s->memory[c] = ZS_DOA_DECAY * s->memory[c] + ws->window_hist[c];

  unsigned peaks[ZS_DOA_MAX_TRACKS];
  const unsigned np = memory_peaks(s->memory, peaks);
  bool used[ZS_DOA_MAX_TRACKS] = {false, false, false};

  /* continue the tracks: where the last bearing and the rate of turn put it (the memory lags behind a fast pass), the
     nearest free memory peak within the gate (wider by the turn), or the window's own support there */
  for (unsigned t = 0u; t < ZS_DOA_MAX_TRACKS; t++) {
    zs_doa_track_t *tr = &s->track[t];
    if (!tr->live) continue;
    if (tr->since_bearing < 255u) tr->since_bearing++;
    const bool fresh = tr->since_bearing <= ZS_DOA_MISS_MAX + 1u;
    const float pred = fresh ? wrap360(tr->last_az_deg + tr->rate_deg * (float)tr->since_bearing) : tr->az_deg;
    const float gate = ZS_DOA_GATE_DEG + (fresh ? fminf(2.0f * fabsf(tr->rate_deg) * (float)tr->since_bearing, 12.0f) : 0.0f);
    int best = -1;
    float best_d = gate;
    for (unsigned p = 0u; p < np; p++) {
      if (used[p]) continue;
      const float d = ang_dist(peak_az(s->memory, peaks[p]), pred);
      if (d <= best_d) { best_d = d; best = (int)p; }
    }
    float support = 0.0f;
    for (unsigned c = 0u; c < ZS_DOA_CELLS; c++)
      if (ang_dist((float)c * CELL_DEG, pred) <= gate && ws->window_hist[c] > support) support = ws->window_hist[c];
    const bool own = support >= ZS_DOA_SUPPORT;
    tr->support = (uint8_t)(((tr->support << 1) | (own ? 1u : 0u)) & ((1u << ZS_DOA_CONFIRM_N) - 1u));
    if (best >= 0) used[best] = true;
    if (best >= 0 || (fresh && own)) {
      tr->az_deg = fresh ? pred : peak_az(s->memory, peaks[best]);
      tr->misses = 0u;
    } else if (++tr->misses > ZS_DOA_MISS_MAX) {
      remember_lost(s, tr);
      memset(tr, 0, sizeof(*tr));
      continue;
    } else tr->az_deg = pred;
    if (tr->age < 255u) tr->age++;
  }
  /* new tracks for the remaining peaks, in free slots (not the lagging memory of a live track) */
  for (unsigned p = 0u; p < np; p++) {
    if (used[p]) continue;
    const float paz = peak_az(s->memory, peaks[p]);
    bool near_live = false;
    for (unsigned t = 0u; t < ZS_DOA_MAX_TRACKS; t++)
      if (s->track[t].live && ang_dist(s->track[t].az_deg, paz) < ZS_DOA_PEAK_SEP_DEG) near_live = true;
    if (near_live) continue;
    for (unsigned t = 0u; t < ZS_DOA_MAX_TRACKS; t++) {
      zs_doa_track_t *tr = &s->track[t];
      if (tr->live) continue;
      memset(tr, 0, sizeof(*tr));
      tr->live = true;
      tr->az_deg = paz;
      tr->since_bearing = 255u;
      const int r = recall(s, paz);
      if (r >= 0) {                                           /* a lost track comes back */
        zs_doa_recent_t *rc = &s->recent[r];
        const uint32_t gap = s->windows - rc->last_bearing_window;
        tr->id = rc->id;
        tr->label_hz = rc->label_hz;
        tr->rate_deg = rc->rate_deg;
        tr->last_az_deg = rc->last_az_deg;
        tr->since_bearing = (uint8_t)(gap > 254u ? 254u : gap);
        memset(rc, 0, sizeof(*rc));
      } else {
        tr->id = s->next_id++;
        if (s->next_id == 0u) s->next_id = 1u;
      }
      float support = 0.0f;
      for (unsigned c = 0u; c < ZS_DOA_CELLS; c++)
        if (ang_dist((float)c * CELL_DEG, tr->az_deg) <= ZS_DOA_GATE_DEG && ws->window_hist[c] > support) support = ws->window_hist[c];
      tr->support = support >= ZS_DOA_SUPPORT ? 1u : 0u;
      tr->age = 1u;
      break;
    }
  }

  /* each track's bins of the window: bearing, label */
  unsigned n = 0u;
  for (unsigned t = 0u; t < ZS_DOA_MAX_TRACKS; t++) {
    zs_doa_track_t *tr = &s->track[t];
    if (!tr->live) continue;
    zs_doa_target_t *o = &out[n++];
    memset(o, 0, sizeof(*o));
    o->id = tr->id;
    if (popcount4(tr->support) >= ZS_DOA_CONFIRM_M) tr->confirmed = true;
    else if (tr->support == 0u) tr->confirmed = false;
    o->confirmed = tr->confirmed;
    {
      const int cell = (int)lroundf(tr->az_deg / CELL_DEG) % (int)ZS_DOA_CELLS;
      o->strength = s->memory[cell];
    }
    float sx = 0.0f, sy = 0.0f, sw = 0.0f, sel = 0.0f, sw2 = 0.0f;
    float *fpk = ws->line_hz, *wpk = ws->line_w;
    unsigned members = 0u, npk = 0u;
    for (unsigned i = 0u; i < nb; i++) {
      const zs_doa_bin_t *b = &ws->bins[i];
      if (ang_dist(b->az_deg, tr->az_deg) > ZS_DOA_ASSIGN_DEG) continue;
      const float w = bin_weight(b) + 1e-3f;
      sx += w * sinf(b->az_deg * (float)M_PI / 180.0f);
      sy += w * cosf(b->az_deg * (float)M_PI / 180.0f);
      sel += w * b->el_deg;
      sw += w;
      sw2 += w * w;
      members++;
      /* a local maximum among the track's own bins: a line for the label */
      bool peak = true;
      for (unsigned j = 0u; j < nb && peak; j++) {
        const zs_doa_bin_t *q = &ws->bins[j];
        if ((q->k + 1u == b->k || q->k == b->k + 1u) && ang_dist(q->az_deg, tr->az_deg) <= ZS_DOA_ASSIGN_DEG && q->power > b->power) peak = false;
      }
      if (peak) { fpk[npk] = (float)b->k * BIN_HZ; wpk[npk++] = b->power; }
    }
    o->bins = (uint8_t)(members > 255u ? 255u : members);
    if (members >= ZS_DOA_MIN_BINS && sw > 0.0f) {
      const float az = wrap360(atan2f(sx, sy) * 180.0f / (float)M_PI);
      float var = 0.0f;
      for (unsigned i = 0u; i < nb; i++) {
        const zs_doa_bin_t *b = &ws->bins[i];
        if (ang_dist(b->az_deg, tr->az_deg) > ZS_DOA_ASSIGN_DEG) continue;
        const float d = ang_dist(b->az_deg, az);
        var += (bin_weight(b) + 1e-3f) * d * d;
      }
      var /= sw;
      const float n_eff = sw * sw / sw2;
      float sigma = sqrtf(var / fmaxf(n_eff, 1.0f)) + 0.5f;
      if (sigma > 45.0f) sigma = 45.0f;
      o->has_bearing = true;
      o->bearing.valid = true;
      o->bearing.azimuth_deg = az;
      if (tr->since_bearing < 255u && tr->since_bearing > 0u) {
        const float turn = (fmodf(az - tr->last_az_deg + 540.0f, 360.0f) - 180.0f) / (float)tr->since_bearing;
        tr->rate_deg = tr->rate_deg == 0.0f ? turn : 0.6f * tr->rate_deg + 0.4f * turn;
      }
      tr->last_az_deg = az;
      tr->since_bearing = 0u;
      tr->az_deg = az;
      o->bearing.elevation_deg = sel / sw;
      o->bearing.sigma_deg = sigma;
      o->bearing.confidence = fminf(1.0f, n_eff / 10.0f);
      o->bearing.frames_used = (uint8_t)ZS_COMB_BEARING_FRAMES;
      if (o->confirmed) {
        /* the label from the lines' powers on a log scale (the sieve's weights) */
        float wmin = 1e30f;
        for (unsigned i = 0u; i < npk; i++) if (wpk[i] < wmin) wmin = wpk[i];
        for (unsigned i = 0u; i < npk; i++) wpk[i] = 1.0f + log10f(wpk[i] / wmin);
        update_label(tr, sieve(fpk, wpk, npk));
      }
    }
    o->bearing.f0_hz = tr->label_hz;
  }
  return n;
}

/* ---- a target's own window: soft mask by direction ------------------------------------------------------------- */
/* sqrt of the periodic Hann window is sin(pi n / N): by rotation */
typedef struct { float s, c, ds, dc; } rot_t;
static void rot_init(rot_t *r) { r->s = 0.0f; r->c = 1.0f; r->ds = sinf((float)M_PI / (float)ZS_DOA_MASK_N); r->dc = cosf((float)M_PI / (float)ZS_DOA_MASK_N); }
static float rot_next(rot_t *r) {
  const float v = r->s;
  const float s = r->s * r->dc + r->c * r->ds, c = r->c * r->dc - r->s * r->ds;
  r->s = s; r->c = c;
  return v < 0.0f ? 0.0f : v;
}

bool zs_doa_sep_mask_window(const zs_bearing_ctx_t *ctx, const zs_audio_ring_t *ring, uint64_t end_sample, uint32_t samples,
                            const zs_bearing_t *tracks, unsigned count, unsigned which, float temperature_c,
                            zs_doa_mask_workspace_t *ws, int16_t *out) {
  const uint32_t lead = ZS_DOA_MASK_HOP, span = samples + lead;
  if (!ctx || !ring || !tracks || !ws || !out || count == 0u || count > ZS_DOA_MAX_TRACKS || which >= count) return false;
  if (samples < ZS_DOA_MASK_N || end_sample < (uint64_t)span || !zs_audio_ring_range_ok(ring, end_sample, span)) return false;
  const float c = zs_spatial_speed_of_sound(temperature_c);
  /* each track's plane wave: arrival of every mic after mic 1, seconds */
  float tau[ZS_DOA_MAX_TRACKS][ZS_SPATIAL_MIC_COUNT];
  for (unsigned t = 0u; t < count; t++) {
    const float a = tracks[t].azimuth_deg * (float)M_PI / 180.0f, e = tracks[t].elevation_deg * (float)M_PI / 180.0f;
    const float u[3] = {sinf(a) * cosf(e), cosf(a) * cosf(e), sinf(e)};
    for (unsigned m = 0u; m < ZS_SPATIAL_MIC_COUNT; m++) {
      float d = 0.0f;
      for (unsigned k = 0u; k < 3u; k++) d += (ctx->geometry.position_m[m][k] - ctx->geometry.position_m[0][k]) * u[k];
      tau[t][m] = -d / c;
    }
  }
  memset(ws->carry, 0, sizeof(ws->carry));
  /* frames every hop from `lead` samples before the window (span index 0); window sample i is span index i + lead.
     Each frame completes the span indices [start, start + hop) with the previous frame's second half; samples after
     the span are zeros (the analysis-synthesis pair sums to one whatever the content). */
  for (uint32_t start = 0u; start < span; start += ZS_DOA_MASK_HOP) {
    for (unsigned m = 0u; m < ZS_SPATIAL_MIC_COUNT; m++) {
      rot_t r;
      rot_init(&r);
      for (unsigned n = 0u; n < ZS_DOA_MASK_N; n++) {
        const uint32_t i = start + n;
        const float x = i < span ? (float)zs_audio_ring_at(ring, end_sample, span, i, m) : 0.0f;
        ws->spectrum[m][n].re = x * rot_next(&r);
        ws->spectrum[m][n].im = 0.0f;
      }
      if (!zs_fft_radix2(ws->spectrum[m], ZS_DOA_MASK_N)) return false;
    }
    /* e^{i w_k tau} for every track and mic by rotation over the bins (w_k = k * dw) */
    float rr[ZS_DOA_MAX_TRACKS][ZS_SPATIAL_MIC_COUNT], ri[ZS_DOA_MAX_TRACKS][ZS_SPATIAL_MIC_COUNT];
    float sr[ZS_DOA_MAX_TRACKS][ZS_SPATIAL_MIC_COUNT], si[ZS_DOA_MAX_TRACKS][ZS_SPATIAL_MIC_COUNT];
    for (unsigned t = 0u; t < count; t++)
      for (unsigned m = 0u; m < ZS_SPATIAL_MIC_COUNT; m++) {
        const float step = 2.0f * (float)M_PI * MASK_FS / (float)ZS_DOA_MASK_N * tau[t][m];
        rr[t][m] = 1.0f; ri[t][m] = 0.0f;
        sr[t][m] = cosf(step); si[t][m] = sinf(step);
      }
    for (unsigned k = 0u; k <= ZS_DOA_MASK_N / 2u; k++) {
      float fit[ZS_DOA_MAX_TRACKS], energy = 0.0f;
      for (unsigned m = 0u; m < ZS_SPATIAL_MIC_COUNT; m++)
        energy += ws->spectrum[m][k].re * ws->spectrum[m][k].re + ws->spectrum[m][k].im * ws->spectrum[m][k].im;
      for (unsigned t = 0u; t < count; t++) {
        float br = 0.0f, bi = 0.0f;           /* sum over the mics of X_m e^{+i w tau_m}: the plane wave aligned */
        for (unsigned m = 0u; m < ZS_SPATIAL_MIC_COUNT; m++) {
          const float cr = rr[t][m], ci = ri[t][m];
          br += ws->spectrum[m][k].re * cr - ws->spectrum[m][k].im * ci;
          bi += ws->spectrum[m][k].re * ci + ws->spectrum[m][k].im * cr;
          rr[t][m] = cr * sr[t][m] - ci * si[t][m];
          ri[t][m] = cr * si[t][m] + ci * sr[t][m];
        }
        /* misfit of the track's plane wave: 0 when the four phases are exactly its own (one source from there); the
           weight 1 / (misfit + MASK_EPS)^2 stays sharp at low frequencies, where a 12 cm array barely tells
           directions apart (the other direction's misfit at 170 Hz is ~0.1) */
        const float f = energy > 1e-20f ? (br * br + bi * bi) / ((float)ZS_SPATIAL_MIC_COUNT * energy) : 1.0f;
        const float misfit = f < 1.0f ? 1.0f - f : 0.0f;
        const float p = 1.0f / ((misfit + MASK_EPS) * (misfit + MASK_EPS));
        fit[t] = p;
      }
      /* only a direction that explains the bin clearly better takes it away (another target's line): noise and what no
         direction explains stay as they are, like the comb notch of zs_air_gate_suppress_combs */
      float taken = 0.0f;
      for (unsigned t = 0u; t < count; t++) if (t != which && fit[t] > MASK_DOMINANCE * fit[which]) taken += fit[t];
      const float g = fit[which] / (fit[which] + taken);
      ws->spectrum[0][k].re *= g;
      ws->spectrum[0][k].im *= g;
      if (k > 0u && k < ZS_DOA_MASK_N / 2u) {
        ws->spectrum[0][ZS_DOA_MASK_N - k].re = ws->spectrum[0][k].re;
        ws->spectrum[0][ZS_DOA_MASK_N - k].im = -ws->spectrum[0][k].im;
      }
    }
    if (!zs_ifft_radix2(ws->spectrum[0], ZS_DOA_MASK_N)) return false;
    rot_t r;
    rot_init(&r);
    for (unsigned n = 0u; n < ZS_DOA_MASK_HOP; n++) {
      const float y = ws->spectrum[0][n].re * rot_next(&r) + ws->carry[n];
      const uint32_t i = start + n;
      if (i >= lead && i - lead < samples) {
        const float q = (float)lroundf(y);
        out[i - lead] = (int16_t)(q > 32767.0f ? 32767 : (q < -32768.0f ? -32768 : q));
      }
    }
    for (unsigned n = ZS_DOA_MASK_HOP; n < ZS_DOA_MASK_N; n++) ws->carry[n - ZS_DOA_MASK_HOP] = ws->spectrum[0][n].re * rot_next(&r);
  }
  return true;
}
