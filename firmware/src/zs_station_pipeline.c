#include "zs_station_pipeline.h"
#include <math.h>
#include <stdint.h>
#include <string.h>

/* Most frequent UAV class among the weak-or-better votes: what the event names before the 5/8 type consensus. */
static uint8_t leading_uav_class(const zs_classifier_consensus_t *v) {
  uint8_t best = ZS_CLASS_UNKNOWN, best_n = 0u;
  for (uint8_t c = ZS_CLASS_PISTON_UAV; c <= ZS_CLASS_ELECTRIC_UAV; c++) {
    uint8_t n = 0u;
    for (uint8_t i = 0u; i < v->count; i++) if (v->class_id[i] == c && v->confidence_u8[i] >= ZS_PRESENCE_WEAK_CONFIDENCE_U8) n++;
    if (n > best_n) { best_n = n; best = c; }
  }
  return best;
}

static uint8_t detector_profile_for(uint8_t family) {
  return family == ZS_FAMILY_PROP_PISTON ? 1u : (family == ZS_FAMILY_TURBINE_JET ? 2u : 0u);
}

bool zs_station_pipeline_init(zs_station_pipeline_t *p, const zs_station_pipeline_port_t *port,
                              zs_complex_t *scratch, int16_t *window) {
  if (!p || !port || !port->extract || !port->emit || !scratch || !window || port->channel >= ZS_AUDIO_CHANNELS) return false;
  if (((uintptr_t)(const void *)window & 3u) != 0u) return false;                    /* lent as floats to the comb bearings */
  memset(p, 0, sizeof(*p));
  p->port = port;
  p->scratch = scratch;
  p->window = window;
  zs_classifier_consensus_init(&p->votes);
  zs_air_gate_init(&p->gate);
  zs_bearing_init(&p->bearing_ctx, NULL);
  zs_doa_sep_init(&p->doa);
  p->classification.unknown = true;
  p->next_window_end = ZS_PIPELINE_WINDOW_SAMPLES;
  return true;
}

void zs_station_pipeline_fill_detection(const zs_station_pipeline_t *p, uint64_t end_sample, zs_detection_t *d) {
  memset(d, 0, sizeof(*d));
  d->schema_ver = 4u;
  d->station_id = p->port->station_id;
  d->boot_id = p->port->boot_id;
  d->seq_no = p->seq_no;
  d->event_id = ((uint64_t)p->port->boot_id << 32) | p->seq_no;
  d->event_time_us = p->port->sample_time_us ? p->port->sample_time_us(p->port->ctx, end_sample) : 0;
  d->classification = p->classification;
  d->classification.confidence_u8 = p->presence.confidence_u8;     /* level 1 confidence governs the event */
  d->hierarchy = p->hierarchy;
  if (p->classification.unknown && p->presence.level == ZS_PRESENCE_CONFIRMED) {
    /* confirmed at level 1 before the 5/8 type consensus: name the leading UAV class, keep `unknown` set */
    d->classification.class_id = leading_uav_class(&p->votes);
    if (d->hierarchy.family_status == ZS_DECISION_UNKNOWN) d->hierarchy.family_status = ZS_DECISION_CANDIDATE;
  }
  memcpy(d->features, p->features, sizeof(d->features));
  if (p->last_bearing.valid && p->last_bearing_end == end_sample) {
    const zs_bearing_t *b = &p->last_bearing;
    long az = lroundf(b->azimuth_deg * 100.0f) % 36000L;
    const long sigma = lroundf(b->sigma_deg * 100.0f);
    if (az < 0) az += 36000L;
    d->doa.azimuth_cdeg = (uint16_t)az;
    d->doa.elevation_cdeg = (int16_t)lroundf(b->elevation_deg * 100.0f);
    d->doa.sigma_cdeg = (uint16_t)(sigma > 65535L ? 65535L : sigma);
    d->doa.valid = true;
    d->spatial.tdoa12_us = (int16_t)lroundf(b->tdoa_us[0]);
    d->spatial.tdoa13_us = (int16_t)lroundf(b->tdoa_us[1]);
    d->spatial.tdoa14_us = (int16_t)lroundf(b->tdoa_us[2]);
    d->spatial.residual_us = (uint16_t)lroundf(b->residual_us);
    d->spatial.confidence_u8 = (uint8_t)lroundf(b->confidence * 255.0f);
    d->spatial.geometry_id = p->bearing_ctx.geometry.geometry_id;
    d->spatial.valid_flags = 0x03u;                                   /* TDOAs and direction valid */
  }
  d->sample_rate_hz = ZS_AIR_SAMPLE_RATE;
  d->detector_profile = detector_profile_for(p->hierarchy.family_id);
}

