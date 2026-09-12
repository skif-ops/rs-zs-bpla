"""Live 43-feature accumulation and online type updates for station events."""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Deque

import pandas as pd

from config import settings
from ml.acoustic_family import hierarchical_label
from ml.family_classifier import AcousticFamilyClassifier
from ml.feature_vector import FEATURE_COLUMNS
from ml.online_type_classifier import OnlineTemporalTypeClassifier
from models.schemas import FamilyClassificationResult
from station.schemas import FeatureUpdateMessage, OnlineTypeStatusMessage


@dataclass(slots=True)
class _Session:
    first_time_us: int
    rows: Deque[dict[str, object]]
    seen_updates: set[tuple[int, int]]


class OnlineTypeSessionService:
    """Maintain bounded per-event feature history and update type hypotheses."""

    def __init__(
        self,
        classifier: OnlineTemporalTypeClassifier | None = None,
        family_classifier: AcousticFamilyClassifier | None = None,
        max_history_seconds: float = 75.0,
    ):
        self.classifier = classifier or OnlineTemporalTypeClassifier()
        self.family_classifier = family_classifier or AcousticFamilyClassifier()
        self.max_history_seconds = float(max_history_seconds)
        self.sessions: dict[tuple[int, int], _Session] = {}

    def ingest(self, msg: FeatureUpdateMessage) -> OnlineTypeStatusMessage:
        key=(int(msg.station_id),int(msg.event_id))
        session=self.sessions.get(key)
        if session is None:
            session=_Session(first_time_us=int(msg.event_time_us),rows=deque(),seen_updates=set())
            self.sessions[key]=session
        elapsed=max((int(msg.event_time_us)-session.first_time_us)/1e6,0.0)
        update_id=(int(msg.boot_id),int(msg.seq_no))
        row:dict[str,object]={
            'label':'UNKNOWN',
            'source_file':f'live:{msg.station_id}:{msg.event_id}',
            'start_seconds':elapsed,
            'duration_seconds':1.0,
            '_update_id':update_id,
        }
        row.update({name:float(value) for name,value in zip(FEATURE_COLUMNS,msg.features)})
        if update_id not in session.seen_updates:
            session.rows.append(row)
            session.seen_updates.add(update_id)
        cutoff=max(elapsed-self.max_history_seconds,0.0)
        while session.rows and float(session.rows[0]['start_seconds']) < cutoff:
            removed=session.rows.popleft()
            removed_id=removed.get('_update_id')
            if isinstance(removed_id,tuple) and len(removed_id)==2:
                session.seen_updates.discard((int(removed_id[0]),int(removed_id[1])))

        frame=pd.DataFrame(list(session.rows)).sort_values('start_seconds')
        frame=frame.tail(settings.hierarchy_max_evidence_windows)
        evidence_windows=int(len(frame))
        family=self.family_classifier.predict_rows(
            frame,
            air_target_confirmed=msg.air_target_confirmed,
        ) if evidence_windows else None

        model=self.classifier.load()
        if evidence_windows < settings.hierarchy_min_evidence_windows:
            return self._status(
                msg,elapsed,evidence_windows,family,
                status='warming_up',model_version=(str(model.get('version')) if model else 'missing'),
            )
        if model is None:
            return self._status(
                msg,elapsed,evidence_windows,family,status='model_missing',model_version='missing',
            )
        replay=self.classifier.replay(
            frame,source_file=str(row['source_file']),candidate_detection_seconds=0.0,model=model
        )
        snapshot=replay.snapshots[-1] if replay.snapshots else None
        if snapshot is None:
            return self._status(
                msg,elapsed,evidence_windows,family,
                status='unknown',model_version=str(model.get('version','unknown')),
            )
        return self._status(
            msg,elapsed,evidence_windows,family,
            best_label=snapshot.best_label,confidence=snapshot.confidence,margin=snapshot.margin,
            status=snapshot.status,type_lock_allowed=snapshot.type_lock_allowed,
            first_type_hypothesis_seconds=replay.first_type_hypothesis_seconds,
            research_stable_seconds=replay.research_stable_seconds,
            model_version=str(model.get('version','unknown')),
        )

    @staticmethod
    def _status(
        msg: FeatureUpdateMessage,
        elapsed: float,
        evidence_windows: int,
        family: FamilyClassificationResult | None,
        **type_fields: object,
    ) -> OnlineTypeStatusMessage:
        family_label=family.best_family if family else 'UNKNOWN'
        type_label=str(type_fields.get('best_label','UNKNOWN'))
        return OnlineTypeStatusMessage(
            station_id=msg.station_id,
            event_id=msg.event_id,
            elapsed_seconds=round(elapsed,3),
            evidence_windows=evidence_windows,
            required_windows=settings.hierarchy_min_evidence_windows,
            max_windows=settings.hierarchy_max_evidence_windows,
            family_label=family_label,
            family_confidence=(family.confidence if family else 0.0),
            family_margin=(family.margin if family else 0.0),
            family_status=(family.status if family else 'unknown'),
            family_operational_validation_ready=(family.operational_validation_ready if family else False),
            family_conditional_on_air_target=(family.conditional_on_air_target if family else False),
            family_model_version=(family.model_version if family else 'missing'),
            hierarchical_label=hierarchical_label(family_label,type_label),
            **type_fields,
        )

    def close(self, station_id: int, event_id: int) -> None:
        self.sessions.pop((int(station_id),int(event_id)),None)
