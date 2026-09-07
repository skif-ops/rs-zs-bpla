"""Live 43-feature accumulation and online type updates for station events."""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Deque

import pandas as pd

from ml.feature_vector import FEATURE_COLUMNS
from ml.online_type_classifier import OnlineTemporalTypeClassifier
from station.schemas import FeatureUpdateMessage, OnlineTypeStatusMessage


@dataclass(slots=True)
class _Session:
    first_time_us: int
    rows: Deque[dict[str, object]]


class OnlineTypeSessionService:
    """Maintain bounded per-event feature history and update type hypotheses."""

    def __init__(self, classifier: OnlineTemporalTypeClassifier | None = None, max_history_seconds: float = 75.0):
        self.classifier = classifier or OnlineTemporalTypeClassifier()
        self.max_history_seconds = float(max_history_seconds)
        self.sessions: dict[tuple[int, int], _Session] = {}

    def ingest(self, msg: FeatureUpdateMessage) -> OnlineTypeStatusMessage:
        key=(int(msg.station_id),int(msg.event_id))
        session=self.sessions.get(key)
        if session is None:
            session=_Session(first_time_us=int(msg.event_time_us),rows=deque())
            self.sessions[key]=session
        elapsed=max((int(msg.event_time_us)-session.first_time_us)/1e6,0.0)
        row:dict[str,object]={
            'label':'UNKNOWN',
            'source_file':f'live:{msg.station_id}:{msg.event_id}',
            'start_seconds':elapsed,
            'duration_seconds':1.0,
        }
        row.update({name:float(value) for name,value in zip(FEATURE_COLUMNS,msg.features)})
        session.rows.append(row)
        cutoff=max(elapsed-self.max_history_seconds,0.0)
        while session.rows and float(session.rows[0]['start_seconds']) < cutoff:
            session.rows.popleft()

        model=self.classifier.load()
        if model is None or elapsed < 5.0:
            return OnlineTypeStatusMessage(
                station_id=msg.station_id,event_id=msg.event_id,elapsed_seconds=round(elapsed,3),
                status='warming_up',model_version=(str(model.get('version')) if model else 'missing'),
            )
        frame=pd.DataFrame(list(session.rows))
        replay=self.classifier.replay(
            frame,source_file=str(row['source_file']),candidate_detection_seconds=0.0,model=model
        )
        snapshot=replay.snapshots[-1] if replay.snapshots else None
        if snapshot is None:
            return OnlineTypeStatusMessage(
                station_id=msg.station_id,event_id=msg.event_id,elapsed_seconds=round(elapsed,3),
                status='unknown',model_version=str(model.get('version','unknown')),
            )
        return OnlineTypeStatusMessage(
            station_id=msg.station_id,event_id=msg.event_id,elapsed_seconds=round(elapsed,3),
            best_label=snapshot.best_label,confidence=snapshot.confidence,margin=snapshot.margin,
            status=snapshot.status,type_lock_allowed=snapshot.type_lock_allowed,
            first_type_hypothesis_seconds=replay.first_type_hypothesis_seconds,
            research_stable_seconds=replay.research_stable_seconds,
            model_version=str(model.get('version','unknown')),
        )

    def close(self, station_id: int, event_id: int) -> None:
        self.sessions.pop((int(station_id),int(event_id)),None)