_Static_assert(ZS_PIPELINE_WINDOW_SAMPLES >= ZS_BEARING_FRAME_MEMORY, "the 1 s window lends the bearing frames");
_Static_assert(ZS_AIR_SCRATCH_COMPLEX * sizeof(zs_complex_t) >= sizeof(zs_spatial_gcc_workspace_t), "the gate scratch lends the GCC workspace");

_Static_assert(ZS_PIPELINE_WINDOW_SAMPLES * sizeof(int16_t) >= ZS_COMB_BEARING_MEMORY * sizeof(float), "the 1 s window lends the decimated span");
_Static_assert(ZS_AIR_SCRATCH_COMPLEX * sizeof(zs_complex_t) >= sizeof(zs_comb_bearing_workspace_t), "the gate scratch lends the comb workspace");
_Static_assert(ZS_COMB_BEARING_SPAN == ZS_PIPELINE_BEARING_SPAN, "both bearings cover the newest 0.5 s of the window");
_Static_assert(ZS_AIR_SCRATCH_COMPLEX * sizeof(zs_complex_t) >= sizeof(zs_doa_workspace_t), "the gate scratch lends the direction workspace");
_Static_assert(ZS_AIR_SCRATCH_COMPLEX * sizeof(zs_complex_t) >= sizeof(zs_doa_mask_workspace_t), "the gate scratch lends the mask workspace");
_Static_assert(ZS_PIPELINE_WINDOW_SAMPLES == 2u * ZS_PIPELINE_HOP_SAMPLES, "a direction's window is two halves");

void zs_station_pipeline_set_stash(zs_station_pipeline_t *p, int16_t *stash) {
  if (!p) return;
  p->stash = stash;
  p->stash_target = 0u;
}

static float temperature_of(const zs_station_pipeline_t *p) {
  return p->port->temperature_c ? p->port->temperature_c(p->port->ctx) : 15.0f;
}

/* Bearings of the sources of a mixture from the window's decimated newest 0.5 s (memory_ok: in the window buffer): one
   per source from the bins of its own harmonics (all sources take part, each excludes the others' bins), the main one
   first.  Returns how many of out[] were filled (valid or not). */
static unsigned comb_bearings(zs_station_pipeline_t *p, bool memory_ok, zs_bearing_t out[ZS_COMB_BEARING_MAX_SOURCES]) {
  const unsigned n = p->source_count;
  if (!memory_ok) {
    for (unsigned i = 0u; i < n; i++) { memset(&out[i], 0, sizeof(out[i])); out[i].f0_hz = p->source_f0[i]; }
    p->comb_stats.attempts += n;
    p->comb_stats.no_audio += n;
    return n;
  }
  (void)zs_comb_bearings_from_memory(&p->bearing_ctx, &p->comb_stats, (const float *)(const void *)p->window, p->source_f0, n,
                                     temperature_of(p), (zs_comb_bearing_workspace_t *)(void *)p->scratch, out);
  p->comb_windows++;
  return n;
}

/* The full-band bearing of a single source (the window buffer and the gate scratch are idle by now). */
static void single_bearing(zs_station_pipeline_t *p, uint64_t end_sample, zs_bearing_t *out) {
  memset(out, 0, sizeof(*out));
  if (!p->ring) return;
  (void)zs_bearing_from_ring(&p->bearing_ctx, p->ring, end_sample, ZS_PIPELINE_BEARING_SPAN, temperature_of(p), p->window,
                             (zs_spatial_gcc_workspace_t *)(void *)p->scratch, out);
  if (p->last_gate.present) out->f0_hz = p->last_gate.window_f0_hz;           /* the source it follows, for the server */
}

/* ---- source tracks of a mixture ---------------------------------------------------------------------------------- */
static bool f0_near(float a, float b) { return a > 0.0f && b > 0.0f && fabsf(a - b) <= ZS_PIPELINE_SOURCE_F0_STEP * fminf(a, b); }
/* the same source after an octave (or 1:3) slip of the gate's fit: no second source */
static bool f0_family(float a, float b) {
  if (a <= 0.0f || b <= 0.0f) return false;
  const float r = fmaxf(a, b) / fminf(a, b), k = roundf(r);
  return k >= 1.0f && fabsf(r - k) <= ZS_PIPELINE_SOURCE_F0_STEP * k;
}

