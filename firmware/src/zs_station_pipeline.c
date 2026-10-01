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

/* Bearings of a CONFIRMED window from the 4-channel ring; the window and the gate scratch are idle by now.  One source:
   the full-band bearing.  A mixture: one bearing per source from the bins of its own harmonics (all sources take
   part, each excludes the others' bins), the main one first; `wanted` marks the sources whose bearing is delivered.
   Returns how many of out[] were filled (valid or not). */
static unsigned update_bearings(zs_station_pipeline_t *p, uint64_t end_sample, zs_bearing_t out[ZS_COMB_BEARING_MAX_SOURCES]) {
  const float t = p->port->temperature_c ? p->port->temperature_c(p->port->ctx) : 15.0f;
  unsigned n = 1u;
  p->last_bearing.valid = false;
  if (!p->ring) return 0u;
  if (p->source_count >= 2u) {
    n = p->source_count;
    (void)zs_comb_bearings_from_ring(&p->bearing_ctx, &p->comb_stats, p->ring, end_sample, p->source_f0, n, t, (float *)(void *)p->window,
                                     (zs_comb_bearing_workspace_t *)(void *)p->scratch, out);
    p->comb_windows++;
  } else {
    (void)zs_bearing_from_ring(&p->bearing_ctx, p->ring, end_sample, ZS_PIPELINE_BEARING_SPAN, t, p->window,
                               (zs_spatial_gcc_workspace_t *)(void *)p->scratch, &out[0]);
    if (p->last_gate.present) out[0].f0_hz = p->last_gate.window_f0_hz;      /* the source it follows, for the server */
  }
  return n;
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
  /* the targets of the mixture: sources heard from one direction are one target (its first listed source) */
  unsigned targets[ZS_PIPELINE_SOURCES], n_targets = 0u;
  for (unsigned i = 0u; i < p->source_count; i++) if (target_of(p, i) == i) targets[n_targets++] = i;
  const bool mixture = n_targets >= 2u;
  if (p->source_count && !mixture) p->merged_windows++;
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
  if (mixture) {
    zs_pipeline_source_t *t = &p->sources[p->source_of[chosen]];
    (void)zs_classifier_consensus_push(&t->votes, p->last_window, &t->classification, &t->hierarchy);
    if (chosen == 0u) (void)zs_classifier_consensus_push(&p->votes, p->last_window, &p->classification, &p->hierarchy);
    for (unsigned t = 0u; t < n_targets; t++) evaluate_source(p, targets[t]);
  } else {
    (void)zs_classifier_consensus_push(&p->votes, p->last_window, &p->classification, &p->hierarchy);
  }
  p->presence = zs_presence_evaluate(&p->votes, &p->last_gate);
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
  p->windows++;
  switch (p->presence.level) {
    case ZS_PRESENCE_CONFIRMED: p->confirmed_windows++; break;
    case ZS_PRESENCE_SUSPECT: p->suspect_windows++; break;
    case ZS_PRESENCE_ENGINE_UNCONFIRMED: p->engine_windows++; break;
    default: break;
  }
  /* several sources: their bearings every window (whether they are one target is told by the directions) */
  zs_bearing_t bearings[ZS_COMB_BEARING_MAX_SOURCES];
  unsigned nb = 0u;
  if (p->source_count >= 2u) {
    nb = update_bearings(p, end_sample, bearings);
    update_together(p, bearings, nb);
  }
  if (p->presence.level == ZS_PRESENCE_CONFIRMED) {
    bool wanted[ZS_COMB_BEARING_MAX_SOURCES] = {true, true, true};
    if (p->source_count < 2u) nb = update_bearings(p, end_sample, bearings);
    else {
      /* a mixture: the bearings of the CONFIRMED targets (the main one also when the main stream confirms it); the
         other combs of a target are not reported */
      const bool main_stream = zs_presence_evaluate(&p->votes, &p->last_gate).level == ZS_PRESENCE_CONFIRMED;
      for (unsigned i = 0u; i < nb; i++)
        wanted[i] = target_of(p, i) == i &&
                    ((mixture && p->sources[p->source_of[i]].presence.level == ZS_PRESENCE_CONFIRMED) || (i == 0u && main_stream));
    }
    for (unsigned i = 0u; i < nb; i++)                         /* the event carries the first delivered bearing */
      if (bearings[i].valid && wanted[i]) { p->last_bearing = bearings[i]; p->last_bearing_end = end_sample; break; }
    if (!p->confirmed) {                                                            /* rising edge */
      p->confirmed = true;
      emit(p, end_sample);
      p->track_event_id = ((uint64_t)p->port->boot_id << 32) | p->seq_no;
    } else if (++p->windows_since_event >= period) emit(p, end_sample);            /* keep-alive update */
    for (unsigned i = 0u; i < nb && p->port->bearing; i++)
      if (bearings[i].valid && wanted[i]) p->port->bearing(p->port->ctx, &bearings[i], end_sample, p->track_event_id);
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
