#!/usr/bin/env python3
"""Merge current user UAV recordings into the v0.6 training dataset safely."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
EXTERNAL = Path('/mnt/data/new_uav_runs_v052')
FEATURES = ROOT / 'dataset' / 'features.csv'
MANIFEST = ROOT / 'dataset' / 'source_policy_v06.json'

NEW_SOURCES = {
    'Лютый 3.wav': ('Лютый', 'training_provisional', 'confirmed', 1.0),
    'Лютый 4.wav': ('Лютый', 'training_provisional', 'confirmed', 1.0),
    'Лютый 5.wav': ('Лютый', 'training_provisional', 'confirmed', 1.0),
    'FP-1.wav': ('FP-1', 'training_provisional_weak', 'weak', 0.40),
    'FP-1 (2).wav': ('FP-1', 'training_provisional_weak', 'weak', 0.40),
    'FP-1 3.wav': ('FP-1', 'training_provisional_weak', 'weak', 0.40),
}


def usability_score(path: Path, row_count: int) -> tuple[float, str]:
    """Heuristic training usability, intentionally independent from label trust."""
    data, sr = sf.read(path, always_2d=True, dtype='float32')
    mono = np.mean(data, axis=1)
    duration = len(mono) / float(sr)
    peak = float(np.max(np.abs(mono))) if mono.size else 0.0
    clipping = float(np.mean(np.abs(mono) >= 0.985)) if mono.size else 1.0
    non_silent = float(np.mean(np.abs(mono) >= max(peak * 0.02, 1e-5))) if mono.size else 0.0
    duration_score = float(np.clip(duration / 20.0, 0.20, 1.0))
    sample_rate_score = 1.0 if sr >= 32000 else (0.8 if sr >= 20000 else 0.5)
    clipping_score = float(np.clip(1.0 - clipping * 25.0, 0.2, 1.0))
    activity_score = float(np.clip(non_silent / 0.60, 0.25, 1.0))
    # Files originate from phone/video material, so cap the heuristic rather than
    # pretending PCM extraction restored the original microphone quality.
    score = 0.30 * duration_score + 0.25 * sample_rate_score + 0.25 * clipping_score + 0.20 * activity_score
    score = min(score, 0.78)
    if score >= 0.70:
        category = 'medium'
    elif score >= 0.50:
        category = 'low'
    else:
        category = 'low'
    return round(float(score), 3), category


def main() -> None:
    df = pd.read_csv(FEATURES)
    new = pd.read_csv(EXTERNAL / 'new_features.csv')
    manifest: dict[str, dict[str, object]] = {'version': 1, 'policy': 'v0.6', 'sources': {}}

    # Existing FP-1 source is no longer treated as a confirmed validation label.
    fp_mask = df['label'].astype(str).eq('FP-1')
    df.loc[fp_mask, 'meta_dataset_role'] = 'training_provisional_weak'
    df.loc[fp_mask, 'meta_label_confidence'] = 'weak'
    df.loc[fp_mask, 'meta_label_confidence_score'] = 0.40
    if 'meta_recording_quality_score' not in df.columns:
        df['meta_recording_quality_score'] = np.nan
    if 'meta_recording_quality' not in df.columns:
        df['meta_recording_quality'] = 'unknown'
    if 'meta_label_confidence' not in df.columns:
        df['meta_label_confidence'] = 'confirmed'
    if 'meta_label_confidence_score' not in df.columns:
        df['meta_label_confidence_score'] = np.nan

    # Existing confirmed Lutyi rows remain provisional training, never validation.
    lt_mask = df['label'].astype(str).eq('Лютый')
    df.loc[lt_mask, 'meta_dataset_role'] = 'training_provisional'
    df.loc[lt_mask, 'meta_label_confidence'] = 'confirmed'
    df.loc[lt_mask, 'meta_label_confidence_score'] = 1.0

    # Avoid duplicate import when the tool is rerun.
    external_names = set(NEW_SOURCES)
    df = df[~df['source_file'].astype(str).isin(external_names)].copy()

    additions=[]
    for filename, (label, role, label_conf, label_score) in NEW_SOURCES.items():
        src = EXTERNAL / filename
        if not src.exists():
            continue
        target_dir = ROOT / 'dataset' / 'raw' / label / 'v06_user_sources' / src.stem
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / src.name
        shutil.copy2(src, target)
        rel = str(target.relative_to(ROOT))
        rows = new[(new['label'].astype(str)==label) & (new['source_file'].astype(str)==filename)].copy()
        if rows.empty:
            continue
        quality_score, quality = usability_score(target, len(rows))
        rows['source_file'] = rel
        rows['original_name'] = filename
        rows['meta_category'] = 'drone'
        rows['meta_is_drone'] = True
        rows['meta_dataset_role'] = role
        rows['meta_recording_quality'] = quality
        rows['meta_recording_quality_score'] = quality_score
        rows['meta_label_confidence'] = label_conf
        rows['meta_label_confidence_score'] = label_score
        rows['meta_notes'] = ('Тип подтверждён пользователем; запись не является эталонной.' if label=='Лютый'
                              else 'Название FP-1 рассматривается как слабая/неподтверждённая метка.')
        additions.append(rows)
        manifest['sources'][rel] = {
            'label': label,
            'dataset_role': role,
            'recording_quality': quality,
            'recording_quality_score': quality_score,
            'label_confidence': label_conf,
            'label_confidence_score': label_score,
            'source_origin': 'user_video_audio',
            'validation_eligible': False,
        }

    if additions:
        df = pd.concat([df, *additions], ignore_index=True, sort=False)
    # Apply a conservative default quality to pre-v0.6 target sources when absent.
    target_mask = df['label'].astype(str).isin(['Лютый','FP-1'])
    df.loc[target_mask & pd.to_numeric(df['meta_recording_quality_score'], errors='coerce').isna(), 'meta_recording_quality_score'] = 0.65
    df.loc[target_mask & df['meta_recording_quality'].isna(), 'meta_recording_quality'] = 'low'
    df.to_csv(FEATURES, index=False)

    for (label, source), group in df[target_mask].groupby(['label','source_file']):
        if str(source) not in manifest['sources']:
            role = str(group['meta_dataset_role'].dropna().iloc[0]) if 'meta_dataset_role' in group and not group['meta_dataset_role'].dropna().empty else 'training'
            manifest['sources'][str(source)] = {
                'label': str(label),
                'dataset_role': role,
                'recording_quality': str(group['meta_recording_quality'].dropna().iloc[0]) if 'meta_recording_quality' in group and not group['meta_recording_quality'].dropna().empty else 'unknown',
                'recording_quality_score': float(pd.to_numeric(group['meta_recording_quality_score'], errors='coerce').dropna().iloc[0]) if not pd.to_numeric(group['meta_recording_quality_score'], errors='coerce').dropna().empty else 0.65,
                'label_confidence': str(group['meta_label_confidence'].dropna().iloc[0]) if 'meta_label_confidence' in group and not group['meta_label_confidence'].dropna().empty else ('weak' if label=='FP-1' else 'confirmed'),
                'label_confidence_score': float(pd.to_numeric(group['meta_label_confidence_score'], errors='coerce').dropna().iloc[0]) if not pd.to_numeric(group['meta_label_confidence_score'], errors='coerce').dropna().empty else (0.4 if label=='FP-1' else 1.0),
                'source_origin': 'pre_v06_dataset',
                'validation_eligible': False,
            }
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    print(df.groupby(['label','meta_dataset_role']).agg(windows=('label','size'),sources=('source_file','nunique')).reset_index().to_string(index=False))
    print(f'Wrote {FEATURES}')
    print(f'Wrote {MANIFEST}')

if __name__ == '__main__':
    main()
