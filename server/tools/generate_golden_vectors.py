#!/usr/bin/env python3
"""Generate 32 kHz / 1 s golden PCM windows and exact 43 server features."""
from __future__ import annotations
import argparse, csv, json
from pathlib import Path
import numpy as np
import librosa
from audio.loader import AudioLoader
from audio.preprocessing import AudioPreprocessor
from audio.features import FeatureExtractor
from ml.feature_vector import FEATURE_COLUMNS, feature_set_to_vector

TARGET_SR=32000
WINDOW=TARGET_SR

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--src',type=Path,required=True); ap.add_argument('--out',type=Path,required=True); ap.add_argument('--count',type=int,default=100); args=ap.parse_args()
    files=sorted([p for p in args.src.iterdir() if p.suffix.lower() in {'.wav','.flac','.mp3','.m4a','.aac'}])
    if not files: raise SystemExit('no audio files')
    out=args.out; pcm_dir=out/'pcm16le'; pcm_dir.mkdir(parents=True,exist_ok=True)
    loader=AudioLoader(); prep=AudioPreprocessor(); ext=FeatureExtractor()
    candidates=[]
    loaded=[]
    for p in files:
        a=loader.load_audio(p); y=a.signal
        if a.sample_rate!=TARGET_SR:
            y=librosa.resample(y=y.astype(np.float32),orig_sr=a.sample_rate,target_sr=TARGET_SR)
            y,_=prep.prepare(y,TARGET_SR)
        loaded.append((p,y))
        # candidate starts on the same 0.5 s grid as production classifier
        starts=list(range(0,max(0,len(y)-WINDOW+1),TARGET_SR//2))
        for st in starts: candidates.append((p,y,st))
    if not candidates: raise SystemExit('no 1s windows')
    # Deterministic coverage: round-robin across files, then evenly spaced windows.
    chosen=[]
    per_file=max(1,args.count//len(loaded))
    for p,y in loaded:
        starts=list(range(0,max(0,len(y)-WINDOW+1),TARGET_SR//2))
        if not starts: continue
        idx=np.linspace(0,len(starts)-1,min(per_file,len(starts)),dtype=int)
        chosen.extend((p,y,starts[i]) for i in idx)
    if len(chosen)<args.count:
        seen={(str(p),st) for p,_,st in chosen}
        for item in candidates:
            key=(str(item[0]),item[2])
            if key not in seen: chosen.append(item);seen.add(key)
            if len(chosen)>=args.count:break
    chosen=chosen[:args.count]
    rows=[]
    for i,(p,y,st) in enumerate(chosen):
        seg=np.asarray(y[st:st+WINDOW],dtype=np.float32)
        # production station transmits int16 PCM to golden test, then feature extractor sees normalized float
        pcm=np.clip(np.round(seg*32767.0),-32768,32767).astype('<i2')
        pcm_path=pcm_dir/f'vec_{i:03d}.bin'; pcm.tofile(pcm_path)
        roundtrip=pcm.astype(np.float32)/32768.0
        roundtrip,_=prep.prepare(roundtrip,TARGET_SR)
        feat=ext.extract(roundtrip,TARGET_SR).features
        v=feature_set_to_vector(feat)
        rows.append([f'vec_{i:03d}',p.name,st/TARGET_SR,pcm_path.name,*map(float,v)])
        if (i+1)%10==0: print(f'{i+1}/{len(chosen)}')
    with open(out/'vectors.csv','w',newline='',encoding='utf-8') as f:
        w=csv.writer(f);w.writerow(['vector_id','source','start_s','pcm_file',*FEATURE_COLUMNS]);w.writerows(rows)
    (out/'feature_order.txt').write_text('\n'.join(FEATURE_COLUMNS)+'\n',encoding='utf-8')
    (out/'manifest.json').write_text(json.dumps({'sample_rate_hz':TARGET_SR,'window_samples':WINDOW,'count':len(rows),'feature_count':len(FEATURE_COLUMNS),'pcm_format':'signed int16 little-endian mono','preprocess':'PCM -> float /32768 -> DC removal -> peak normalize -> FeatureExtractor'},ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'README.md').write_text(f'''# Golden vectors\n\nGenerated from the non-empty original audio files recovered from the supplied June 2026 archive.\n\n- Count: {len(rows)} windows\n- Input: mono PCM16LE, 32000 Hz, exactly 1.0 s\n- Feature vector: 43 values in `feature_order.txt`\n- Server reference: current `audio.features.FeatureExtractor`\n- MCU acceptance: median normalized error <=3%, p95 <=5%, with separate absolute tolerances for F0/harmonic features.\n\nThe windows are a regression fixture, not a statistically representative training dataset.\n''',encoding='utf-8')

if __name__=='__main__':main()