/* This window's sources the gate reports (main first) onto the source tracks: the nearest track within the step,
   else a free one, else the one heard longest ago.  A new track of the main source starts with the main stream's
   votes (its history before the mixture).  Then the tracks the gate did not report this window but heard within
   ZS_PIPELINE_SOURCE_HOLD_WINDOWS, and once heard beside another source, join the window's sources as they were (the
   gate's other combs come and go from
   window to window: a source it counts in one window and misses in the next is still there), unless it is of the
   family of a listed one (an octave slip of the fit is the same source).  Returns the number of the window's sources. */
static unsigned match_sources(zs_station_pipeline_t *p, unsigned reported) {
  for (unsigned k = 0u; k < ZS_PIPELINE_SOURCES; k++) {
    zs_pipeline_source_t *t = &p->sources[k];
    t->heard = false;
    if (t->f0_hz > 0.0f && p->windows - t->last_window > ZS_PIPELINE_SOURCE_HOLD_WINDOWS) t->f0_hz = 0.0f;
  }
  for (unsigned i = 0u; i < reported; i++) {
    int best = -1, spare = -1;
    for (unsigned k = 0u; k < ZS_PIPELINE_SOURCES; k++) {
      const zs_pipeline_source_t *t = &p->sources[k];
      if (t->heard) continue;
      if (f0_near(t->f0_hz, p->source_f0[i]) &&
          (best < 0 || fabsf(t->f0_hz - p->source_f0[i]) < fabsf(p->sources[best].f0_hz - p->source_f0[i]))) best = (int)k;
      if (t->f0_hz <= 0.0f) { if (spare < 0 || p->sources[spare].f0_hz > 0.0f) spare = (int)k; }
      else if (spare < 0 || (p->sources[spare].f0_hz > 0.0f && t->last_window < p->sources[spare].last_window)) spare = (int)k;
    }
    if (best < 0) {
      zs_pipeline_source_t *t = &p->sources[spare];
      for (unsigned o = 0u; o < ZS_PIPELINE_SOURCES; o++) {
        /* a new source is one target with the ones heard already (a multirotor's rotors run at different speeds, an
           engine has several combs) until their bearings tell them apart */
        const bool close = o != (unsigned)spare && p->sources[o].f0_hz > 0.0f;
        p->together[spare][o] = p->together[o][spare] = close ? (uint8_t)ZS_PIPELINE_TOGETHER_WINDOWS : 0u;
        p->same_target[spare][o] = p->same_target[o][spare] = close;
      }
      memset(t, 0, sizeof(*t));
      zs_classifier_consensus_init(&t->votes);
      t->classification.unknown = true;
      if (i == 0u) { t->votes = p->votes; t->classification = p->classification; t->hierarchy = p->hierarchy; }
      best = spare;
    }
    p->sources[best].f0_hz = p->source_f0[i];
    p->sources[best].last_window = p->windows;
    p->sources[best].heard = true;
    if (reported >= 2u) p->sources[best].with_others = true;
    p->source_of[i] = (uint8_t)best;
  }
  unsigned n = reported;
  for (unsigned k = 0u; k < ZS_PIPELINE_SOURCES && n < ZS_PIPELINE_SOURCES; k++) {
    zs_pipeline_source_t *t = &p->sources[k];
    bool listed = t->heard || t->f0_hz <= 0.0f || !t->with_others;
    for (unsigned i = 0u; i < n && !listed; i++) listed = f0_family(t->f0_hz, p->source_f0[i]);
    if (listed) continue;
    t->heard = true;                                         /* remembered: its f0 and age stay as they were */
    p->source_f0[n] = t->f0_hz;
    p->source_of[n++] = (uint8_t)k;
  }
  return n;
}

/* The level-1 decision of a source track: its votes with the gate's evidence for its comb (the main one's is the
   gate's result; another source the gate counts is a present comb of the same history). */
static void evaluate_source(zs_station_pipeline_t *p, unsigned i) {
  zs_pipeline_source_t *t = &p->sources[p->source_of[i]];
  zs_air_gate_result_t g = p->last_gate;
  if (i > 0u) { g.present = true; g.mains = false; }
  t->presence = zs_presence_evaluate(&t->votes, &g);
}

/* The window's source a listed source belongs to: itself, or the first listed source of the same target. */
static unsigned target_of(const zs_station_pipeline_t *p, unsigned i) {
  for (unsigned j = 0u; j < i; j++) if (p->same_target[p->source_of[i]][p->source_of[j]]) return target_of(p, j);
  return i;
}

