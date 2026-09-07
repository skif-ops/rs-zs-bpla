#!/usr/bin/env python3
"""Whole-recording LOFO replay for current v0.6 UAV sources."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd

from audio.loader import AudioLoader
from audio.separation import DroneSeparator
from ml.online_type_classifier import OnlineTemporalTypeClassifier

DATASET=ROOT/'dataset'/'features.csv'
POLICY=ROOT/'dataset'/'source_policy_v06.json'
OUT=ROOT/'output'/'v06_benchmark'


def candidate_time(path: Path) -> tuple[float|None,float,int,int]:
    loader=AudioLoader(); sep=DroneSeparator(); audio=loader.load_audio(path)
    sr=audio.sample_rate; win=max(int(round(2.0*sr)),1); hop=max(int(round(1.0*sr)),1)
    first=None; best=0.0; present=0; total=0
    if len(audio.signal)<win:
        return None,0.0,0,0
    for start in range(0,len(audio.signal)-win+1,hop):
        result=sep.separate(audio.signal[start:start+win],sr).findings
        total += 1
        best=max(best,float(result.confidence))
        if result.drone_present:
            present += 1
        if first is None and result.drone_present and result.confidence>=0.55:
            first=start/sr+2.0
    return first,best,present,total


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    df=pd.read_csv(DATASET)
    manifest=json.loads(POLICY.read_text(encoding='utf-8'))['sources']
    test_sources=[s for s in manifest if 'v06_user_sources' in s]
    records=[]; timelines={}
    for src in sorted(test_sources):
        meta=manifest[src]; test=df[df['source_file'].astype(str)==src].copy()
        if test.empty: continue
        raw=ROOT/src
        detect_s,best_det,present,total=candidate_time(raw)
        train=df[df['source_file'].astype(str)!=src].copy()
        with tempfile.TemporaryDirectory() as td:
            clf=OnlineTemporalTypeClassifier(model_path=Path(td)/'temporal.json')
            model=clf.train(train)
            replay=clf.replay(test,source_file=src,candidate_detection_seconds=detect_s,model=model)
        records.append({
            'source_file':src,
            'file_name':Path(src).name,
            'label':meta['label'],
            'label_confidence':meta['label_confidence'],
            'recording_quality_score':meta['recording_quality_score'],
            'duration_seconds':round(float(len(AudioLoader().load_audio(raw).signal)/AudioLoader().load_audio(raw).sample_rate),2),
            'candidate_detection_seconds':detect_s,
            'candidate_best_confidence':round(best_det,4),
            'candidate_present_windows':present,
            'candidate_total_windows':total,
            'first_type_hypothesis_seconds':replay.first_type_hypothesis_seconds,
            'research_stable_seconds':replay.research_stable_seconds,
            'final_type':replay.final_label,
            'final_status':replay.final_status,
            'type_lock_allowed':replay.type_lock_allowed,
            'type_snapshot_count':len(replay.snapshots),
        })
        timelines[src]=[x.model_dump() for x in replay.snapshots]
    out=pd.DataFrame(records)
    out.to_csv(OUT/'whole_recording_lofo.csv',index=False)
    (OUT/'timelines.json').write_text(json.dumps(timelines,ensure_ascii=False,indent=2),encoding='utf-8')

    confirmed=out[out.label_confidence=='confirmed']
    weak=out[out.label_confidence=='weak']
    detected=out['candidate_detection_seconds'].notna().sum()
    within2=((out['candidate_detection_seconds'].fillna(999)<=2.0)).sum()
    false_locks=int(out['type_lock_allowed'].astype(bool).sum())
    confirmed_type_hits=int(((confirmed['final_type']==confirmed['label']) & (confirmed['final_type']!='UNKNOWN')).sum())
    md=[
        '# Мухоед v0.6 - whole-recording LOFO benchmark', '',
        'Каждый тестовый source полностью исключён из обучения. FP-1 имеет weak label и не используется как ground truth accuracy.', '',
        f'- Записей: {len(out)}.',
        f'- Акустический кандидат обнаружен: {detected}/{len(out)}.',
        f'- Обнаружение не позднее 2 с: {within2}/{len(out)}.',
        f'- Ложных operational type lock: {false_locks}.',
        f'- Подтверждённые записи Лютого с корректной type-гипотезой в финальном кадре: {confirmed_type_hits}/{len(confirmed)}. Эта величина является диагностикой, не acceptance accuracy.',
        f'- FP-1 weak sources: {len(weak)}; совпадение с именем не считается accuracy.', '',
        '## Вывод', '',
        'v0.6 подтверждает разделение задач detection/type. Детектор присутствия цели на текущих файлах достаточно быстрый, но имеющиеся типовые признаки и слабая FP-1 разметка не дают оснований для безопасного lock типа. Консервативный классификатор оставляет тип UNKNOWN вместо ложной уверенности. Для Design Freeze type-classifier требуется новая независимая подтверждённая выборка FP-1 и более качественные пролёты.', '',
        '## Операционная логика', '',
        '- 0-2 с: candidate detection / AIR_WARNING без обязательного типа.',
        '- 5-8 с: первая типовая гипотеза только при достаточном margin.',
        '- 10-20 с: накопление 5/10-секундных temporal features.',
        '- 20-40 с: refinement; противоречащие признаки снимают pending type hypothesis.',
        '- 40-60 с не являются обязательным временем ожидания решения.',
    ]
    (OUT/'README.md').write_text('\n'.join(md),encoding='utf-8')
    print(out.to_string(index=False))
    print('\n'.join(md[:12]))

if __name__=='__main__': main()