/* Two sources whose bearings agree window after window are one target; disagreement undoes it. */
static void update_together(zs_station_pipeline_t *p, const zs_bearing_t *b, unsigned n) {
  for (unsigned i = 0u; i < n; i++)
    for (unsigned j = i + 1u; j < n; j++) {
      const unsigned a = p->source_of[i], c = p->source_of[j];
      if (!b[i].valid || !b[j].valid) continue;
      const float d = fabsf(fmodf(b[i].azimuth_deg - b[j].azimuth_deg + 540.0f, 360.0f) - 180.0f);
      const float tol = fmaxf(ZS_PIPELINE_TOGETHER_DEG, 2.0f * sqrtf(b[i].sigma_deg * b[i].sigma_deg + b[j].sigma_deg * b[j].sigma_deg));
      uint8_t k = p->together[a][c];
      k = d <= tol ? (uint8_t)(k < 2u * ZS_PIPELINE_TOGETHER_WINDOWS ? k + 1u : k) : (uint8_t)(k >= 2u ? k - 2u : 0u);
      p->together[a][c] = p->together[c][a] = k;
      if (k >= ZS_PIPELINE_TOGETHER_WINDOWS) p->same_target[a][c] = p->same_target[c][a] = true;
      else if (k == 0u) p->same_target[a][c] = p->same_target[c][a] = false;
    }
}

/* ---- targets by direction ----------------------------------------------------------------------------------- */
static void doa_clear(zs_station_pipeline_t *p) {
  zs_doa_sep_reset(&p->doa);
  memset(p->doa_targets, 0, sizeof(p->doa_targets));
  p->stash_target = 0u;
}

/* The directions a window can classify: present, confirmed, labelled, with a bearing at most
   ZS_PIPELINE_DOA_BEARING_AGE windows old (the mask aims at it). */
static unsigned doa_ready(const zs_station_pipeline_t *p, unsigned list[ZS_DOA_MAX_TRACKS]) {
  unsigned n = 0u;
  for (unsigned k = 0u; k < ZS_DOA_MAX_TRACKS; k++) {
    const zs_pipeline_target_t *t = &p->doa_targets[k];
    if (t->id && !t->absent && t->confirmed_direction && t->bearing.valid && t->bearing_age <= ZS_PIPELINE_DOA_BEARING_AGE &&
        t->bearing.f0_hz > 0.0f)
      list[n++] = k;
  }
  return n;
}

/* The window's direction tracks onto the targets: the same track keeps its votes (also after a few windows gone: the
   track comes back under its id); a new one starts with no votes (the main stream's votes are the mixture's, not this
   direction's). */
static void doa_update_targets(zs_station_pipeline_t *p, const zs_doa_target_t *out, unsigned n) {
  bool seen[ZS_DOA_MAX_TRACKS] = {false, false, false};
  for (unsigned i = 0u; i < n; i++) {
    int slot = -1;
    for (unsigned k = 0u; k < ZS_DOA_MAX_TRACKS && slot < 0; k++) if (p->doa_targets[k].id == out[i].id) slot = (int)k;
    if (slot < 0) {
      /* a free slot, else the target gone longest */
      for (unsigned k = 0u; k < ZS_DOA_MAX_TRACKS; k++) {
        const zs_pipeline_target_t *t = &p->doa_targets[k];
        if (seen[k]) continue;
        if (!t->id) { slot = (int)k; break; }
        if (t->absent && (slot < 0 || t->absent > p->doa_targets[slot].absent)) slot = (int)k;
      }
      if (slot < 0) continue;
      zs_pipeline_target_t *t = &p->doa_targets[slot];
      memset(t, 0, sizeof(*t));
      t->id = out[i].id;
      zs_classifier_consensus_init(&t->votes);
      t->classification.unknown = true;
    }
    zs_pipeline_target_t *t = &p->doa_targets[slot];
    seen[slot] = true;
    t->absent = 0u;
    t->confirmed_direction = out[i].confirmed;
    t->strength = out[i].strength;
    if (out[i].has_bearing) { t->bearing = out[i].bearing; t->bearing_age = 0u; }
    else { t->bearing.f0_hz = out[i].bearing.f0_hz; if (t->bearing_age < 255u) t->bearing_age++; }
  }
  for (unsigned k = 0u; k < ZS_DOA_MAX_TRACKS; k++) {
    zs_pipeline_target_t *t = &p->doa_targets[k];
    if (seen[k] || !t->id) continue;
    t->confirmed_direction = false;
    if (t->bearing_age < 255u) t->bearing_age++;
    if (++t->absent > ZS_DOA_RECALL_WINDOWS + ZS_DOA_MISS_MAX + 2u) memset(t, 0, sizeof(*t));
  }
}

/* level 1 of a direction target: its own votes alone (the gate's comb belongs to the station, not to this direction:
   a tractor heard beside a UAV would borrow it).  A UAV majority of at least ZS_CLASSIFICATION_MIN_WINDOWS of its own
   windows; or, as the station does with a comb, a majority of weak UAV votes, the direction's own comb being its label
   (a harmonic series of its own bins) and ground votes at most an eighth: the own window of a UAV (the other targets'
   lines removed) is a UAV, often less certainly than the whole sound. */
static void doa_evaluate(zs_station_pipeline_t *p, unsigned k) {
  zs_pipeline_target_t *t = &p->doa_targets[k];
  t->presence = zs_presence_evaluate(&t->votes, NULL);
  const unsigned n = t->presence.windows, majority = (n * 5u + 7u) / 8u;
  if (t->presence.level != ZS_PRESENCE_CONFIRMED && n >= ZS_CLASSIFICATION_MIN_WINDOWS && t->bearing.f0_hz > 0.0f &&
      t->presence.uav_weak_votes >= majority && 8u * t->presence.ground_votes <= n) {
    t->presence.level = ZS_PRESENCE_CONFIRMED;
    t->presence.confidence_u8 = ZS_PRESENCE_WEAK_CONFIDENCE_U8;
  }
}

/* the gate comb a label names: k x f0 (k 1..6) within ZS_PIPELINE_LABEL_RATIO; 0 when none or more than one */
static float gate_comb_of(const zs_air_gate_result_t *g, float label) {
  float combs[1u + ZS_AIR_MAX_SECONDARY], found = 0.0f;
  unsigned n = 0u, hits = 0u;
  if (!g->present || label <= 0.0f) return 0.0f;
  if (g->window_f0_hz > 0.0f) combs[n++] = g->window_f0_hz;
  for (unsigned s = 0u; s < g->secondary_count && s < ZS_AIR_MAX_SECONDARY; s++) if (g->secondary_f0_hz[s] > 0.0f) combs[n++] = g->secondary_f0_hz[s];
  for (unsigned i = 0u; i < n; i++) {
    const float k = roundf(label / combs[i]);
    if (k >= 1.0f && k <= 6.0f && fabsf(label - k * combs[i]) <= ZS_PIPELINE_LABEL_RATIO * label) { found = combs[i]; hits++; }
  }
  return hits == 1u ? found : 0.0f;
}

/* The bearings of the CONFIRMED direction targets (a window with at least two classifiable directions); the label goes
   out as the gate's fundamental when it names exactly one gate comb and no other delivered target names the same one.
   Returns how many of out[] were filled. */
static unsigned doa_deliveries(zs_station_pipeline_t *p, zs_bearing_t out[ZS_DOA_MAX_TRACKS]) {
  unsigned list[ZS_DOA_MAX_TRACKS], n = 0u;
  const unsigned nd = doa_ready(p, list);
  if (!p->stash || nd < 2u) return 0u;
  float comb[ZS_DOA_MAX_TRACKS];
  for (unsigned i = 0u; i < nd; i++) {
    const zs_pipeline_target_t *t = &p->doa_targets[list[i]];
    if (t->presence.level != ZS_PRESENCE_CONFIRMED || t->bearing_age != 0u) continue;    /* this window's own bearing */
    out[n] = t->bearing;
    comb[n] = gate_comb_of(&p->last_gate, t->bearing.f0_hz);
    n++;
  }
  for (unsigned i = 0u; i < n; i++) {
    bool shared = false;
    for (unsigned j = 0u; j < n; j++) if (j != i && comb[j] > 0.0f && comb[j] == comb[i]) shared = true;
    if (comb[i] > 0.0f && !shared) out[i].f0_hz = comb[i];
  }
  return n;
}

static void emit(zs_station_pipeline_t *p, uint64_t end_sample) {
  zs_detection_t d;
  p->seq_no++;
  zs_station_pipeline_fill_detection(p, end_sample, &d);
  if (p->port->emit(p->port->ctx, &d)) p->events_emitted++; else p->events_refused++;
  p->windows_since_event = 0u;
}

bool zs_station_pipeline_push_window(zs_station_pipeline_t *p, const int16_t *pcm, uint64_t end_sample) {
  if (!p || !pcm) return false;
  const uint8_t period = p->port->update_period_windows ? p->port->update_period_windows : ZS_PIPELINE_DEFAULT_UPDATE_WINDOWS;
  unsigned chosen = 0u;
  /* the gate first: it finds the strongest comb and the others (zs_air_gate.h); a window with one source reaches the
     classifier unchanged, a mixture's window carries one of its sources in turn with all the others suppressed */
  if (!zs_air_gate_push(&p->gate, pcm, ZS_PIPELINE_WINDOW_SAMPLES, p->scratch, &p->last_gate)) return false;
  p->source_count = 0u;
  if (p->last_gate.present && p->last_gate.window_f0_hz > 0.0f) {
    unsigned reported = 0u;
    p->source_f0[reported++] = p->last_gate.window_f0_hz;
    for (unsigned s = 0u; s < p->last_gate.secondary_count && reported < ZS_PIPELINE_SOURCES; s++)
      p->source_f0[reported++] = p->last_gate.secondary_f0_hz[s];
    p->source_count = (uint8_t)match_sources(p, reported);
    if (p->source_count < 2u) p->source_count = 0u;           /* one source: the window as it is, the main stream */
  }
  /* targets by direction (the last window's tracks): at least two classifiable ones replace the comb mixture; when the
     stash holds the last window's newest 0.5 s of one of them, this window completes and classifies its own 1 s */
  unsigned dl[ZS_DOA_MAX_TRACKS];
  const unsigned nd = doa_ready(p, dl);
  const bool by_direction = p->stash && p->ring && nd >= 2u;
  bool dir_window = false;
  unsigned dir_slot = 0u;
  if (by_direction && p->stash_target && p->stash_end + ZS_PIPELINE_HOP_SAMPLES == end_sample) {
    zs_bearing_t dirs[ZS_DOA_MAX_TRACKS];
    int which = -1;
    for (unsigned i = 0u; i < nd; i++) {
      dirs[i] = p->doa_targets[dl[i]].bearing;
      if (p->doa_targets[dl[i]].id == p->stash_target) which = (int)i;
    }
    if (which >= 0) {
      int16_t *buf = (int16_t *)p->window;
      if (zs_doa_sep_mask_window(&p->bearing_ctx, p->ring, end_sample, ZS_PIPELINE_HOP_SAMPLES, dirs, nd, (unsigned)which,
                                 temperature_of(p), (zs_doa_mask_workspace_t *)(void *)p->scratch, buf + ZS_PIPELINE_HOP_SAMPLES)) {
        memcpy(buf, p->stash, ZS_PIPELINE_HOP_SAMPLES * sizeof(int16_t));
        pcm = buf;
        dir_window = true;
        dir_slot = dl[which];
      } else p->doa_mask_failed++;
    }
  }
  p->stash_target = 0u;
  if (by_direction) p->doa_mixture_windows++;
  /* the targets of the mixture: sources heard from one direction are one target (its first listed source) */
  unsigned targets[ZS_PIPELINE_SOURCES], n_targets = 0u;
  for (unsigned i = 0u; i < p->source_count; i++) if (target_of(p, i) == i) targets[n_targets++] = i;
  const bool mixture = !by_direction && n_targets >= 2u;
  if (p->source_count && !mixture && !by_direction) p->merged_windows++;
  if (mixture) {
    float others[ZS_PIPELINE_SOURCES];
    unsigned n_others = 0u;
    chosen = targets[p->mixture_turn++ % n_targets];
    for (unsigned i = 0u; i < p->source_count; i++) if (target_of(p, i) != chosen) others[n_others++] = p->source_f0[i];
    if (pcm != p->window) memcpy(p->window, pcm, ZS_PIPELINE_WINDOW_SAMPLES * sizeof(int16_t));
    zs_air_gate_suppress_combs(p->window, ZS_PIPELINE_WINDOW_SAMPLES, others, n_others);
    pcm = p->window;
    p->separated_windows++;
  }
  if (!p->port->extract(p->port->ctx, pcm, ZS_PIPELINE_WINDOW_SAMPLES, p->features)) return false;
  p->last_window = zs_classifier_predict_centroid(p->features);
  if (dir_window) {
    zs_pipeline_target_t *t = &p->doa_targets[dir_slot];
    (void)zs_classifier_consensus_push(&t->votes, p->last_window, &t->classification, &t->hierarchy);
    p->doa_classified_windows++;
  } else if (mixture) {
    zs_pipeline_source_t *t = &p->sources[p->source_of[chosen]];
    (void)zs_classifier_consensus_push(&t->votes, p->last_window, &t->classification, &t->hierarchy);
    if (chosen == 0u) (void)zs_classifier_consensus_push(&p->votes, p->last_window, &p->classification, &p->hierarchy);
    for (unsigned t = 0u; t < n_targets; t++) evaluate_source(p, targets[t]);
  } else {
    (void)zs_classifier_consensus_push(&p->votes, p->last_window, &p->classification, &p->hierarchy);
  }
  p->presence = zs_presence_evaluate(&p->votes, &p->last_gate);
  if (by_direction) for (unsigned i = 0u; i < nd; i++) doa_evaluate(p, dl[i]);
  /* a mixture: the station is CONFIRMED when any of its sources is; the event names the confirming source */
  if (p->presence.level != ZS_PRESENCE_CONFIRMED && mixture) {
    for (unsigned k = 0u; k < n_targets; k++) {
      const zs_pipeline_source_t *t = &p->sources[p->source_of[targets[k]]];
      if (t->presence.level != ZS_PRESENCE_CONFIRMED) continue;
      p->presence = t->presence;
      p->classification = t->classification;
      p->hierarchy = t->hierarchy;
      p->source_confirmed_windows++;
      break;
    }
  }
  if (p->presence.level != ZS_PRESENCE_CONFIRMED && by_direction) {
    for (unsigned i = 0u; i < nd; i++) {
      const zs_pipeline_target_t *t = &p->doa_targets[dl[i]];
      if (t->presence.level != ZS_PRESENCE_CONFIRMED) continue;
      p->presence = t->presence;
      p->classification = t->classification;
      p->hierarchy = t->hierarchy;
      p->doa_confirmed_windows++;
      break;
    }
  }
  p->windows++;
  switch (p->presence.level) {
    case ZS_PRESENCE_CONFIRMED: p->confirmed_windows++; break;
    case ZS_PRESENCE_SUSPECT: p->suspect_windows++; break;
    case ZS_PRESENCE_ENGINE_UNCONFIRMED: p->engine_windows++; break;
    default: break;
  }
  /* the window's newest 0.5 s decimated once (into the window buffer, done with by now): the comb bearings of a gate
     mixture every window (whether its sources are one target is told by the directions), and the direction tracks
     from the first sign of a target on (the gate's comb, any level above none, or tracks still alive), so they are
     confirmed by the time the station is */
  bool live = false;
  for (unsigned k = 0u; k < ZS_DOA_MAX_TRACKS; k++) live = live || (p->doa_targets[k].id != 0u && !p->doa_targets[k].absent);
  const bool doa_run = p->stash && p->ring && (p->last_gate.present || p->presence.level != ZS_PRESENCE_NONE || live);
  const bool comb_run = p->source_count >= 2u && !by_direction;
  bool memory_ok = false;
  if (p->ring && (doa_run || comb_run))
    memory_ok = zs_comb_bearing_decimate_ring(p->ring, end_sample, (float *)(void *)p->window);
  zs_bearing_t bearings[ZS_COMB_BEARING_MAX_SOURCES];
  unsigned nb = 0u;
  if (comb_run) {
    nb = comb_bearings(p, memory_ok, bearings);
    update_together(p, bearings, nb);
  }
  if (doa_run && memory_ok) {
    zs_doa_target_t out[ZS_DOA_MAX_TRACKS];
    const unsigned n = zs_doa_sep_push(&p->doa, &p->bearing_ctx, (const float *)(const void *)p->window, temperature_of(p),
                                       (zs_doa_workspace_t *)(void *)p->scratch, out);
    doa_update_targets(p, out, n);
    p->doa_windows++;
  } else if (!doa_run) {
    doa_clear(p);
  }
  /* a window classified as it is takes the next direction's newest 0.5 s into the stash (one mask per window) */
  if (p->stash && p->ring && !dir_window) {
    unsigned list[ZS_DOA_MAX_TRACKS];
    const unsigned n = doa_ready(p, list);
    if (n >= 2u) {
      zs_bearing_t dirs[ZS_DOA_MAX_TRACKS];
      for (unsigned i = 0u; i < n; i++) dirs[i] = p->doa_targets[list[i]].bearing;
      const unsigned which = p->doa_turn++ % n;
      if (zs_doa_sep_mask_window(&p->bearing_ctx, p->ring, end_sample, ZS_PIPELINE_HOP_SAMPLES, dirs, n, which, temperature_of(p),
                                 (zs_doa_mask_workspace_t *)(void *)p->scratch, p->stash)) {
        p->stash_target = p->doa_targets[list[which]].id;
        p->stash_end = end_sample;
      } else p->doa_mask_failed++;
    }
  }
  if (p->presence.level == ZS_PRESENCE_CONFIRMED) {
    zs_bearing_t send[ZS_COMB_BEARING_MAX_SOURCES > ZS_DOA_MAX_TRACKS ? ZS_COMB_BEARING_MAX_SOURCES : ZS_DOA_MAX_TRACKS];
    unsigned ns = doa_deliveries(p, send);
    p->doa_bearings += ns;
    /* several directions heard (confirmed, labelled or not yet): only their own bearings; the full band mixes them, and
       the gate's main comb may be the one that is no UAV (a tractor's beside a UAV the main stream confirms) */
    unsigned several = 0u;
    for (unsigned k = 0u; k < ZS_DOA_MAX_TRACKS; k++)
      several += p->doa_targets[k].id && !p->doa_targets[k].absent && p->doa_targets[k].confirmed_direction;
    if (ns == 0u && !by_direction && several < 2u) {
      if (p->source_count < 2u) {
        single_bearing(p, end_sample, &bearings[0]);
        if (bearings[0].valid) send[ns++] = bearings[0];
      } else {
        /* a mixture: the bearings of the CONFIRMED targets (the main one also when the main stream confirms it); the
           other combs of a target are not reported */
        const bool main_stream = zs_presence_evaluate(&p->votes, &p->last_gate).level == ZS_PRESENCE_CONFIRMED;
        for (unsigned i = 0u; i < nb; i++) {
          const bool wanted = target_of(p, i) == i &&
                              ((mixture && p->sources[p->source_of[i]].presence.level == ZS_PRESENCE_CONFIRMED) || (i == 0u && main_stream));
          if (bearings[i].valid && wanted) send[ns++] = bearings[i];
        }
      }
    }
    if (ns) { p->last_bearing = send[0]; p->last_bearing_end = end_sample; }     /* the event carries the first one */
    else p->last_bearing.valid = false;
    if (!p->confirmed) {                                                            /* rising edge */
      p->confirmed = true;
      emit(p, end_sample);
      p->track_event_id = ((uint64_t)p->port->boot_id << 32) | p->seq_no;
    } else if (++p->windows_since_event >= period) emit(p, end_sample);            /* keep-alive update */
    for (unsigned i = 0u; i < ns && p->port->bearing; i++) p->port->bearing(p->port->ctx, &send[i], end_sample, p->track_event_id);
  } else {
    p->confirmed = false;
    p->windows_since_event = 0u;
  }
  return true;
}

bool zs_station_pipeline_fetch(zs_station_pipeline_t *p, const zs_audio_ring_t *ring) {
  if (!p || !ring || p->pending) return false;
  /* windows whose start the ring has already overwritten are lost: skip to the oldest one still complete */
  if (ring->total_frames > ring->frames_capacity) {
    const uint64_t oldest_end = ring->total_frames - ring->frames_capacity + ZS_PIPELINE_WINDOW_SAMPLES;
    while (p->next_window_end < oldest_end) { p->next_window_end += ZS_PIPELINE_HOP_SAMPLES; p->windows_dropped++; }
  }
  if (p->next_window_end > ring->total_frames) return false;
  if (!zs_audio_ring_copy_mono(ring, p->next_window_end, ZS_PIPELINE_WINDOW_SAMPLES, p->window, p->port->channel)) return false;
  p->ring = ring;
  p->pending_end = p->next_window_end;
  p->pending = true;
  p->next_window_end += ZS_PIPELINE_HOP_SAMPLES;
  return true;
}

bool zs_station_pipeline_run_pending(zs_station_pipeline_t *p) {
  bool ok;
  if (!p || !p->pending) return false;
  ok = zs_station_pipeline_push_window(p, p->window, p->pending_end);
  p->pending = false;
  return ok;
}

unsigned zs_station_pipeline_poll(zs_station_pipeline_t *p, const zs_audio_ring_t *ring) {
  unsigned done = 0u;
  while (zs_station_pipeline_fetch(p, ring)) { if (!zs_station_pipeline_run_pending(p)) break; done++; }
  return done;
}
